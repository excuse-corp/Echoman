"""
RAG对话服务

实现两种模式：
1. topic模式：基于特定主题的对话（强制引用主题内容）
2. global模式：全局检索TopK主题回答（检索增强）

优化：集成 TokenManager 以处理 qwen3-32b 的 32k 上下文限制
支持：SSE流式输出（ask_stream方法）
"""
from typing import List, Dict, Optional, Tuple, AsyncGenerator, Any
from decimal import Decimal
from datetime import datetime, timedelta, date
import re
from app.utils.timezone import now_cn
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import json
import logging
import asyncio

from app.models import (
    Topic, TopicNode, SourceItem, Summary, 
    Chat
)
from app.services.llm.factory import get_llm_provider, get_embedding_provider
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
        self.embedding_provider = get_embedding_provider()
        self.token_manager = get_token_manager(model=settings.qwen_model)
        self.top_k = 10  # 检索TopK
        self.min_similarity = 0.7  # 向量相似度阈值（1为满分）
        self.platform_aliases = {
            "微博": "weibo",
            "知乎": "zhihu",
            "头条": "toutiao",
            "今日头条": "toutiao",
            "新浪": "sina",
            "新浪新闻": "sina",
            "腾讯": "tencent",
            "腾讯新闻": "tencent",
            "网易": "netease",
            "网易新闻": "netease",
            "百度": "baidu",
            "百度热搜": "baidu",
            "虎扑": "hupu",
            "抖音": "douyin",
            "小红书": "xiaohongshu",
        }
        self.query_stopwords = {
            "最近", "最新", "新闻", "情况", "相关", "有哪些", "有什么", "什么", "关于", "事件", "热点", "消息", "动态",
            "进展", "现在", "今天", "昨日", "昨天", "前天", "今日", "谁", "哪里", "为何", "为什么", "怎么", "如何",
        }
        
    async def ask(
        self,
        db: AsyncSession,
        query: str,
        mode: str = MODE_GLOBAL,
        topic_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None
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
            return await self._ask_global_with_agent(db, query, start_time, history)
        
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
            answer = self._strip_think_blocks(answer)
            
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
        chat_id: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None
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
                async for event in self._ask_global_with_agent_stream(db, query, start_time, history):
                    yield event
                return
            
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
            suppress_think = False
            think_buffer = ""
            async for chunk in self.llm_provider.chat_completion_stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=settings.rag_max_completion_tokens
            ):
                # 提取文本内容
                content = chunk.get("content", "")
                if content:
                    full_answer += content
                    filtered, suppress_think, think_buffer = self._filter_think_stream(
                        content,
                        suppress_think,
                        think_buffer
                    )
                    if filtered:
                        yield {
                            "type": "token",
                            "data": {"content": filtered}
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
        # 0. 解析自由模式意图（关键词/时间/平台）
        intent = await self._parse_free_query_intent(query)
        keywords = intent.get("keywords", [])
        keyword_topics = []
        if keywords:
            keyword_topics = await self._search_topics_by_keywords(db, keywords, limit=self.top_k)

        # 1. 向量检索相关主题
        query_embedding = await self._get_query_embedding(query)

        vector_topics: List[Topic] = []
        if query_embedding:
            vector_topics = await self._vector_search_topics(
                db, query_embedding, limit=self.top_k
            )

        if keyword_topics:
            topic_map = {t.id: t for t in keyword_topics}
            for t in vector_topics:
                topic_map.setdefault(t.id, t)
            relevant_topics = list(topic_map.values())[: self.top_k]
        elif vector_topics:
            relevant_topics = vector_topics
        else:
            # 降级：获取最近活跃的主题
            relevant_topics = await self._get_recent_topics(db, limit=self.top_k)
        
        if not relevant_topics:
            return [], []

        # 2. 结构化过滤（平台/时间）
        filtered_topics = await self._apply_intent_filters(db, relevant_topics, intent)
        if not filtered_topics:
            filtered_topics = relevant_topics

        # 3. 关键词重排
        reranked_topics, max_keyword_score = self._rerank_topics_by_keywords(
            filtered_topics, keywords
        )
        if keywords and max_keyword_score == 0:
            return [], []

        # 4. 构造上下文
        context = []
        citations = []

        platforms = intent.get("platforms", [])
        for topic in reranked_topics[:5]:  # 最多使用前5个主题
            # 添加主题摘要
            summary = None
            if topic.summary_id:
                summary = await db.get(Summary, topic.summary_id)

            topic_platforms = await self._get_topic_platforms(db, topic.id)
            context.append({
                "type": "topic_overview",
                "topic_id": topic.id,
                "title": topic.title_key,
                "first_seen": topic.first_seen.isoformat() if topic.first_seen else "",
                "last_active": topic.last_active.isoformat() if topic.last_active else "",
                "platforms": topic_platforms,
                "summary": summary.content if summary else ""
            })

            if summary:
                context.append({
                    "type": "topic_summary",
                    "topic_id": topic.id,
                    "title": topic.title_key,
                    "summary": summary.content
                })

            # 获取该主题的代表性节点作为citation + 补充上下文
            nodes = await self._get_latest_nodes(db, topic.id, limit=2, platforms=platforms or None)
            for idx, node in enumerate(nodes):
                if node.source_item:
                    citations.append({
                        "topic_id": topic.id,
                        "node_id": node.id,
                        "source_url": node.source_item.url,
                        "snippet": node.source_item.title,
                        "platform": node.source_item.platform
                    })
                    if idx == 0:
                        context.append({
                            "type": "node",
                            "platform": node.source_item.platform,
                            "title": node.source_item.title,
                            "summary": node.source_item.summary or "",
                            "url": node.source_item.url,
                            "published_at": node.source_item.published_at.isoformat() if node.source_item.published_at else ""
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
        limit: int = 5,
        platforms: Optional[List[str]] = None
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
        if platforms:
            stmt = (
                select(TopicNode)
                .options(joinedload(TopicNode.source_item))
                .join(SourceItem, TopicNode.source_item_id == SourceItem.id)
                .where(TopicNode.topic_id == topic_id, SourceItem.platform.in_(platforms))
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
            embedding = await self.embedding_provider.embedding([query])
            if isinstance(embedding, list) and embedding and isinstance(embedding[0], list):
                return embedding[0]
            return embedding
        except Exception as e:
            print(f"获取query embedding失败: {e}")
            return None

    async def _ask_global_with_agent(
        self,
        db: AsyncSession,
        query: str,
        start_time: datetime,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict:
        """自由模式 Agent：工具调用 + 整理分析"""
        tool_calls, allow_empty = await self._agent_plan_tool_calls(query, history)
        tool_outputs, citations, used_tools = await self._agent_execute_tools(
            db,
            tool_calls,
            query,
            allow_empty=allow_empty
        )

        prompt = self._build_agent_final_prompt(query, tool_outputs, history)
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=settings.rag_max_completion_tokens
            )
            answer = self._parse_answer(response)
            answer = self._strip_think_blocks(answer)
            answer = answer + self._format_tool_usage(used_tools)
            end_time = now_cn()
            diagnostics = {
                "latency_ms": int((end_time - start_time).total_seconds() * 1000),
                "tokens_prompt": response.get("usage", {}).get("prompt_tokens", 0),
                "tokens_completion": response.get("usage", {}).get("completion_tokens", 0),
                "context_chunks": len(tool_outputs),
                "original_chunks": len(tool_outputs)
            }
            return {
                "answer": answer,
                "citations": citations,
                "diagnostics": diagnostics
            }
        except Exception as e:
            print(f"自由模式Agent失败: {e}")
            return await self._fallback_answer(query, self.MODE_GLOBAL)

    async def _ask_global_with_agent_stream(
        self,
        db: AsyncSession,
        query: str,
        start_time: datetime,
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[Dict, None]:
        """自由模式 Agent 流式输出"""
        tool_calls, allow_empty = await self._agent_plan_tool_calls(query, history)
        tool_outputs, citations, used_tools = await self._agent_execute_tools(
            db,
            tool_calls,
            query,
            allow_empty=allow_empty
        )
        prompt = self._build_agent_final_prompt(query, tool_outputs, history)

        full_answer = ""
        suppress_think = False
        think_buffer = ""

        async for chunk in self.llm_provider.chat_completion_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=settings.rag_max_completion_tokens
        ):
            content = chunk.get("content", "")
            if content:
                full_answer += content
                filtered, suppress_think, think_buffer = self._filter_think_stream(
                    content,
                    suppress_think,
                    think_buffer
                )
                if filtered:
                    yield {
                        "type": "token",
                        "data": {"content": filtered}
                    }

        if used_tools:
            tool_line = self._format_tool_usage(used_tools)
            full_answer += tool_line
            yield {
                "type": "token",
                "data": {"content": tool_line}
            }

        yield {
            "type": "citations",
            "data": {"citations": citations}
        }

        end_time = now_cn()
        diagnostics = {
            "latency_ms": int((end_time - start_time).total_seconds() * 1000),
            "tokens_prompt": 0,
            "tokens_completion": len(full_answer.split()),
            "context_chunks": len(tool_outputs),
            "original_chunks": len(tool_outputs)
        }
        yield {
            "type": "done",
            "data": {"diagnostics": diagnostics}
        }

    async def _agent_plan_tool_calls(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """让Agent决定调用哪些工具（返回 tool_calls 和 allow_empty 标记）"""
        resolved_query, followup_flags, refine_only = self._resolve_followup_query(query, history)
        plan = await self._llm_plan_agent(resolved_query, history)
        intent = (plan.get("intent") or "").lower()
        if refine_only:
            last_tool = self._extract_last_tool_from_history(history)
            if intent == "chat":
                if last_tool == "topic_query":
                    intent = "query"
                elif last_tool == "topic_search":
                    intent = "search"
                else:
                    intent = "search"
        if intent == "chat":
            return [], True

        if intent == "query":
            filters = {}
            plan_filters = plan.get("filters") if isinstance(plan.get("filters"), dict) else {}
            plan_filters = self._apply_followup_filter_overrides(plan_filters, followup_flags)
            time_range = plan_filters.get("time_range") if isinstance(plan_filters.get("time_range"), dict) else None
            if time_range:
                filters["date_range"] = {
                    "start": time_range.get("start"),
                    "end": time_range.get("end"),
                }
            if isinstance(plan_filters.get("recent_days"), int):
                filters["recent_days"] = plan_filters.get("recent_days")
            platforms = plan_filters.get("platforms") if isinstance(plan_filters.get("platforms"), list) else []
            platforms = [p for p in platforms if isinstance(p, str) and p]
            if platforms:
                filters["platforms"] = platforms
            locations = plan_filters.get("locations") if isinstance(plan_filters.get("locations"), list) else []
            locations = [p for p in locations if isinstance(p, str) and p]
            if locations:
                filters["title_contains"] = locations[0]
            keywords = plan.get("keywords") if isinstance(plan.get("keywords"), list) else []
            if keywords:
                filters["title_contains"] = keywords[0]
            return [{
                "tool": "topic_query",
                "args": {
                    "fields": [
                        "topic_id",
                        "title",
                        "summary",
                        "first_seen",
                        "last_active",
                        "echo_length_hours",
                        "intensity_total",
                    ],
                    "filters": filters,
                    "order_by": "echo_length_desc",
                    "limit": 20
                }
            }], False

        if intent in ("search", "analysis", "compare"):
            plan_filters = plan.get("filters") if isinstance(plan.get("filters"), dict) else {}
            plan_filters = self._apply_followup_filter_overrides(plan_filters, followup_flags)
            return [{
                "tool": "topic_search",
                "args": {
                    "query": resolved_query,
                    "keywords": plan.get("keywords"),
                    "filters": plan_filters,
                    "match_logic": plan.get("match_logic"),
                }
            }], False

        # 兜底：默认执行 topic_search
        return [{"tool": "topic_search", "args": {"query": resolved_query}}], False

    def _route_agent_tools(self, query: str) -> List[Dict[str, Any]]:
        """基于关键词的硬路由规则"""
        lowered = query.lower()
        trigger_keywords = [
            "筛选", "列出", "排名", "统计", "汇总", "top", "榜单", "表", "字段", "sql", "排序", "返回标题", "持续时间",
        ]
        if any(key in query for key in trigger_keywords) or any(key in lowered for key in ["top", "sql"]):
            filters = {}
            date_match = re.search(r"(\d{4})[-\\/年](\d{1,2})[-\\/月](\d{1,2})", query)
            if date_match:
                y, m, d = date_match.groups()
                date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                filters["date_range"] = {"start": date_str, "end": date_str}
            return [{
                "tool": "topic_query",
                "args": {
                    "fields": [
                        "topic_id",
                        "title",
                        "summary",
                        "first_seen",
                        "last_active",
                        "echo_length_hours",
                        "intensity_total",
                    ],
                    "filters": filters,
                    "order_by": "last_active_desc",
                    "limit": 20
                }
            }]
        return []

    async def _agent_execute_tools(
        self,
        db: AsyncSession,
        tool_calls: List[Dict[str, Any]],
        query: str,
        allow_empty: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        outputs: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        used_tools: List[str] = []

        for call in tool_calls:
            tool = call.get("tool")
            args = call.get("args", {}) if isinstance(call.get("args"), dict) else {}
            if tool == "topic_query":
                result = await self._tool_topic_query(db, args)
                outputs.append({"tool": "topic_query", "output": result})
                used_tools.append("topic_query")
            elif tool == "topic_search":
                result = await self._tool_topic_search(db, args, query)
                outputs.append({"tool": "topic_search", "output": result})
                used_tools.append("topic_search")
                for item in result.get("merged", []):
                    urls = item.get("example_urls") or []
                    citations.append({
                        "topic_id": item.get("topic_id"),
                        "node_id": None,
                        "source_url": urls[0] if urls else "",
                        "snippet": item.get("title", ""),
                        "platform": ""
                    })
            else:
                continue

        if not outputs and not allow_empty:
            outputs.append({"tool": "topic_search", "output": await self._tool_topic_search(db, {}, query)})
            used_tools.append("topic_search")

        used_tools = list(dict.fromkeys(used_tools))
        return outputs, citations, used_tools

    async def _tool_topic_query(self, db: AsyncSession, args: Dict[str, Any]) -> Dict[str, Any]:
        """工具：查询 topic_item 物化视图"""
        allowed_fields = {
            "topic_id",
            "title",
            "summary",
            "first_seen",
            "last_active",
            "status",
            "category",
            "echo_length_hours",
            "intensity_total",
            "heat_normalized",
            "item_title",
            "item_summary",
            "item_url",
            "item_platform",
            "item_published_at",
        }
        fields = args.get("fields") if isinstance(args.get("fields"), list) else None
        if not fields:
            fields = [
                "topic_id",
                "title",
                "summary",
                "first_seen",
                "last_active",
                "category",
                "echo_length_hours",
                "intensity_total",
            ]
        fields = [f for f in fields if f in allowed_fields]
        if not fields:
            fields = ["topic_id", "title", "last_active"]

        filters = args.get("filters") if isinstance(args.get("filters"), dict) else {}
        order_by = args.get("order_by", "echo_length_desc")
        limit = int(args.get("limit", 10))
        limit = max(1, min(limit, 50))

        where_clauses = []
        params: Dict[str, Any] = {"limit": limit}
        if filters.get("status"):
            where_clauses.append("status = :status")
            params["status"] = filters.get("status")
        if filters.get("category"):
            where_clauses.append("category = :category")
            params["category"] = filters.get("category")
        if filters.get("title_contains"):
            where_clauses.append("title ILIKE :title_contains")
            params["title_contains"] = f"%{filters.get('title_contains')}%"
        platforms = filters.get("platforms") if isinstance(filters.get("platforms"), list) else []
        platforms = [p for p in platforms if isinstance(p, str) and p]
        if platforms:
            where_clauses.append("item_platform = ANY(:platforms)")
            params["platforms"] = platforms
        date_range = filters.get("date_range") if isinstance(filters.get("date_range"), dict) else {}
        start = self._parse_date_string(date_range.get("start"))
        end = self._parse_date_string(date_range.get("end"), end_of_day=True)
        recent_days = filters.get("recent_days")
        if isinstance(recent_days, int) and recent_days > 0 and not start:
            start = now_cn() - timedelta(days=recent_days)
        if start:
            where_clauses.append("last_active >= :start_date")
            params["start_date"] = start
        if end:
            where_clauses.append("first_seen <= :end_date")
            params["end_date"] = end

        order_sql = "echo_length_hours DESC NULLS LAST"
        if order_by == "heat_desc":
            order_sql = "heat_normalized DESC NULLS LAST"
        elif order_by == "intensity_desc":
            order_sql = "intensity_total DESC NULLS LAST"
        elif order_by == "first_seen_desc":
            order_sql = "first_seen DESC"
        elif order_by == "last_active_desc":
            order_sql = "last_active DESC NULLS LAST"
        elif order_by == "echo_length_desc":
            order_sql = "echo_length_hours DESC NULLS LAST"

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        item_fields = [
            "item_title",
            "item_summary",
            "item_url",
            "item_platform",
            "item_published_at",
        ]
        select_fields = ", ".join(fields + [f for f in item_fields if f not in fields])
        sql = f"""
            WITH ranked AS (
              SELECT
                {select_fields},
                item_fetched_at,
                ROW_NUMBER() OVER (
                  PARTITION BY topic_id
                  ORDER BY item_published_at DESC NULLS LAST, item_fetched_at DESC NULLS LAST
                ) AS rn
              FROM topic_item_mv
              {where_sql}
            )
            SELECT {select_fields}
            FROM ranked
            WHERE rn = 1
            ORDER BY {order_sql}
            LIMIT :limit
        """
        result = await db.execute(text(sql), params)
        rows = result.mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            # 确保时间序列为字符串
            for key, value in list(item.items()):
                if isinstance(value, datetime):
                    item[key] = value.isoformat()
                elif isinstance(value, Decimal):
                    item[key] = float(value)
            items.append(item)

        return {
            "count": len(items),
            "items": items,
            "fields": fields,
            "filters": filters,
            "order_by": order_by,
        }

    async def _tool_topic_search(self, db: AsyncSession, args: Dict[str, Any], query: str) -> Dict[str, Any]:
        """工具：topic 检索工作流（向量 + 标题关键词）"""
        input_query = args.get("query") if args.get("query") else query
        keywords = args.get("keywords") if isinstance(args.get("keywords"), list) else []
        search_plan = await self._llm_parse_topic_search(input_query)
        plan_keywords = search_plan.get("keywords") if isinstance(search_plan.get("keywords"), list) else []
        if not keywords and plan_keywords:
            keywords = plan_keywords
        if not keywords:
            keywords = self._extract_query_keywords(input_query)
        # 过滤无效/泛化关键词
        keywords = [k for k in keywords if k and k not in self.query_stopwords]

        filters = args.get("filters") if isinstance(args.get("filters"), dict) else {}
        plan_filters = search_plan.get("filters") if isinstance(search_plan.get("filters"), dict) else {}
        if not filters:
            filters = plan_filters

        match_logic = args.get("match_logic") or search_plan.get("match_logic")
        if match_logic not in ("and", "or"):
            match_logic = "or"

        limit = args.get("limit")
        if not isinstance(limit, int) or limit <= 0:
            limit = 10

        recent_days = filters.get("recent_days")
        if not isinstance(recent_days, int) or recent_days <= 0:
            recent_days = None
        time_range = filters.get("time_range") if isinstance(filters.get("time_range"), dict) else {}
        start = self._parse_date_string(time_range.get("start"))
        end = self._parse_date_string(time_range.get("end"), end_of_day=True)

        if recent_days and not start:
            start = now_cn() - timedelta(days=recent_days)

        locations = filters.get("locations") if isinstance(filters.get("locations"), list) else []
        locations = [p for p in locations if isinstance(p, str) and p]
        if locations:
            for loc in locations:
                if loc not in keywords:
                    keywords.append(loc)

        keyword_hits = await self._search_topics_by_keywords(
            db,
            keywords,
            limit=None,
            recent_days=recent_days,
            match_all=(match_logic == "and"),
            start_date=start,
            end_date=end
        )

        vector_hits: List[Topic] = []
        embedding = await self._get_query_embedding(input_query)
        if embedding:
            vector_hits = await self._vector_search_topics_strict(db, embedding, limit=3)
            if start or end:
                vector_hits = [t for t in vector_hits if self._topic_in_range(t, start, end)]
            elif recent_days:
                cutoff = now_cn() - timedelta(days=recent_days)
                vector_hits = [t for t in vector_hits if t.last_active and t.last_active >= cutoff]

        platforms = filters.get("platforms") if isinstance(filters.get("platforms"), list) else []
        platforms = [p for p in platforms if isinstance(p, str) and p]
        if platforms:
            keyword_hits = await self._filter_topics_by_platform(db, keyword_hits, platforms)
            vector_hits = await self._filter_topics_by_platform(db, vector_hits, platforms)

        merged = []
        seen_ids = set()
        topic_ids = []
        for topic in keyword_hits + vector_hits:
            if topic.id in seen_ids:
                continue
            seen_ids.add(topic.id)
            topic_ids.append(topic.id)

        view_rows = await self._fetch_topic_view_by_ids(db, topic_ids, order_by="echo_length_desc")
        for row in view_rows:
            merged.append(row)

        merged = merged[:limit] if limit else merged
        return {
            "query": input_query,
            "keywords": keywords,
            "search_plan": {
                "keywords": keywords,
                "filters": {
                    "recent_days": recent_days,
                    "time_range": time_range if time_range else None,
                    "platforms": platforms if platforms else None,
                    "locations": locations if locations else None,
                },
                "match_logic": match_logic,
            },
            "keyword_hits": [
                {"topic_id": t.id, "title": t.title_key} for t in keyword_hits
            ],
            "vector_hits": [
                {"topic_id": t.id, "title": t.title_key} for t in vector_hits
            ],
            "merged": merged,
            "total_count": len(topic_ids)
        }

    async def _llm_parse_topic_search(self, query: str) -> Dict[str, Any]:
        """让LLM解析检索关键词、过滤条件和匹配逻辑"""
        prompt = (
            "你是搜索指令解析器，请从用户问题中抽取检索关键词和过滤条件，输出JSON。\n"
            "要求：\n"
            "1) keywords 仅包含用于检索的核心短语（中文短语、英文或数字），不要包含“最近/最新/今天”等时间词。\n"
            "2) filters 包含过滤条件，可选：\n"
            "   - recent_days: 最近N天（整数，无法判断则为null）\n"
            "   - time_range: {\"start\":\"YYYY-MM-DD\"|null,\"end\":\"YYYY-MM-DD\"|null}\n"
            "   - platforms: 平台英文代码数组（weibo, zhihu, toutiao, sina, netease, baidu, hupu, douyin, xiaohongshu, tencent）\n"
            "   - locations: 地点/地区关键词数组（可选）\n"
            "3) match_logic 只能是 \"and\" 或 \"or\"，表示关键词检索的并且/或者逻辑；除非用户明确要求同时满足多个条件，否则优先使用 \"or\"。\n"
            "   如果关键词是同一实体的不同称谓（如“美国总统/特朗普”），应选择 \"or\"。\n"
            "输出JSON格式：{\"keywords\":[...],\"filters\":{...},\"match_logic\":\"and\"|\"or\"}\n"
            f"用户问题：{query}\n"
            "只输出JSON，不要输出其他内容。"
        )
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
                response_format="json",
            )
            content = response.get("content", "") if isinstance(response, dict) else str(response)
            parsed = self._extract_json(content)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def _llm_plan_agent(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """让LLM判断用户意图并生成检索计划"""
        history_text = self._format_history_for_prompt(history)
        prompt = (
            "你是对话意图与检索计划解析器，请结合对话历史与用户当前问题输出JSON。\n"
            "intent 只能是：chat | search | query | analysis | compare。\n"
            "- chat：闲聊/问候/寒暄/身份确认，不需要检索。\n"
            "- search：需要检索热点/事件。\n"
            "- query：需要结构化数据查询、统计、筛选、排行、字段输出。\n"
            "- analysis/compare：需要基于检索结果进行分析或对比。\n"
            "keywords：用于检索的核心短语数组（不要包含时间词）。\n"
            "filters：过滤条件，可选 recent_days / time_range / platforms / locations。\n"
            "match_logic：关键词检索的 and/or，除非用户明确要求多条件同时满足，否则优先 or。\n"
            "输出JSON格式：{\"intent\":\"search\",\"keywords\":[...],\"filters\":{...},\"match_logic\":\"or\"}\n\n"
            f"对话历史：\n{history_text}\n\n"
            f"用户问题：{query}\n"
            "只输出JSON，不要输出其他内容。"
        )
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=250,
                response_format="json",
            )
            content = response.get("content", "") if isinstance(response, dict) else str(response)
            parsed = self._extract_json(content)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _build_agent_system_prompt(self) -> str:
        return (
            "你是Echoman，基于AI能力为用户记录全网热点事件的持续时长和声量强度，"
            "可以为用户提供相关事件查询和数据分析。"
            "输出要有条理：先给1-2句总结，再给清晰的分析段落。不要输出表格、JSON或代码。"
            "默认输出10条topic；若工具输出不足10条，则按实际条数输出。"
            "输出时请包含每个topic对应的代表性原文URL，使用Markdown链接格式，例如[微博链接1](https://...)."
            "每个topic必须包含回声长度和回声强度，分别对应 echo_length_hours 和 intensity_total。"
            "不需要思考过程，不要输出<think>标签，只输出最终答案。"
            "如果工具输出为空数组，表示未调用工具，请按正常对话回复，不要提到检索结果。"
            "如果已调用工具但结果为空，明确说明未找到相关内容。"
            "在总结段落最后加入命中说明，并放在topic列表之前单独成行："
            "如果命中话题数>=10，写“本次命中X条话题，以下是前10条话题”。"
            "如果命中话题数<10，写“本次命中X条话题”。"
        )

    def _build_agent_tool_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "topic_query",
                "description": "查询 topic_item_mv 视图，支持字段选择、过滤、排序和限制",
                "args": {
                    "fields": "字段列表，例如['topic_id','title','summary','first_seen','last_active','category','echo_length_hours','intensity_total']",
                    "filters": {
                        "status": "active|ended",
                        "category": "entertainment|current_affairs|sports_esports",
                        "title_contains": "标题关键词",
                        "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
                        "recent_days": "最近N天过滤",
                        "platforms": "平台英文代码数组"
                    },
                    "order_by": "echo_length_desc|last_active_desc|heat_desc|intensity_desc|first_seen_desc",
                    "limit": "1-50"
                }
            },
            {
                "name": "topic_search",
                "description": "topic检索工作流（向量匹配+标题关键词），返回top3结果",
                "args": {
                    "query": "用户查询",
                    "keywords": "关键词数组，可省略",
                    "filters": {
                        "recent_days": "最近N天过滤（可选）",
                        "time_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
                        "platforms": "平台英文代码数组",
                        "locations": "地点/地区关键词数组"
                    },
                    "match_logic": "and|or",
                    "limit": "返回topic数量（默认10）"
                }
            }
        ]

    def _build_agent_final_prompt(
        self,
        query: str,
        tool_outputs: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        history_text = self._format_history_for_prompt(history)
        tool_text = json.dumps(tool_outputs, ensure_ascii=False)
        return (
            f"{self._build_agent_system_prompt()}\n\n"
            f"对话历史：\n{history_text}\n\n"
            f"用户问题：{query}\n\n"
            f"工具输出：{tool_text}\n\n"
            "请基于工具输出进行回答与分析。"
        )

    def _format_tool_usage(self, tools: List[str]) -> str:
        if not tools:
            return "\n\n（本次使用工具：无）"
        tools = sorted(set(tools))
        return f"\n\n（本次使用工具：{', '.join(tools)}）"

    def _format_history_for_prompt(self, history: Optional[List[Dict[str, str]]]) -> str:
        if not history:
            return "（无）"
        trimmed = history[-8:]
        lines = []
        for item in trimmed:
            role = (item.get("role") or "").strip().lower()
            content = (item.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                prefix = "助手"
            else:
                prefix = "用户"
            lines.append(f"{prefix}：{content}")
        return "\n".join(lines) if lines else "（无）"

    def _extract_last_user_query(self, history: Optional[List[Dict[str, str]]]) -> str:
        if not history:
            return ""
        for item in reversed(history):
            role = (item.get("role") or "").lower()
            if role != "user":
                continue
            content = (item.get("content") or "").strip()
            if content:
                return content
        return ""

    def _extract_last_tool_from_history(self, history: Optional[List[Dict[str, str]]]) -> str:
        if not history:
            return ""
        for item in reversed(history):
            role = (item.get("role") or "").lower()
            if role != "assistant":
                continue
            content = item.get("content") or ""
            if "本次使用工具" not in content:
                continue
            match = re.search(r"本次使用工具：([^)\\n]+)", content)
            if not match:
                continue
            tools = [t.strip() for t in match.group(1).split(",")]
            if "topic_query" in tools:
                return "topic_query"
            if "topic_search" in tools:
                return "topic_search"
        return ""

    def _resolve_followup_query(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]]
    ) -> Tuple[str, Dict[str, Any], bool]:
        text = (query or "").strip()
        flags: Dict[str, Any] = {"force_all_time": False, "force_recent_days": None}

        if re.search(r"(不要|不需要|去掉|取消).*(近期|最近|近来|最新)|全部时间|所有时间|不限时间|不限制时间|全量|不限范围|全部范围", text):
            flags["force_all_time"] = True
        if re.search(r"(近一周|最近7天|近7天|本周)", text):
            flags["force_recent_days"] = 7
        elif re.search(r"(近两周|最近14天|近14天)", text):
            flags["force_recent_days"] = 14
        elif re.search(r"(近一月|最近30天|近30天|本月)", text):
            flags["force_recent_days"] = 30
        elif re.search(r"(近三月|最近90天|近90天)", text):
            flags["force_recent_days"] = 90
        elif re.search(r"(近半年|最近180天|近180天)", text):
            flags["force_recent_days"] = 180

        modifier_pattern = r"(不要|不需要|去掉|取消|改为|改成|全部|所有|不限|不限制|近期|最近|近来|最新|时间|范围|只要|只看|仅|只|的|，|,|。|\\s)"
        stripped = re.sub(modifier_pattern, "", text)
        content_tokens = re.findall(r"[A-Za-z0-9]{3,}|[\u4e00-\u9fff]{2,}", stripped)
        refine_only = len(content_tokens) == 0

        resolved_query = text
        last_user_query = self._extract_last_user_query(history)
        if refine_only and last_user_query:
            resolved_query = f"{last_user_query} {text}"

        return resolved_query, flags, refine_only

    def _apply_followup_filter_overrides(
        self,
        filters: Dict[str, Any],
        flags: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = dict(filters or {})
        if flags.get("force_all_time"):
            result.pop("recent_days", None)
            result.pop("time_range", None)
        if isinstance(flags.get("force_recent_days"), int):
            result["recent_days"] = int(flags["force_recent_days"])
        return result

    async def _vector_search_topics_strict(
        self,
        db: AsyncSession,
        query_embedding: List[float],
        limit: int = 3
    ) -> List[Topic]:
        """向量检索相关主题（严格模式：不回退到最新主题）"""
        vector_service = get_vector_service()
        if vector_service.db_type != "chroma":
            return []
        try:
            ids, distances, metadatas = vector_service.search_similar(
                query_embedding=query_embedding,
                top_k=max(limit * 10, limit),
                where={"object_type": "topic_summary"}
            )
            metric = (settings.vector_similarity_metric or "cosine").lower()
            candidates = []
            for meta, dist in zip(metadatas or [], distances or []):
                if not meta:
                    continue
                tid = meta.get("topic_id")
                if not tid or dist is None:
                    continue
                if metric == "cosine":
                    similarity = 1 - float(dist)
                elif metric in ("ip", "inner_product", "dot"):
                    similarity = float(dist)
                else:
                    similarity = 1 / (1 + float(dist))
                if similarity < self.min_similarity:
                    continue
                candidates.append((tid, similarity))

            # 取相似度最高的 top3
            best_by_id: Dict[int, float] = {}
            for tid, sim in candidates:
                if tid not in best_by_id or sim > best_by_id[tid]:
                    best_by_id[tid] = sim
            topic_ids_ordered = [
                tid for tid, _ in sorted(best_by_id.items(), key=lambda x: x[1], reverse=True)
            ][:limit]
            if not topic_ids_ordered:
                return []
            topics_stmt = select(Topic).where(Topic.id.in_(topic_ids_ordered))
            topics_result = await db.execute(topics_stmt)
            topics = {t.id: t for t in topics_result.scalars().all()}
            return [topics[tid] for tid in topic_ids_ordered if tid in topics]
        except Exception as e:
            logger.warning(f"Chroma 主题向量检索失败（严格模式），回退为空：{e}")
            return []

    async def _parse_free_query_intent(self, query: str) -> Dict[str, Any]:
        """解析自由模式意图（关键词/平台/时间范围）"""
        rule_intent = self._rule_parse_query(query)
        prompt = (
            "请从用户问题中抽取结构化信息，输出JSON：\n\n"
            f"用户问题：{query}\n\n"
            "请输出JSON，字段含义：\n"
            "- keywords: 关键词数组\n"
            "- platforms: 平台英文代码数组（可选：weibo, zhihu, toutiao, sina, netease, baidu, hupu, douyin, xiaohongshu, tencent）\n"
            "- time_range: {\"start\": \"YYYY-MM-DD\"|null, \"end\": \"YYYY-MM-DD\"|null}\n"
            "- intent: 概括用户需求（overview|timeline|latest|cause|impact|other）\n\n"
            "注意：只输出JSON，不要输出其他内容。\n"
        )
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
                response_format="json",
            )
            content = response.get("content", "") if isinstance(response, dict) else str(response)
            parsed = self._extract_json(content)
            if not isinstance(parsed, dict):
                return rule_intent
            return self._merge_intent(rule_intent, parsed)
        except Exception:
            return rule_intent

    def _merge_intent(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        if isinstance(override.get("keywords"), list) and override.get("keywords"):
            result["keywords"] = [str(k) for k in override.get("keywords") if str(k).strip()]
        if isinstance(override.get("platforms"), list) and override.get("platforms"):
            result["platforms"] = [str(p) for p in override.get("platforms") if str(p).strip()]
        if isinstance(override.get("time_range"), dict):
            result["time_range"] = {
                "start": override.get("time_range", {}).get("start")
                or base.get("time_range", {}).get("start"),
                "end": override.get("time_range", {}).get("end")
                or base.get("time_range", {}).get("end"),
            }
        if override.get("intent"):
            result["intent"] = override.get("intent")
        return result

    def _extract_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
        return None

    def _rule_parse_query(self, query: str) -> Dict[str, Any]:
        intent = {
            "keywords": [],
            "platforms": [],
            "time_range": {"start": None, "end": None},
            "intent": "overview",
        }
        # 平台识别
        for alias, platform in self.platform_aliases.items():
            if alias in query:
                intent["platforms"].append(platform)
        intent["platforms"] = list(dict.fromkeys(intent["platforms"]))

        # 日期识别（显式日期）
        date_matches = re.findall(r"(\d{4})[\-/年](\d{1,2})[\-/月](\d{1,2})", query)
        if date_matches:
            dates = []
            for y, m, d in date_matches:
                try:
                    dates.append(date(int(y), int(m), int(d)))
                except Exception:
                    continue
            if dates:
                dates.sort()
                intent["time_range"] = {
                    "start": dates[0].isoformat(),
                    "end": dates[-1].isoformat(),
                }

        # 相对时间
        if intent["time_range"]["start"] is None:
            today = now_cn().date()
            if "今天" in query:
                intent["time_range"] = {"start": today.isoformat(), "end": today.isoformat()}
            elif "昨天" in query or "昨日" in query:
                day = today - timedelta(days=1)
                intent["time_range"] = {"start": day.isoformat(), "end": day.isoformat()}
            elif "前天" in query:
                day = today - timedelta(days=2)
                intent["time_range"] = {"start": day.isoformat(), "end": day.isoformat()}
            elif re.search(r"近(\d+)天|最近(\d+)天|过去(\d+)天", query):
                days = [int(x) for x in re.findall(r"(\d+)", query) if x.isdigit()]
                if days:
                    delta = max(1, min(days[0], 365))
                    start = today - timedelta(days=delta - 1)
                    intent["time_range"] = {"start": start.isoformat(), "end": today.isoformat()}
            elif "近一周" in query or "最近一周" in query or "过去7天" in query or "近7天" in query:
                start = today - timedelta(days=6)
                intent["time_range"] = {"start": start.isoformat(), "end": today.isoformat()}
            elif "近两周" in query or "最近两周" in query or "过去14天" in query:
                start = today - timedelta(days=13)
                intent["time_range"] = {"start": start.isoformat(), "end": today.isoformat()}
            elif "近一个月" in query or "最近一个月" in query or "过去30天" in query or "近30天" in query:
                start = today - timedelta(days=29)
                intent["time_range"] = {"start": start.isoformat(), "end": today.isoformat()}
            elif "本周" in query:
                start = today - timedelta(days=today.weekday())
                intent["time_range"] = {"start": start.isoformat(), "end": today.isoformat()}
            elif "上周" in query:
                start = today - timedelta(days=today.weekday() + 7)
                end = start + timedelta(days=6)
                intent["time_range"] = {"start": start.isoformat(), "end": end.isoformat()}

        # 关键词兜底
        if not intent["keywords"]:
            intent["keywords"] = self._extract_query_keywords(query)

        return intent

    async def _apply_intent_filters(
        self,
        db: AsyncSession,
        topics: List[Topic],
        intent: Dict[str, Any]
    ) -> List[Topic]:
        filtered = topics
        time_range = intent.get("time_range") or {}
        start = self._parse_date_string(time_range.get("start"))
        end = self._parse_date_string(time_range.get("end"), end_of_day=True)
        if start or end:
            filtered = [t for t in filtered if self._topic_in_range(t, start, end)]

        platforms = intent.get("platforms") or []
        platforms = [p for p in platforms if isinstance(p, str) and p]
        if platforms:
            filtered = await self._filter_topics_by_platform(db, filtered, platforms)

        return filtered

    def _topic_in_range(self, topic: Topic, start: Optional[datetime], end: Optional[datetime]) -> bool:
        if not topic.first_seen or not topic.last_active:
            return False
        if start and topic.last_active < start:
            return False
        if end and topic.first_seen > end:
            return False
        return True

    def _parse_date_string(self, value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                return dt.replace(hour=23, minute=59, second=59)
            return dt
        except Exception:
            return None

    async def _filter_topics_by_platform(
        self,
        db: AsyncSession,
        topics: List[Topic],
        platforms: List[str]
    ) -> List[Topic]:
        if not topics:
            return []
        topic_ids = [t.id for t in topics]
        stmt = (
            select(Topic.id)
            .join(TopicNode, Topic.id == TopicNode.topic_id)
            .join(SourceItem, TopicNode.source_item_id == SourceItem.id)
            .where(Topic.id.in_(topic_ids), SourceItem.platform.in_(platforms))
            .group_by(Topic.id)
        )
        result = await db.execute(stmt)
        matched_ids = {row[0] for row in result.all()}
        return [t for t in topics if t.id in matched_ids]

    def _rerank_topics_by_keywords(self, topics: List[Topic], keywords: List[str]) -> Tuple[List[Topic], int]:
        if not keywords:
            return topics, 0
        scored = []
        max_score = 0
        for topic in topics:
            score = 0
            title = topic.title_key or ""
            for kw in keywords:
                if kw and kw in title:
                    score += 1
            scored.append((score, topic))
            if score > max_score:
                max_score = score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored], max_score

    def _extract_query_keywords(self, query: str) -> List[str]:
        if not query:
            return []
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", query)
        for sw in self.query_stopwords:
            if sw:
                normalized = normalized.replace(sw, " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()

        keywords: List[str] = []
        # 英文/数字
        keywords.extend(re.findall(r"[A-Za-z0-9]+", normalized))
        # 中文片段
        for seg in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            if seg in self.query_stopwords:
                continue
            if len(seg) <= 4:
                keywords.append(seg)
            else:
                grams = []
                for n in (4, 3, 2):
                    for i in range(0, len(seg) - n + 1):
                        grams.append(seg[i:i + n])
                keywords.extend(grams)

        deduped: List[str] = []
        seen = set()
        for token in keywords:
            if not token or token in self.query_stopwords:
                continue
            if token in seen:
                continue
            if len(token) < 2 and not re.match(r"[A-Za-z0-9]+", token):
                continue
            seen.add(token)
            deduped.append(token)

        if not deduped and query.strip():
            return [query.strip()]
        return deduped[:8]

    async def _get_topic_platforms(self, db: AsyncSession, topic_id: int) -> List[str]:
        stmt = (
            select(SourceItem.platform)
            .join(TopicNode, TopicNode.source_item_id == SourceItem.id)
            .where(TopicNode.topic_id == topic_id)
            .group_by(SourceItem.platform)
        )
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]

    async def _get_topic_item_urls(
        self,
        db: AsyncSession,
        topic_id: int,
        limit: int = 2
    ) -> List[str]:
        stmt = (
            select(SourceItem.url)
            .join(TopicNode, TopicNode.source_item_id == SourceItem.id)
            .where(TopicNode.topic_id == topic_id)
            .order_by(TopicNode.appended_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [row[0] for row in result.all() if row and row[0]]

    async def _fetch_topic_view_by_ids(
        self,
        db: AsyncSession,
        topic_ids: List[int],
        order_by: str = "echo_length_desc"
    ) -> List[Dict[str, Any]]:
        if not topic_ids:
            return []
        order_sql = "echo_length_hours DESC NULLS LAST"
        if order_by == "last_active_desc":
            order_sql = "last_active DESC NULLS LAST"
        elif order_by == "intensity_desc":
            order_sql = "intensity_total DESC NULLS LAST"
        elif order_by == "heat_desc":
            order_sql = "heat_normalized DESC NULLS LAST"
        sql = f"""
            WITH ranked AS (
              SELECT
                topic_id,
                title,
                summary,
                first_seen,
                last_active,
                category,
                echo_length_hours,
                intensity_total,
                heat_normalized,
                item_title,
                item_summary,
                item_url,
                item_platform,
                item_published_at,
                item_fetched_at,
                ROW_NUMBER() OVER (
                  PARTITION BY topic_id
                  ORDER BY item_published_at DESC NULLS LAST, item_fetched_at DESC NULLS LAST
                ) AS rn
              FROM topic_item_mv
              WHERE topic_id = ANY(:topic_ids)
            )
            SELECT
              topic_id,
              title,
              summary,
              first_seen,
              last_active,
              category,
              echo_length_hours,
              intensity_total,
              heat_normalized,
              item_title,
              item_summary,
              item_url,
              item_platform,
              item_published_at
            FROM ranked
            WHERE rn = 1
            ORDER BY {order_sql}
        """
        result = await db.execute(text(sql), {"topic_ids": topic_ids})
        rows = result.mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            for key, value in list(item.items()):
                if isinstance(value, datetime):
                    item[key] = value.isoformat()
                elif isinstance(value, Decimal):
                    item[key] = float(value)
            items.append(item)
        return items

    async def _search_topics_by_keywords(
        self,
        db: AsyncSession,
        keywords: List[str],
        limit: Optional[int] = 10,
        recent_days: Optional[int] = None,
        match_all: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Topic]:
        if not keywords:
            return []
        from sqlalchemy import or_, and_
        from datetime import timedelta

        since = None
        if isinstance(recent_days, int) and recent_days > 0:
            since = now_cn() - timedelta(days=recent_days)
        start = start_date or since

        conditions = []
        for kw in keywords:
            if not kw:
                continue
            conditions.append(Topic.title_key.ilike(f"%{kw}%"))
        if not conditions:
            return []

        logic = and_(*conditions) if match_all else or_(*conditions)
        stmt = select(Topic).where(logic)
        if start:
            stmt = stmt.where(Topic.last_active >= start)
        if end_date:
            stmt = stmt.where(Topic.first_seen <= end_date)
        stmt = stmt.order_by(Topic.last_active.desc())
        if isinstance(limit, int) and limit > 0:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
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
            elif chunk.get("type") == "topic_overview":
                platforms = chunk.get("platforms") or []
                platform_text = " / ".join(platforms) if platforms else "未知"
                time_range = ""
                if chunk.get("first_seen") or chunk.get("last_active"):
                    time_range = f"{chunk.get('first_seen', '')} - {chunk.get('last_active', '')}"
                formatted.append(
                    f"【主题概览】{chunk.get('title', '')}\n"
                    f"时间范围: {time_range}\n"
                    f"来源平台: {platform_text}"
                    + (f"\n摘要: {chunk.get('summary', '')}" if chunk.get('summary') else "")
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
0. 不需要思考过程，不要输出<think>标签，只输出最终答案
1. 基于提供的参考内容回答，不要编造信息
2. 如果参考内容不足以回答问题，明确说明
3. 回答要准确、简洁、有条理
4. 可以引用具体的来源（如"根据微博消息..."）

请回答："""
        else:
            return """请基于以下检索到的相关内容回答用户问题：

要求：
0. 不需要思考过程，不要输出<think>标签，只输出最终答案
1. 综合多个主题的信息回答
2. 如果没有找到相关内容，明确告知用户
3. 回答要准确、客观、有条理
4. 如果匹配到多个事件，请给出3-5个相关事件并对比说明
5. 可以引用具体的主题或来源

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
0. 不需要思考过程，不要输出<think>标签，只输出最终答案
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
0. 不需要思考过程，不要输出<think>标签，只输出最终答案
1. 综合多个主题的信息回答
2. 如果没有找到相关内容，明确告知用户
3. 回答要准确、客观、有条理
4. 如果匹配到多个事件，请给出3-5个相关事件并对比说明
5. 可以引用具体的主题或来源

请回答：
"""
        
        return prompt
    
    def _parse_answer(self, response: str) -> str:
        """解析LLM回答"""
        # 简单处理，直接返回response
        return response.strip()

    def _strip_think_blocks(self, text: str) -> str:
        """移除<think>...</think>内容"""
        if not text:
            return text
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    def _filter_think_stream(self, chunk: str, suppress: bool, buffer: str) -> Tuple[str, bool, str]:
        """流式过滤<think>标签内容"""
        buffer = buffer + chunk
        output = []
        i = 0
        start_tag = "<think>"
        end_tag = "</think>"

        while i < len(buffer):
            if not suppress:
                idx = buffer.find(start_tag, i)
                if idx == -1:
                    tail = self._partial_tag_tail(buffer[i:], start_tag)
                    if tail:
                        output.append(buffer[i:len(buffer) - len(tail)])
                        buffer = tail
                    else:
                        output.append(buffer[i:])
                        buffer = ""
                    return "".join(output), suppress, buffer
                output.append(buffer[i:idx])
                i = idx + len(start_tag)
                suppress = True
            else:
                idx = buffer.find(end_tag, i)
                if idx == -1:
                    tail = self._partial_tag_tail(buffer[i:], end_tag)
                    buffer = tail
                    return "".join(output), suppress, buffer
                i = idx + len(end_tag)
                suppress = False

        buffer = ""
        return "".join(output), suppress, buffer

    def _partial_tag_tail(self, text: str, tag: str) -> str:
        max_len = min(len(text), len(tag) - 1)
        for length in range(max_len, 0, -1):
            if text.endswith(tag[:length]):
                return text[-length:]
        return ""
    
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
