"""
摘要生成服务

实现增量摘要生成，避免每次都对整个主题重新生成摘要
采用关键节点选择 + 增量合成的策略

优化：集成 TokenManager 以处理 qwen3-32b 的 32k 上下文限制
"""
from typing import List, Optional, Dict
from datetime import datetime
from datetime import timedelta
from app.utils.timezone import now_cn
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import json
import logging

from app.models import Summary, Topic, TopicNode, SourceItem, LLMJudgement
from app.services.llm.factory import get_llm_provider
from app.config import settings
from app.utils.token_manager import get_token_manager

logger = logging.getLogger(__name__)


class SummaryService:
    """摘要生成服务"""
    
    def __init__(self):
        self.settings = settings
        self.llm_provider = get_llm_provider()
        self.token_manager = get_token_manager(model=settings.qwen_model)
        self.min_nodes_for_update = 3  # 最少新节点数才触发更新
        self.max_context_nodes = 15  # 最多使用的节点数
        self.update_interval_hours = 6  # 更新间隔（小时）
        # Token 限制：为摘要生成预留合理的 token 预算
        self.max_prompt_tokens = 4000  # 输入上下文最大 token（考虑到摘要任务较复杂）
        self.max_completion_tokens = 1000  # 摘要最大 token
        
    async def generate_or_update_summary(
        self,
        db: AsyncSession,
        topic: Topic,
        new_nodes: Optional[List[TopicNode]] = None
    ) -> Optional[Summary]:
        """
        生成或更新主题摘要
        
        Args:
            db: 数据库会话
            topic: 主题对象
            new_nodes: 新增的节点列表（如果是增量更新）
            
        Returns:
            Summary对象，如果无需更新则返回None
        """
        # 获取当前摘要
        current_summary = await self._get_current_summary(db, topic.id)
        
        if current_summary is None:
            # 首次生成全量摘要
            return await self.generate_full_summary(db, topic)
        else:
            # 增量更新
            return await self.generate_incremental_summary(
                db, 
                topic, 
                current_summary,
                new_nodes or []
            )
    
    async def generate_full_summary(
        self,
        db: AsyncSession,
        topic: Topic
    ) -> Summary:
        """
        生成全量摘要
        
        Args:
            db: 数据库会话
            topic: 主题对象
            
        Returns:
            Summary对象
        """
        logger.info(f"🔄 开始生成全量摘要 - Topic ID: {topic.id}, 标题: {topic.title_key}")
        
        # 1. 获取所有节点
        all_nodes = await self._get_all_topic_nodes(db, topic.id)
        logger.info(f"   获取到 {len(all_nodes)} 个节点")
        
        if not all_nodes:
            # 无节点，创建占位摘要
            logger.warning(f"   ⚠️  无节点，创建占位摘要")
            return await self._create_placeholder_summary(db, topic)
        
        # 2. 选择关键节点
        key_nodes = self._select_key_nodes(all_nodes)
        logger.info(f"   选择了 {len(key_nodes)} 个关键节点")
        
        # 3. 获取主题统计信息
        stats = await self._get_topic_stats(db, topic)
        logger.info(f"   统计: {stats['node_count']} 个节点, 平台: {stats['platforms']}")
        
        # 4. 构造Prompt（带 Token 优化）
        prompt = self._build_full_prompt(topic, key_nodes, stats)
        
        # 5. Token 优化：确保 prompt 不超过限制
        prompt_tokens = self.token_manager.count_tokens(prompt)
        logger.info(f"   Prompt tokens: {prompt_tokens}")
        
        if prompt_tokens > self.max_prompt_tokens:
            logger.warning(
                f"全量摘要 prompt 过长 ({prompt_tokens} tokens)，需要截断上下文"
            )
            # 截断 prompt（保留系统提示和主题信息，压缩节点内容）
            prompt = self.token_manager.truncate_text(
                prompt, 
                max_tokens=self.max_prompt_tokens
            )
            logger.info(f"截断后 prompt: {self.token_manager.count_tokens(prompt)} tokens")
        
        # 6. 调用LLM
        logger.info(f"   📡 调用LLM生成摘要 (provider: {self.llm_provider.get_provider_name()}, model: {self.llm_provider.model})")
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=self.max_completion_tokens  # 使用配置的值（1000）
            )
            logger.info(f"   ✅ LLM调用成功")
            
            # 7. 解析响应
            summary_data = self._parse_summary_response(response)
            logger.info(f"   ✅ 响应解析成功，摘要长度: {len(summary_data.get('summary', ''))} 字")
            
            # 8. 记录 Token 使用
            completion_tokens = response.get('usage', {}).get('completion_tokens', 0) if isinstance(response, dict) else 0
            logger.info(
                f"   📊 Token统计 - Prompt: {prompt_tokens}, Completion: {completion_tokens}"
            )
            
            # 9. 保存摘要
            summary = Summary(
                topic_id=topic.id,
                content=summary_data["summary"],
                method="full",
                provider=self.llm_provider.get_provider_name(),
                model=self.llm_provider.model,
                generated_at=now_cn()
            )
            db.add(summary)
            await db.commit()
            await db.refresh(summary)
            logger.info(f"   💾 摘要已保存到数据库 (Summary ID: {summary.id})")
            
            # 10. 更新topic的summary_id
            topic.summary_id = summary.id
            await db.commit()
            logger.info(f"   🔗 已关联到Topic")
            
            # 11. 记录判定任务
            await self._record_judgement(
                db,
                topic_id=topic.id,
                type="summarize_full",
                prompt=prompt,
                response=response,
                summary_data=summary_data
            )
            
            logger.info(f"✅ 全量摘要生成完成 - Topic ID: {topic.id}")
            return summary
            
        except Exception as e:
            logger.error(f"全量摘要生成失败 - Topic ID: {topic.id}, 标题: {topic.title_key}")
            logger.error(f"错误信息: {e}")
            import traceback
            logger.error(f"完整堆栈:\n{traceback.format_exc()}")
            print(f"❌ 全量摘要生成失败 (Topic {topic.id}): {e}")
            return await self._create_placeholder_summary(db, topic)
    
    async def generate_incremental_summary(
        self,
        db: AsyncSession,
        topic: Topic,
        current_summary: Summary,
        new_nodes: List[TopicNode]
    ) -> Optional[Summary]:
        """
        生成增量摘要
        
        Args:
            db: 数据库会话
            topic: 主题对象
            current_summary: 当前摘要
            new_nodes: 新增节点列表
            
        Returns:
            新的Summary对象，如果无需更新则返回None
        """
        # 1. 检查是否需要更新
        if not await self._should_update(current_summary, new_nodes):
            return None
        
        # 2. 压缩新节点（如果太多）
        compressed_nodes = self._compress_new_nodes(new_nodes)
        
        # 3. 构造增量Prompt（带 Token 优化）
        prompt = self._build_incremental_prompt(
            topic,
            current_summary.content,
            compressed_nodes
        )
        
        # 4. Token 优化：确保 prompt 不超过限制
        prompt_tokens = self.token_manager.count_tokens(prompt)
        if prompt_tokens > self.max_prompt_tokens:
            logger.warning(
                f"增量摘要 prompt 过长 ({prompt_tokens} tokens)，需要截断"
            )
            # 截断 prompt（优先保留当前摘要和新节点摘要）
            prompt = self.token_manager.truncate_text(
                prompt,
                max_tokens=self.max_prompt_tokens
            )
            logger.info(f"截断后 prompt: {self.token_manager.count_tokens(prompt)} tokens")
        
        # 5. 调用LLM
        try:
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=self.max_completion_tokens  # 使用配置的值（1000）
            )
            
            # 6. 解析响应
            update_data = self._parse_incremental_response(response)
            
            # 7. 记录 Token 使用
            logger.info(
                f"增量摘要生成完成 - Prompt: {prompt_tokens} tokens, "
                f"Completion: {response.get('usage', {}).get('completion_tokens', 0)} tokens"
            )
            
            # 8. 如果LLM判断不需要更新
            if not update_data.get("needs_update", True):
                return None
            
            # 9. 保存新摘要
            summary = Summary(
                topic_id=topic.id,
                content=update_data["updated_summary"],
                method="incremental",
                provider=self.llm_provider.get_provider_name(),
                model=self.llm_provider.model,
                generated_at=now_cn()
            )
            db.add(summary)
            await db.commit()
            await db.refresh(summary)
            
            # 10. 更新topic的summary_id
            topic.summary_id = summary.id
            await db.commit()
            
            # 11. 记录判定任务
            await self._record_judgement(
                db,
                topic_id=topic.id,
                type="summarize_incremental",
                prompt=prompt,
                response=response,
                summary_data=update_data
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"增量摘要生成失败 - Topic ID: {topic.id}, 标题: {topic.title_key}")
            logger.error(f"错误信息: {e}")
            import traceback
            logger.error(f"完整堆栈:\n{traceback.format_exc()}")
            print(f"❌ 增量摘要生成失败 (Topic {topic.id}): {e}")
            return None
    
    def _select_key_nodes(self, nodes: List[TopicNode]) -> List[TopicNode]:
        """
        选择关键节点以压缩上下文
        
        策略：首条 + 峰值（互动最高）+ 最新
        """
        if not nodes:
            return []
        
        key_nodes = []
        seen_ids = set()
        
        # 1. 首条节点（事件起因）
        first_node = min(nodes, key=lambda n: n.appended_at)
        key_nodes.append(first_node)
        seen_ids.add(first_node.id)
        
        # 2. 峰值节点（互动量最高的前2条）
        nodes_with_interactions = [
            n for n in nodes 
            if n.source_item and n.source_item.interactions
        ]
        
        if nodes_with_interactions:
            sorted_by_interactions = sorted(
                nodes_with_interactions,
                key=lambda n: self._get_total_interactions(n),
                reverse=True
            )
            
            for node in sorted_by_interactions[:2]:
                if node.id not in seen_ids:
                    key_nodes.append(node)
                    seen_ids.add(node.id)
        
        # 3. 最新节点（最近的5条）
        latest_nodes = sorted(nodes, key=lambda n: n.appended_at, reverse=True)[:5]
        for node in latest_nodes:
            if node.id not in seen_ids:
                key_nodes.append(node)
                seen_ids.add(node.id)
        
        # 按时间排序
        key_nodes.sort(key=lambda n: n.appended_at)
        
        # 限制总数
        return key_nodes[:self.max_context_nodes]
    
    def _compress_new_nodes(self, nodes: List[TopicNode]) -> List[TopicNode]:
        """压缩新节点列表"""
        if len(nodes) <= 5:
            return nodes
        
        # 保留最新的5条
        return sorted(nodes, key=lambda n: n.appended_at, reverse=True)[:5]
    
    def _build_full_prompt(
        self, 
        topic: Topic, 
        key_nodes: List[TopicNode],
        stats: Dict
    ) -> str:
        """构造全量摘要Prompt"""
        nodes_text = []
        for i, node in enumerate(key_nodes, 1):
            if node.source_item:
                # 使用published_at，如果为None则使用fetched_at
                pub_time = node.source_item.published_at or node.source_item.fetched_at
                time_str = pub_time.strftime("%Y-%m-%d %H:%M") if pub_time else "未知时间"
                nodes_text.append(
                    f"{i}. [{node.source_item.platform}] {time_str}\n"
                    f"   标题: {node.source_item.title}"
                )
                if node.source_item.summary:
                    nodes_text.append(f"   摘要: {node.source_item.summary[:150]}")
                
                # 互动数据
                interactions = self._format_interactions(node.source_item.interactions)
                if interactions:
                    nodes_text.append(f"   互动: {interactions}")
        
        prompt = f"""请为以下热点事件生成结构化摘要。

【事件基本信息】
- 标题: {topic.title_key}
- 首次发现: {topic.first_seen.strftime("%Y-%m-%d %H:%M") if topic.first_seen else "未知"}
- 最后活跃: {topic.last_active.strftime("%Y-%m-%d %H:%M") if topic.last_active else "未知"}
- 涉及平台: {stats['platforms']}
- 节点总数: {stats['node_count']}

【关键节点】（按时间顺序，已筛选关键信息）
{chr(10).join(nodes_text)}

要求：
1. 概述事件的核心内容（150-300字）
2. 提炼3-5个关键要点
3. 如果有重要进展，按时间顺序说明
4. 保持客观中立，不做主观评价

重要：直接返回JSON格式，不要包含任何思维过程或其他文本。
输出格式：
{{
  "summary": "事件概述（150-300字）",
  "key_points": [
    "要点1：事件起因或背景",
    "要点2：主要内容或进展",
    "要点3：当前状态或影响"
  ]
}}
"""
        return prompt
    
    def _build_incremental_prompt(
        self,
        topic: Topic,
        current_summary: str,
        new_nodes: List[TopicNode]
    ) -> str:
        """构造增量摘要Prompt"""
        new_nodes_text = []
        for i, node in enumerate(new_nodes, 1):
            if node.source_item:
                # 使用published_at，如果为None则使用fetched_at
                pub_time = node.source_item.published_at or node.source_item.fetched_at
                time_str = pub_time.strftime("%Y-%m-%d %H:%M") if pub_time else "未知时间"
                new_nodes_text.append(
                    f"{i}. [{node.source_item.platform}] {time_str}\n"
                    f"   {node.source_item.title}"
                )
                if node.source_item.summary:
                    new_nodes_text.append(f"   {node.source_item.summary[:150]}")
        
        prompt = f"""请基于当前摘要和新增进展，更新事件摘要。

【当前摘要】
{current_summary}

【新增进展】（{len(new_nodes)}条新节点）
{chr(10).join(new_nodes_text)}

请分析新增内容，判断是否需要更新摘要。

更新原则：
1. 如果新节点只是重复旧信息，保持原摘要不变
2. 如果有重要新进展或转折，更新摘要并添加新要点
3. 保持摘要简洁（150-300字）
4. 保留历史摘要的连贯性

重要：直接返回JSON格式，不要包含任何思维过程或其他文本。
输出格式：
{{
  "needs_update": true,
  "updated_summary": "更新后的摘要（如果needs_update=true）",
  "new_key_points": ["新增要点1", "新增要点2"],
  "change_reason": "说明为什么需要更新（或为什么不需要）"
}}
"""
        return prompt
    
    def _parse_summary_response(self, response) -> Dict:
        """解析摘要响应"""
        try:
            # 如果response是dict（来自LLM provider），提取content字段
            if isinstance(response, dict):
                content = response.get("content", "")
            else:
                content = response
            
            # 如果content为空，记录并使用默认值
            if not content:
                logger.error(f"LLM响应content为空: {response}")
                return {
                    "summary": "摘要生成失败：LLM返回空内容",
                    "key_points": []
                }
            
            # 处理Qwen思维链：提取<think>标签之后的内容
            content_clean = self._extract_content_from_think(content)
            
            # 尝试解析JSON
            data = json.loads(content_clean)
            
            if "summary" not in data:
                raise ValueError("Missing summary field")
            
            logger.info(f"   ✅ 成功解析JSON格式摘要")
            return data
            
        except json.JSONDecodeError as e:
            # 降级：尝试查找JSON部分
            logger.warning(f"JSON解析失败，尝试提取JSON部分: {e}")
            
            # 尝试从文本中提取JSON
            json_data = self._extract_json_from_text(content_clean if 'content_clean' in locals() else content)
            if json_data:
                logger.info(f"   ✅ 从文本中成功提取JSON")
                return json_data
            
            # 最终降级：使用原始文本作为摘要
            logger.warning(f"   ⚠️  无法提取JSON，使用原始文本")
            fallback_text = content_clean if 'content_clean' in locals() else (content if isinstance(content, str) else str(response))
            return {
                "summary": fallback_text[:500],
                "key_points": []
            }
        except Exception as e:
            logger.error(f"解析响应时出错: {e}")
            return {
                "summary": f"摘要解析失败：{str(e)}",
                "key_points": []
            }
    
    def _extract_content_from_think(self, text: str) -> str:
        """从Qwen思维链输出中提取实际内容"""
        import re
        
        # 如果包含<think>标签，提取</think>之后的内容
        if "<think>" in text.lower() or "</think>" in text.lower():
            logger.info("   检测到思维链标签，提取实际内容")
            # 使用正则表达式提取</think>之后的内容
            match = re.search(r'</think>\s*(.+)', text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                logger.info(f"   提取到内容长度: {len(content)} 字符")
                return content
            else:
                # 如果没有</think>，尝试提取<think>之前的内容
                match = re.search(r'^(.+?)<think>', text, re.DOTALL | re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                # 如果都没有，返回原文
                logger.warning("   无法提取思维链后的内容，返回原文")
                return text
        
        return text
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """从文本中提取JSON对象"""
        import re
        
        # 尝试找到JSON对象（以{开头，}结尾）
        match = re.search(r'\{[^{}]*"summary"[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                json_str = match.group(0)
                data = json.loads(json_str)
                if "summary" in data:
                    return data
            except json.JSONDecodeError:
                pass
        
        # 尝试更宽松的匹配
        match = re.search(r'\{.+\}', text, re.DOTALL)
        if match:
            try:
                json_str = match.group(0)
                data = json.loads(json_str)
                if "summary" in data:
                    return data
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _parse_incremental_response(self, response) -> Dict:
        """解析增量响应"""
        try:
            # 如果response是dict（来自LLM provider），提取content字段
            if isinstance(response, dict):
                content = response.get("content", "")
            else:
                content = response
            
            # 如果content为空，记录并使用默认值
            if not content:
                logger.error(f"LLM响应content为空: {response}")
                return {
                    "needs_update": False,
                    "updated_summary": "",
                    "new_key_points": [],
                    "change_reason": "LLM返回空内容"
                }
            
            # 处理Qwen思维链：提取<think>标签之后的内容
            content_clean = self._extract_content_from_think(content)
            
            # 尝试解析JSON
            data = json.loads(content_clean)
            
            # 设置默认值
            data.setdefault("needs_update", True)
            
            logger.info(f"   ✅ 成功解析JSON格式增量响应")
            return data
            
        except json.JSONDecodeError as e:
            # 降级：尝试查找JSON部分
            logger.warning(f"JSON解析失败，尝试提取JSON部分: {e}")
            
            # 尝试从文本中提取JSON
            json_data = self._extract_json_from_text(content_clean if 'content_clean' in locals() else content)
            if json_data:
                # 确保有needs_update字段
                json_data.setdefault("needs_update", True)
                logger.info(f"   ✅ 从文本中成功提取JSON")
                return json_data
            
            # 最终降级：使用原始文本作为摘要
            logger.warning(f"   ⚠️  无法提取JSON，使用原始文本")
            fallback_text = content_clean if 'content_clean' in locals() else (content if isinstance(content, str) else str(response))
            return {
                "needs_update": True,
                "updated_summary": fallback_text[:500],
                "new_key_points": [],
                "change_reason": "Parsed from text"
            }
        except Exception as e:
            logger.error(f"解析响应时出错: {e}")
            return {
                "needs_update": False,
                "updated_summary": f"摘要解析失败：{str(e)}",
                "new_key_points": [],
                "change_reason": f"Error: {str(e)}"
            }
    
    async def _should_update(
        self, 
        current_summary: Summary, 
        new_nodes: List[TopicNode]
    ) -> bool:
        """判断是否需要更新摘要"""
        # 1. 检查新节点数量
        if len(new_nodes) < self.min_nodes_for_update:
            return False
        
        # 2. 检查更新间隔
        time_since_last = now_cn() - current_summary.generated_at
        if time_since_last < timedelta(hours=self.update_interval_hours):
            return False
        
        return True
    
    async def _get_current_summary(
        self, 
        db: AsyncSession, 
        topic_id: int
    ) -> Optional[Summary]:
        """获取当前摘要"""
        stmt = (
            select(Summary)
            .where(Summary.topic_id == topic_id)
            .order_by(Summary.generated_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_all_topic_nodes(
        self, 
        db: AsyncSession, 
        topic_id: int
    ) -> List[TopicNode]:
        """获取主题的所有节点"""
        from sqlalchemy.orm import joinedload
        
        stmt = (
            select(TopicNode)
            .options(joinedload(TopicNode.source_item))
            .where(TopicNode.topic_id == topic_id)
            .order_by(TopicNode.appended_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_topic_stats(self, db: AsyncSession, topic: Topic) -> Dict:
        """获取主题统计信息"""
        # 统计节点数
        node_count_stmt = (
            select(func.count(TopicNode.id))
            .where(TopicNode.topic_id == topic.id)
        )
        node_count = await db.scalar(node_count_stmt) or 0
        
        # 统计平台数
        platforms_stmt = (
            select(func.array_agg(func.distinct(SourceItem.platform)))
            .select_from(TopicNode)
            .join(SourceItem)
            .where(TopicNode.topic_id == topic.id)
        )
        platforms_result = await db.scalar(platforms_stmt)
        platforms = ", ".join(platforms_result) if platforms_result else "未知"
        
        return {
            "node_count": node_count,
            "platforms": platforms
        }
    
    async def _create_placeholder_summary(
        self, 
        db: AsyncSession, 
        topic: Topic
    ) -> Summary:
        """创建占位摘要"""
        summary = Summary(
            topic_id=topic.id,
            content=f"事件「{topic.title_key}」的摘要正在生成中...",
            method="placeholder",
            provider="system",
            model="",
            generated_at=now_cn()
        )
        db.add(summary)
        await db.commit()
        await db.refresh(summary)
        
        topic.summary_id = summary.id
        await db.commit()
        
        return summary
    
    def _get_total_interactions(self, node: TopicNode) -> int:
        """计算节点的总互动量"""
        if not node.source_item or not node.source_item.interactions:
            return 0
        
        interactions = node.source_item.interactions
        total = 0
        
        for key in ["repost", "comment", "like", "view", "favorite"]:
            if key in interactions:
                total += interactions[key] or 0
        
        return total
    
    def _format_interactions(self, interactions: Optional[Dict]) -> str:
        """格式化互动数据"""
        if not interactions:
            return ""
        
        parts = []
        if interactions.get("repost"):
            parts.append(f"转发{interactions['repost']}")
        if interactions.get("comment"):
            parts.append(f"评论{interactions['comment']}")
        if interactions.get("like"):
            parts.append(f"点赞{interactions['like']}")
        
        return ", ".join(parts) if parts else ""
    
    async def _record_judgement(
        self,
        db: AsyncSession,
        topic_id: int,
        type: str,
        prompt: str,
        response: str,
        summary_data: Dict
    ):
        """记录LLM判定任务"""
        # 确保prompt是字符串类型
        prompt_str = str(prompt) if not isinstance(prompt, str) else prompt
        
        judgement = LLMJudgement(
            type=type,
            status="completed",
            request_data={
                "topic_id": topic_id,
                "prompt": prompt_str[:1000]  # 截断过长的prompt
            },
            response_data=summary_data,
            provider=self.llm_provider.get_provider_name(),
            model=self.llm_provider.model,
            latency_ms=0,  # TODO: 记录实际延迟
            tokens_prompt=0,  # TODO: 从LLM响应中获取
            tokens_completion=0
        )
        db.add(judgement)
        await db.commit()

