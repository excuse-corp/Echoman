"""
RAG对话服务

实现两种模式：
1. topic模式：基于特定主题的对话（强制引用主题内容）
2. global模式：全局检索TopK主题回答（检索增强）

优化：集成 TokenManager 以处理 qwen3-32b 的 32k 上下文限制
支持：SSE流式输出（ask_stream方法）
"""
from typing import List, Dict, Optional, Tuple, AsyncGenerator
from app.utils.timezone import now_cn
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import logging
import asyncio

from app.models import (
    Topic, TopicNode, SourceItem, Summary, 
    Chat
)
from app.services.llm.factory import get_llm_provider
from app.services.vector_service import get_vector_service
from app.config import settings
from app.utils.token_manager import get_token_manager
import numpy as np

logger = logging.getLogger(__name__)


class RAGService:
    """RAG对话服务"""
    
    MODE_TOPIC = "topic"
    MODE_GLOBAL = "global"
    
    def __init__(self):
        self.settings = settings
        self.llm_provider = get_llm_provider()
        self.token_manager = get_token_manager(model=settings.qwen_model)
        self.top_k = 10  # 检索TopK
        self.min_similarity = 0.3  # 最小相似度阈值
        
    async def ask(
        self,
        db: AsyncSession,
        query: str,
        mode: str = MODE_GLOBAL,
        topic_id: Optional[int] = None,
        chat_id: Optional[int] = None
    ) -> Dict:
        """
        处理用户提问
        
        Args:
            db: 数据库会话
            query: 用户问题
            mode: 对话模式（topic/global）
            topic_id: 主题ID（topic模式必需）
            chat_id: 会话ID（可选，用于上下文）
            
        Returns:
            {
                "answer": "回答内容",
                "citations": [引用列表],
                "diagnostics": {延迟/token等}
            }
        """
        start_time = now_cn()
        
        # 验证参数
        if mode == self.MODE_TOPIC and not topic_id:
            raise ValueError("topic模式需要提供topic_id")
        # chat_id 保留兼容性，当前版本仅在前端维护上下文
        _ = chat_id
        
        # 1. 检索相关内容
        if mode == self.MODE_TOPIC:
            context, citations = await self._retrieve_topic_context(
                db, topic_id, query
            )
        else:
            context, citations = await self._retrieve_global_context(
                db, query
            )
        
        # 2. 如果没有检索到内容，降级处理
        if not context:
            return await self._fallback_answer(query, mode)
        
        # 3. 格式化上下文为字符串
        formatted_context = self._format_context_chunks(context)
        
        # 4. Token 优化：确保不超过 32k 上下文限制
        system_prompt = self._get_system_prompt(mode)
        optimized_context, token_stats = self.token_manager.optimize_rag_context(
            query=query,
            context_chunks=[{"content": c} for c in formatted_context],
            system_prompt_template=system_prompt,
            max_completion_tokens=settings.rag_max_completion_tokens,
            text_key="content"
        )
        
        # 记录 Token 使用情况
        logger.info(
            f"RAG Token 使用: {token_stats['used_context_tokens']}/{token_stats['available_context_tokens']} "
            f"(原始块:{token_stats['original_chunks']}, 优化后:{token_stats['optimized_chunks']})"
        )
        
        # 提取优化后的上下文文本
        optimized_context_texts = [chunk["content"] for chunk in optimized_context]
        
        # 5. 构造Prompt
        prompt = self._build_rag_prompt(query, optimized_context_texts, mode)
        
        # 6. 调用LLM（使用优化后的参数）
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=settings.rag_max_completion_tokens  # 使用配置的值（2000）
            )
            
            # 7. 解析响应
            answer = self._parse_answer(response)
            
            # 8. 计算诊断信息
            end_time = now_cn()
            diagnostics = {
                "latency_ms": int((end_time - start_time).total_seconds() * 1000),
                "tokens_prompt": response.get("usage", {}).get("prompt_tokens", token_stats['used_context_tokens']),
                "tokens_completion": response.get("usage", {}).get("completion_tokens", 0),
                "context_chunks": len(optimized_context_texts),
                "original_chunks": len(context),
                "token_optimization": token_stats
            }
            
            return {
                "answer": answer,
                "citations": [self._format_citation(c) for c in citations],
                "diagnostics": diagnostics
            }
            
        except Exception as e:
            print(f"RAG对话失败: {e}")
            return await self._fallback_answer(query, mode)
    
    async def ask_stream(
        self,
        db: AsyncSession,
        query: str,
        mode: str = "global",
        topic_id: Optional[int] = None,
        chat_id: Optional[int] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        流式处理用户提问（SSE版本）
        
        Args:
            db: 数据库会话
            query: 用户问题
            mode: 对话模式（topic/global）
            topic_id: 主题ID（topic模式必需）
            chat_id: 会话ID（可选，用于上下文）
            
        Yields:
            事件字典，包含type和data：
            - {"type": "token", "data": {"content": "文字"}}
            - {"type": "citations", "data": {"citations": [...]}}
            - {"type": "done", "data": {"diagnostics": {...}}}
        """
        start_time = now_cn()
        
        try:
            # 验证参数
            if mode == self.MODE_TOPIC and not topic_id:
                yield {
                    "type": "error",
                    "data": {"message": "topic模式需要提供topic_id"}
                }
                return
            # chat_id 保留兼容性，当前版本仅在前端维护上下文
            _ = chat_id
            
            # 1. 检索相关内容
            if mode == self.MODE_TOPIC:
                context, citations = await self._retrieve_topic_context(
                    db, topic_id, query
                )
            else:
                context, citations = await self._retrieve_global_context(
                    db, query
                )
            
            # 2. 如果没有检索到内容，发送降级回答
            if not context:
                fallback = await self._fallback_answer(query, mode)
                # 逐字发送fallback答案
                for char in fallback["answer"]:
                    yield {
                        "type": "token",
                        "data": {"content": char}
                    }
                    await asyncio.sleep(0.02)  # 模拟打字效果
                
                yield {
                    "type": "done",
                    "data": {"diagnostics": fallback["diagnostics"]}
                }
                return
            
            # 3. 格式化上下文
            formatted_context = self._format_context_chunks(context)
            
            # 4. Token优化
            system_prompt = self._get_system_prompt(mode)
            optimized_context, token_stats = self.token_manager.optimize_rag_context(
                query=query,
                context_chunks=[{"content": c} for c in formatted_context],
                system_prompt_template=system_prompt,
                max_completion_tokens=settings.rag_max_completion_tokens,
                text_key="content"
            )
            
            optimized_context_texts = [chunk["content"] for chunk in optimized_context]
            
            # 5. 构造Prompt
            prompt = self._build_rag_prompt(query, optimized_context_texts, mode)
            
            # 6. 调用LLM流式API
            logger.info(f"开始流式生成回答，query长度: {len(query)}")
            
            full_answer = ""
            async for chunk in self.llm_provider.chat_completion_stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=settings.rag_max_completion_tokens
            ):
                # 提取文本内容
                content = chunk.get("content", "")
                if content:
                    full_answer += content
                    
                    # 发送token事件
                    yield {
                        "type": "token",
                        "data": {"content": content}
                    }
            
            # 7. 发送引用
            yield {
                "type": "citations",
                "data": {
                    "citations": [self._format_citation(c) for c in citations]
                }
            }
            
            # 8. 计算诊断信息
            end_time = now_cn()
            diagnostics = {
                "latency_ms": int((end_time - start_time).total_seconds() * 1000),
                "tokens_prompt": token_stats['used_context_tokens'],
                "tokens_completion": len(full_answer.split()),  # 估算
                "context_chunks": len(optimized_context_texts),
                "original_chunks": len(context)
            }
            
            # 9. 发送完成信号
            yield {
                "type": "done",
                "data": {"diagnostics": diagnostics}
            }
        
        except Exception as e:
            logger.error(f"流式RAG对话失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "data": {"message": f"对话处理失败: {str(e)}"}
            }
    
    async def _retrieve_topic_context(
        self,
        db: AsyncSession,
        topic_id: int,
        query: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        检索主题内上下文（topic模式）
        
        Returns:
            (context_chunks, citations)
        """
        # 1. 获取主题信息
        topic = await db.get(Topic, topic_id)
        if not topic:
            return [], []
        
        # 2. 获取主题摘要
        summary = None
        if topic.summary_id:
            summary = await db.get(Summary, topic.summary_id)
        
        # 3. 向量检索节点（如果有query embedding）
        query_embedding = await self._get_query_embedding(query)
        
        if query_embedding:
            # 向量检索最相关的节点
            relevant_nodes = await self._vector_search_nodes(
                db, topic_id, query_embedding, limit=5
            )
        else:
            # 降级：获取最新的几个节点
            relevant_nodes = await self._get_latest_nodes(db, topic_id, limit=5)
        
        # 4. 构造上下文
        context = []
        citations = []
        
        # 添加摘要
        if summary:
            context.append({
                "type": "summary",
                "content": summary.content,
                "metadata": {"topic_id": topic_id}
            })
        
        # 添加节点
        for node in relevant_nodes:
            if node.source_item:
                context.append({
                    "type": "node",
                    "platform": node.source_item.platform,
                    "title": node.source_item.title,
                    "summary": node.source_item.summary or "",
                    "url": node.source_item.url,
                    "published_at": node.source_item.published_at.isoformat() if node.source_item.published_at else ""
                })
                
                citations.append({
                    "topic_id": topic_id,
                    "node_id": node.id,
                    "source_url": node.source_item.url,
                    "snippet": node.source_item.title,
                    "platform": node.source_item.platform
                })
        
        return context, citations
    
    async def _retrieve_global_context(
        self,
        db: AsyncSession,
        query: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        全局检索上下文（global模式）
        
        Returns:
            (context_chunks, citations)
        """
        # 1. 向量检索相关主题
        query_embedding = await self._get_query_embedding(query)
        
        if query_embedding:
            relevant_topics = await self._vector_search_topics(
                db, query_embedding, limit=self.top_k
            )
        else:
            # 降级：获取最近活跃的主题
            relevant_topics = await self._get_recent_topics(db, limit=self.top_k)
        
        if not relevant_topics:
            return [], []
        
        # 2. 构造上下文
        context = []
        citations = []
        
        for topic in relevant_topics[:5]:  # 最多使用前5个主题
            # 添加主题摘要
            if topic.summary_id:
                summary = await db.get(Summary, topic.summary_id)
                if summary:
                    context.append({
                        "type": "topic_summary",
                        "topic_id": topic.id,
                        "title": topic.title_key,
                        "summary": summary.content
                    })
                    
                    # 获取该主题的代表性节点作为citation
                    nodes = await self._get_latest_nodes(db, topic.id, limit=2)
                    for node in nodes:
                        if node.source_item:
                            citations.append({
                                "topic_id": topic.id,
                                "node_id": node.id,
                                "source_url": node.source_item.url,
                                "snippet": node.source_item.title,
                                "platform": node.source_item.platform
                            })
        
        return context, citations
    
    async def _vector_search_nodes(
        self,
        db: AsyncSession,
        topic_id: int,
        query_embedding: List[float],
        limit: int = 5
    ) -> List[TopicNode]:
        """向量检索主题内的节点（Chroma 优先，降级为最新节点）"""
        vector_service = get_vector_service()

        # 从数据库拿到该主题的节点及其 source_item
        from sqlalchemy.orm import joinedload
        nodes_stmt = (
            select(TopicNode)
            .options(joinedload(TopicNode.source_item))
            .where(TopicNode.topic_id == topic_id)
        )
        nodes_result = await db.execute(nodes_stmt)
        nodes = list(nodes_result.scalars().all())
        if not nodes:
            return []

        if vector_service.db_type != "chroma":
            # 没有 Chroma 时退化：直接返回最新节点
            nodes.sort(key=lambda n: n.appended_at, reverse=True)
            return nodes[:limit]

        scored = []
        for node in nodes:
            if not node.source_item_id:
                continue
            vec = vector_service.get_embedding("source_item", int(node.source_item_id))
            if vec is None:
                continue
            # 计算余弦相似度
            a = np.array(query_embedding)
            b = np.array(vec)
            if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
                continue
            sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            scored.append((sim, node))

        if not scored:
            nodes.sort(key=lambda n: n.appended_at, reverse=True)
            return nodes[:limit]

        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:limit]]
    
    async def _vector_search_topics(
        self,
        db: AsyncSession,
        query_embedding: List[float],
        limit: int = 10
    ) -> List[Topic]:
        """向量检索相关主题（Chroma 优先）"""
        vector_service = get_vector_service()

        if vector_service.db_type == "chroma":
            try:
                ids, distances, metadatas = vector_service.search_similar(
                    query_embedding=query_embedding,
                    top_k=limit * 2,
                    where={"object_type": "topic_summary"}
                )
                topic_ids_ordered = []
                for meta, dist in zip(metadatas, distances):
                    tid = meta.get("topic_id") if meta else None
                    if tid and tid not in topic_ids_ordered:
                        topic_ids_ordered.append(tid)
                    if len(topic_ids_ordered) >= limit:
                        break
                
                if not topic_ids_ordered:
                    return []

                topics_stmt = select(Topic).where(Topic.id.in_(topic_ids_ordered))
                topics_result = await db.execute(topics_stmt)
                topics = {t.id: t for t in topics_result.scalars().all()}
                # 按检索顺序返回
                return [topics[tid] for tid in topic_ids_ordered if tid in topics]
            except Exception as e:
                logger.warning(f"Chroma 主题向量检索失败，回退：{e}")

        # 回退：最新活跃主题
        topics_stmt = (
            select(Topic)
            .where(Topic.status == "active")
            .order_by(Topic.last_active.desc())
            .limit(limit)
        )
        topics_result = await db.execute(topics_stmt)
        return list(topics_result.scalars().all())
    
    async def _get_latest_nodes(
        self,
        db: AsyncSession,
        topic_id: int,
        limit: int = 5
    ) -> List[TopicNode]:
        """获取主题的最新节点（降级方案）"""
        from sqlalchemy.orm import joinedload
        
        stmt = (
            select(TopicNode)
            .options(joinedload(TopicNode.source_item))
            .where(TopicNode.topic_id == topic_id)
            .order_by(TopicNode.appended_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_recent_topics(
        self,
        db: AsyncSession,
        limit: int = 10
    ) -> List[Topic]:
        """获取最近活跃的主题（降级方案）"""
        stmt = (
            select(Topic)
            .where(Topic.status == "active")
            .order_by(Topic.last_active.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """获取查询的向量表示"""
        try:
            embedding = await self.llm_provider.embedding(query)
            return embedding
        except Exception as e:
            print(f"获取query embedding失败: {e}")
            return None
    
    def _format_context_chunks(self, context: List[Dict]) -> List[str]:
        """
        格式化上下文块为字符串列表
        
        Args:
            context: 原始上下文字典列表
            
        Returns:
            格式化后的字符串列表
        """
        formatted = []
        
        for i, chunk in enumerate(context, 1):
            if chunk.get("type") == "summary":
                formatted.append(f"【主题摘要】\n{chunk['content']}")
            elif chunk.get("type") == "node":
                formatted.append(
                    f"{i}. [{chunk.get('platform', '未知')}] {chunk.get('published_at', '')}\n"
                    f"   {chunk.get('title', '')}\n"
                    f"   {chunk.get('summary', '')[:200]}"
                )
            elif chunk.get("type") == "topic_summary":
                formatted.append(
                    f"【主题：{chunk.get('title', '')}】\n{chunk.get('summary', '')}"
                )
            else:
                # 兜底：直接使用 content
                formatted.append(str(chunk.get('content', chunk)))
        
        return formatted
    
    def _get_system_prompt(self, mode: str) -> str:
        """获取系统 Prompt（用于 Token 预算估算）"""
        if mode == self.MODE_TOPIC:
            return """请基于以下主题内容回答用户问题：

要求：
1. 基于提供的参考内容回答，不要编造信息
2. 如果参考内容不足以回答问题，明确说明
3. 回答要准确、简洁、有条理
4. 可以引用具体的来源（如"根据微博消息..."）

请回答："""
        else:
            return """请基于以下检索到的相关内容回答用户问题：

要求：
1. 综合多个主题的信息回答
2. 如果没有找到相关内容，明确告知用户
3. 回答要准确、客观、有条理
4. 可以引用具体的主题或来源

请回答："""
    
    def _build_rag_prompt(
        self, 
        query: str, 
        context: List[str], 
        mode: str
    ) -> str:
        """构造RAG Prompt（context 现在是字符串列表）"""
        # context 已经是格式化的字符串列表，直接使用
        context_text = "\n\n".join(context)
        
        if mode == self.MODE_TOPIC:
            prompt = f"""请基于以下主题内容回答用户问题：

【参考内容】
{context_text}

【用户问题】
{query}

要求：
1. 基于提供的参考内容回答，不要编造信息
2. 如果参考内容不足以回答问题，明确说明
3. 回答要准确、简洁、有条理
4. 可以引用具体的来源（如"根据微博消息..."）

请回答：
"""
        else:
            prompt = f"""请基于以下检索到的相关内容回答用户问题：

【参考内容】（按相关性排序）
{context_text}

【用户问题】
{query}

要求：
1. 综合多个主题的信息回答
2. 如果没有找到相关内容，明确告知用户
3. 回答要准确、客观、有条理
4. 可以引用具体的主题或来源

请回答：
"""
        
        return prompt
    
    def _parse_answer(self, response: str) -> str:
        """解析LLM回答"""
        # 简单处理，直接返回response
        return response.strip()
    
    async def _fallback_answer(self, query: str, mode: str) -> Dict:
        """降级回答"""
        if mode == self.MODE_TOPIC:
            answer = "抱歉，该主题暂时没有足够的信息来回答您的问题。"
        else:
            answer = "抱歉，没有找到与您问题相关的内容。请尝试换个问法或提供更多关键词。"
        
        return {
            "answer": answer,
            "citations": [],
            "diagnostics": {
                "latency_ms": 0,
                "tokens_prompt": 0,
                "tokens_completion": 0,
                "context_chunks": 0,
                "fallback": True
            }
        }
    
    def _format_citation(self, citation: Dict) -> Dict:
        """格式化引用"""
        return {
            "topic_id": citation.get("topic_id"),
            "node_id": citation.get("node_id"),
            "source_url": citation.get("source_url", ""),
            "snippet": citation.get("snippet", ""),
            "platform": citation.get("platform", "")
        }
    
    async def create_chat(
        self,
        db: AsyncSession,
        mode: str = MODE_GLOBAL,
        topic_id: Optional[int] = None
    ) -> Chat:
        """创建新会话"""
        chat = Chat(
            mode=mode,
            topic_id=topic_id,
            created_at=now_cn()
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        return chat
