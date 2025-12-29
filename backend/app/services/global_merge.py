"""
【归并阶段二】整体归并服务

⚠️ 命名说明：
- 本文件名为 global_merge.py，功能是【归并阶段二：整体归并】
- "global" 指的是与历史Topic全局库进行比对归并
- 核心功能：决策新事件是归入已有主题，还是创建新主题

【归并总体流程】
每日执行2次完整归并（上半日 12:15-12:30，下半日 22:15-22:30）：
  ┌─────────────────────────────────────────────────────────────┐
  │ 阶段一：新事件归并（halfday_merge.py，12:15/22:15）         │
  │ - 对新爬取数据去噪                                           │
  │ - 输出：pending_global_merge                                │
  └─────────────────────────────────────────────────────────────┘
                             ↓
  ┌─────────────────────────────────────────────────────────────┐
  │ 阶段二：整体归并（本模块，12:30/22:30）                      │
  │ - 与最近7天Topic比对（向量检索 + LLM判定）                   │
  │ - 决策：merge（追加到已有Topic）or new（创建新Topic）       │
  │ - 更新热度、分类、摘要                                       │
  │ - 输出：更新Topics表 + TopicNodes + 前端数据更新            │
  └─────────────────────────────────────────────────────────────┘

【本模块功能】阶段二：整体归并
- 输入：status=pending_global_merge 且 period 匹配的数据
- 处理：向量检索近7天Topics → LLM关联判定 → merge or new
- 输出：
  * Topics 表：新建或更新主题
  * TopicNodes 表：记录主题节点
  * TopicPeriodHeat 表：记录半日热度
  * SourceItems：status 更新为 merged
  * 前端数据：通过 API 轮询获取最新 Topics

【性能优化策略】
1. 批量处理：每次最多处理 50 个新事件组
2. 向量检索限制：每个事件最多召回 Top-10 候选 Topics
3. LLM 限流：批量判定时分批处理
4. Token 管理：智能截断，控制在 Qwen3-32B 的 32k 限制内
5. 超时控制：单个归并任务最长执行 15 分钟
6. 资源监控：记录每次归并的耗时和资源使用
"""
import json
import uuid
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from app.utils.timezone import now_cn
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
import numpy as np

from app.config import settings
from app.models import (
    SourceItem, Topic, TopicNode, TopicPeriodHeat, 
    LLMJudgement, RunPipeline, Summary
)
from app.services.llm import get_llm_provider, get_embedding_provider
from app.services.classification_service import ClassificationService
from app.services.summary_service import SummaryService
from app.services.vector_service import get_vector_service
from app.utils.token_manager import get_token_manager

logger = logging.getLogger(__name__)


class GlobalMergeService:
    """
    【归并阶段二】整体归并服务
    
    ⚠️ 类名说明：GlobalMergeService 表示与全局Topic库进行归并
    
    职责：
    - 将阶段一输出的验证事件与历史主题库比对
    - 通过向量检索 + LLM判定，决策是归入已有主题还是创建新主题
    - 更新 Topics、TopicNodes、TopicPeriodHeat 等表
    - 触发前端数据更新（通过数据库更新，前端轮询API获取）
    
    输入：status=pending_global_merge 且 period 匹配的数据
    输出：
    - Topics 表：新建或更新主题
    - TopicNodes 表：记录主题-源数据关联
    - TopicPeriodHeat 表：记录半日热度快照
    - SourceItems：status 更新为 merged
    
    性能优化：
    - 批量处理（MAX_BATCH_SIZE = 50）
    - 向量检索限制（TOP_K_CANDIDATES = 10）
    - LLM 批量判定分批处理
    - Token 管理和超时控制
    """
    
    # 性能优化配置
    MAX_BATCH_SIZE = 200  # 每次最多处理200个新事件组（优化提升4x）
    MAX_TIMEOUT_SECONDS = 900  # 15分钟超时
    
    def __init__(self, db: AsyncSession):
        """
        初始化服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
        self.llm_provider = get_llm_provider()
        self.embedding_provider = get_embedding_provider()
        self.classification_service = ClassificationService()
        self.summary_service = SummaryService()
        self.token_manager = get_token_manager(model=settings.qwen_model)
        # Token 限制：整体归并上下文包含候选主题信息
        self.max_prompt_tokens = 2500  # 输入上下文最大 token
        self.max_completion_tokens = 300  # 判定结果最大 token
        self.max_candidate_summary_tokens = 200  # 每个候选主题摘要最大 token
    
    async def _ensure_summary_vector(self, topic: Topic, representative: SourceItem):
        """
        确保 Topic 具备可检索的摘要向量
        - 若已有摘要但无向量，则重写向量
        - 若无摘要，则创建占位摘要（用标题+摘要），并写向量
        """
        vector_service = get_vector_service()
        try:
            # 已有摘要，检查向量
            if topic.summary_id:
                vec = vector_service.get_embedding("topic_summary", int(topic.summary_id))
                if vec is not None:
                    return
                # 重写向量
                stmt = select(Summary).where(Summary.id == topic.summary_id)
                result = await self.db.execute(stmt)
                summary = result.scalar_one_or_none()
                if summary:
                    await self.summary_service._generate_summary_embedding(self.db, summary)  # type: ignore
                    return
            
            # 没有摘要，创建占位摘要（带向量）
            await self.summary_service._create_placeholder_summary(self.db, topic)  # type: ignore
            
        except Exception as e:
            logger.warning(f\"确保摘要向量失败 (Topic {topic.id}): {e}\")
    
    async def run_global_merge(self, period: str) -> Dict[str, Any]:
        """
        执行整体归并（阶段二）
        
        将新事件归并的结果与历史主题库比对，关联演进或创建新主题
        
        性能优化：
        - 批量处理：每次最多处理 MAX_BATCH_SIZE 个新事件组
        - 资源监控：记录耗时和处理数量
        """
        print(f"🌍 开始整体归并（阶段二）: {period}")
        start_time = now_cn()
        # 创建运行记录
        run_id = f"global_merge_{uuid.uuid4().hex[:12]}"
        run_record = RunPipeline(
            run_id=run_id,
            stage="global_merge",
            status="running",
            started_at=start_time
        )
        self.db.add(run_record)
        await self.db.commit()
        try:
            # 1. 获取半日归并后保留的事件
            merge_groups = await self._get_pending_merge_groups(period)
            if not merge_groups:
                run_record.status = "success"
                run_record.ended_at = now_cn()
                run_record.duration_ms = int((run_record.ended_at - start_time).total_seconds() * 1000)
                run_record.input_count = 0
                run_record.output_count = 0
                run_record.success_count = 0
                run_record.results = {
                    "status": "no_data",
                    "period": period,
                    "input_events": 0
                }
                await self.db.commit()
                return {
                    "status": "no_data",
                    "period": period,
                    "input_events": 0
                }
            total_groups = len(merge_groups)
            print(f"📊 待归并事件组: {total_groups} 个")
            if total_groups > self.MAX_BATCH_SIZE:
                print(
                    f"⚠️  事件组数量({total_groups})超过批量处理限制({self.MAX_BATCH_SIZE})，"
                    f"将只处理前 {self.MAX_BATCH_SIZE} 个"
                )
                merge_groups = merge_groups[:self.MAX_BATCH_SIZE]
            merge_count = 0
            new_count = 0
            new_topics = []
            CONCURRENT_BATCH_SIZE = 1  # 串行，避免会话冲突
            print(f"🚀 开始处理（每批{CONCURRENT_BATCH_SIZE}个）...")
            for i in range(0, len(merge_groups), CONCURRENT_BATCH_SIZE):
                batch = merge_groups[i:i + CONCURRENT_BATCH_SIZE]
                batch_start = now_cn()
                results = await asyncio.gather(
                    *[self._process_event_group(group, period) for group in batch],
                    return_exceptions=True
                )
                for idx, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"  ❌ Group {i + idx} 处理失败: {result}")
                        continue
                    if result.get("action") == "merge":
                        merge_count += 1
                    elif result.get("action") == "new":
                        new_count += 1
                        if "topic" in result:
                            new_topics.append(result["topic"])
                batch_duration = (now_cn() - batch_start).total_seconds()
                print(f"  ✅ 批次 {i//CONCURRENT_BATCH_SIZE + 1}/{(len(merge_groups)-1)//CONCURRENT_BATCH_SIZE + 1} 完成 "
                      f"({len(batch)}个group, 耗时{batch_duration:.2f}秒)")
            if new_topics:
                print(f"\\n📝 开始批量生成摘要（{len(new_topics)}个新Topic）...")
                await self._batch_generate_summaries(new_topics)
            end_time = now_cn()
            duration_seconds = (end_time - start_time).total_seconds()
            print(f"✅ 归并完成: merge={merge_count}, new={new_count}, 耗时={duration_seconds:.2f}秒")
            merge_stats = {
                "status": "success",
                "period": period,
                "total_groups": total_groups,
                "processed_groups": len(merge_groups),
                "merge_count": merge_count,
                "new_count": new_count,
                "merge_rate": merge_count / len(merge_groups) if merge_groups else 0,
                "duration_seconds": duration_seconds,
                "avg_seconds_per_group": duration_seconds / len(merge_groups) if merge_groups else 0
            }
            try:
                from app.services.frontend_update_service import update_frontend_after_merge
                await update_frontend_after_merge(self.db, period, merge_stats)
            except Exception as e:
                print(f"  ⚠️  前端数据更新失败（不影响归并）: {e}")
            run_record.status = "success"
            run_record.ended_at = end_time
            run_record.duration_ms = int(duration_seconds * 1000)
            run_record.input_count = total_groups
            run_record.output_count = merge_count + new_count
            run_record.success_count = merge_count + new_count
            run_record.results = merge_stats
            await self.db.commit()
            return merge_stats
        except Exception as e:
            run_record.status = "failed"
            run_record.ended_at = now_cn()
            run_record.duration_ms = int((run_record.ended_at - start_time).total_seconds() * 1000)
            run_record.error_summary = str(e)
            await self.db.commit()
            raise
    async def _get_pending_merge_groups(self, period: str) -> List[Dict[str, Any]]:
        """获取待整体归并的事件组"""
        stmt = select(SourceItem).where(
            and_(
                SourceItem.period == period,
                SourceItem.merge_status == "pending_global_merge"
            )
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()
        
        if not items:
            return []
        
        # 按归并组分组
        groups_dict = {}
        for item in items:
            group_id = item.period_merge_group_id
            if group_id not in groups_dict:
                groups_dict[group_id] = []
            groups_dict[group_id].append(item)
        
        # 转换为列表
        groups = [
            {
                "group_id": group_id,
                "items": items_list,
                "representative": items_list[0]  # 使用第一个作为代表
            }
            for group_id, items_list in groups_dict.items()
        ]
        
        return groups
    
    async def _process_event_group(
        self,
        event_group: Dict[str, Any],
        period: str
    ) -> Dict[str, Any]:
        """
        处理单个事件组
        
        Returns:
            决策结果 {"action": "merge"|"new", "target_topic_id": ...}
        """
        representative = event_group["representative"]
        items = event_group["items"]
        
        # 1. 向量检索候选 Topics
        candidates = await self._retrieve_candidate_topics(representative)
        
        if not candidates:
            # 无候选，直接创建新 Topic
            topic = await self._create_new_topic(event_group, period)
            return {"action": "new", "target_topic_id": topic.id, "topic": topic}
        
        # 2. LLM 关联判定
        decision = await self._llm_judge_relation(representative, candidates, period)
        
        if decision["action"] == "merge":
            # 归并到已有 Topic
            # 确保topic_id是整数类型（LLM可能返回字符串或其他格式）
            try:
                if isinstance(decision["target_topic_id"], str):
                    # 尝试从字符串中提取数字（处理"候选主题 1"这样的情况）
                    import re
                    match = re.search(r'\d+', decision["target_topic_id"])
                    if match:
                        topic_id = int(match.group())
                    else:
                        topic_id = int(decision["target_topic_id"])
                else:
                    topic_id = int(decision["target_topic_id"])
                
                await self._merge_to_topic(
                    topic_id,
                    event_group,
                    period
                )
                return {"action": "merge", "target_topic_id": topic_id}
            except (ValueError, TypeError) as e:
                print(f"  ⚠️  无法解析topic_id: {decision.get('target_topic_id')}, 错误: {e}")
                print(f"  ⚠️  改为创建新Topic")
                # 解析失败，降级为创建新Topic
                topic = await self._create_new_topic(event_group, period)
                return {"action": "new", "target_topic_id": topic.id, "topic": topic}
        else:
            # 创建新 Topic
            topic = await self._create_new_topic(event_group, period)
            return {"action": "new", "target_topic_id": topic.id, "topic": topic}
    
    async def _retrieve_candidate_topics(
        self,
        item: SourceItem,
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        向量检索候选 Topics（优化版：使用Summary向量）
        
        【性能优化】
        1. 直接检索topic_summary向量（质量更高，数量更少）
        2. 每个事件最多召回 Top-K 候选 Topics（默认3个，最多3个）
        3. 只与最近7天的Topic比对，避免与过时事件关联
        4. 相似度阈值过滤（≥0.5），过滤明显不相关的候选
        
        Args:
            item: 代表性数据项
            top_k: 返回数量（默认使用配置，最多3个）
            
        Returns:
            候选 Topics 列表（相似度由高到低，最多3个）
        """
        top_k = top_k or settings.global_merge_topk_candidates
        
        # 确保不超过3个候选（性能优化+成本控制）
        top_k = min(top_k, 3)
        
        # 计算时间窗口（默认半年内）
        from datetime import timedelta
        active_since = now_cn() - timedelta(days=180)
        
        # 获取 item 的向量（Chroma）
        vector_service = get_vector_service()
        item_vector = vector_service.get_embedding("source_item", int(item.id))
        if item_vector is None or len(item_vector) == 0:
            return []
        # 确保使用 Python list，避免 numpy array 布尔判断歧义
        if not isinstance(item_vector, list):
            item_vector = list(item_vector)
        
        # 尝试使用Chroma进行向量搜索
        candidates = []
        
        if vector_service.db_type == "chroma":
            try:
                # 【优化】直接搜索topic_summary向量，而非source_item向量
                ids, distances, metadatas = vector_service.search_similar(
                    query_embedding=item_vector,
                    top_k=top_k * 2,  # 多召回一些，然后时间过滤
                    where={"object_type": "topic_summary"}  # 搜索Summary向量
                )
                
                if ids:
                    seen_topics = set()
                    for id_str, distance, metadata in zip(ids, distances, metadatas):
                        similarity = 1 - distance  # 距离转相似度
                        
                        # 【优化】相似度阈值过滤
                        if similarity < settings.global_merge_similarity_threshold:
                            continue  # 跳过相似度过低的候选
                        
                        # 从metadata直接获取topic_id（无需查询TopicNode）
                        topic_id = metadata.get("topic_id")
                        if not topic_id or topic_id in seen_topics:
                            continue
                        
                        # 查询Topic（只检索最近7天的活跃Topic）
                        stmt = select(Topic).where(
                            and_(
                                Topic.id == topic_id,
                                Topic.status == "active",
                                Topic.last_active >= active_since  # 时间过滤
                            )
                        )
                        result = await self.db.execute(stmt)
                        topic = result.scalar_one_or_none()
                        
                        if topic:
                            seen_topics.add(topic.id)
                            candidates.append({
                                "topic_id": topic.id,
                                "title": topic.title_key,
                                "last_active": topic.last_active,
                                "length_hours": (topic.last_active - topic.first_seen).total_seconds() / 3600,
                                "similarity": similarity
                            })
                            
                            if len(candidates) >= top_k:
                                break
                    
                    if candidates:
                        print(f"✅ 使用Summary向量检索到 {len(candidates)} 个候选Topics（相似度 ≥ {settings.global_merge_similarity_threshold}）")
                        return candidates
                        
            except Exception as e:
                print(f"⚠️  Summary向量搜索失败，回退到简单查询: {e}")
        
        # 回退方案：获取最近活跃的topics（只检索最近7天的）
        stmt = select(Topic).where(
            and_(
                Topic.status == "active",
                Topic.last_active >= active_since  # 半年内
            )
        ).order_by(
            Topic.last_active.desc()
        ).limit(top_k)
        result = await self.db.execute(stmt)
        topics = result.scalars().all()
        
        for topic in topics:
            candidates.append({
                "topic_id": topic.id,
                "title": topic.title_key,
                "last_active": topic.last_active,
                "length_hours": (topic.last_active - topic.first_seen).total_seconds() / 3600
            })
        
        return candidates
    
    async def _llm_judge_relation(
        self,
        item: SourceItem,
        candidates: List[Dict[str, Any]],
        period: str
    ) -> Dict[str, Any]:
        """
        LLM 判定新事件与候选 Topics 的关联性
        
        Returns:
            决策 {"action": "merge"|"new", "target_topic_id": ..., "confidence": ...}
        """
        if not candidates:
            return {"action": "new", "confidence": 1.0}
        
        # 构建 Prompt（带文本截断）
        date_str, period = period.split("_")
        
        # 截断新事件的标题和摘要
        title = self.token_manager.truncate_text(item.title, max_tokens=80)
        summary = item.summary or '无'
        if summary != '无':
            summary = self.token_manager.truncate_text(summary, max_tokens=150)
        
        new_event_desc = (
            f"标题: {title}\n"
            f"摘要: {summary}\n"
            f"平台: {item.platform}\n"
            f"日期: {date_str} {period}"
        )
        
        # 截断候选主题信息
        candidates_desc = []
        for idx, cand in enumerate(candidates, 1):
            cand_title = self.token_manager.truncate_text(
                cand['title'],
                max_tokens=self.max_candidate_summary_tokens  # 每个候选最多 200 tokens
            )
            candidates_desc.append(
                f"【候选主题 {idx}】\n"
                f"主题ID: {cand['topic_id']}\n"
                f"标题: {cand_title}\n"
                f"最后活跃: {cand['last_active'].strftime('%Y-%m-%d %H:%M')}\n"
                f"持续时长: {cand['length_hours']:.1f} 小时"
            )
        
        prompt = f"""判断新事件是否为已有主题的新进展：

【新事件】
{new_event_desc}

{chr(10).join(candidates_desc)}

要求输出 JSON 格式：
{{
  "decision": "merge" 或 "new",
  "target_topic_id": 上述候选主题的真实主题ID（数字），
  "confidence": 0.0-1.0,
  "reason": "判断理由"
}}

判断标准：
1. 如果新事件是某个候选主题的后续进展、新报道，则选择 "merge"
2. 如果新事件与所有候选主题都无关，则选择 "new"
3. 时间间隔不超过7天
4. 主题一致性强
"""
        
        # Token 优化：确保 prompt 不超过限制
        prompt_tokens = self.token_manager.count_tokens(prompt)
        if prompt_tokens > self.max_prompt_tokens:
            logger.warning(
                f"整体归并 prompt 过长 ({prompt_tokens} tokens)，需要截断"
            )
            prompt = self.token_manager.truncate_text(
                prompt,
                max_tokens=self.max_prompt_tokens
            )
            logger.info(f"截断后 prompt: {self.token_manager.count_tokens(prompt)} tokens")
        
        try:
            messages = [
                {"role": "system", "content": "你是专业的新闻事件分析助手，擅长判断事件之间的关联性。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_provider.chat_completion(
                messages,
                response_format="json",
                max_tokens=self.max_completion_tokens  # 使用配置的值（300）
            )
            
            result = json.loads(response["content"])
            
            # 记录 Token 使用
            logger.info(
                f"整体归并判定完成 - Prompt: {prompt_tokens} tokens, "
                f"Completion: {response.get('usage', {}).get('completion_tokens', 0)} tokens, "
                f"决策: {result.get('decision')} (置信度: {result.get('confidence')})"
            )
            resolved_topic_id = self._resolve_llm_target_topic_id(
                result.get("target_topic_id"),
                candidates
            )
            result["resolved_topic_id"] = resolved_topic_id
            
            # 记录判定
            judgement = LLMJudgement(
                type="global_merge",
                status="success",
                request={
                    "item_id": item.id,
                    "candidates": [c["topic_id"] for c in candidates]
                },
                response=result,
                tokens_prompt=response["usage"].get("prompt_tokens"),
                tokens_completion=response["usage"].get("completion_tokens"),
                provider=self.llm_provider.get_provider_name(),
                model=self.llm_provider.model
            )
            self.db.add(judgement)
            # 先flush确保ID立即分配，避免并行冲突
            await self.db.flush()
            await self.db.commit()
            
            # 检查置信度
            if (
                result.get("decision") == "merge" 
                and result.get("confidence", 0) >= settings.global_merge_confidence_threshold
                and resolved_topic_id is not None
            ):
                return {
                    "action": "merge",
                    "target_topic_id": resolved_topic_id,
                    "confidence": result.get("confidence"),
                    "reason": result.get("reason")
                }
            else:
                return {
                    "action": "new",
                    "confidence": result.get("confidence", 0),
                    "reason": result.get("reason")
                }
            
        except Exception as e:
            print(f"❌ LLM 判定失败: {e}")
            # 失败时保守处理：创建新 Topic
            return {"action": "new", "confidence": 0.5}

    def _resolve_llm_target_topic_id(
        self,
        raw_target: Any,
        candidates: List[Dict[str, Any]]
    ) -> Optional[int]:
        """将LLM返回的target_topic_id解析为真实Topic ID"""
        if raw_target is None:
            return None
        
        candidate_ids = [cand["topic_id"] for cand in candidates]
        
        # 如果直接是整数且存在于候选ID列表，直接使用
        if isinstance(raw_target, int):
            if raw_target in candidate_ids:
                return raw_target
            # 兼容只返回序号的情况
            if 1 <= raw_target <= len(candidate_ids):
                return candidate_ids[raw_target - 1]
            return None
        
        # 如果是浮点数（LLM可能返回1.0）
        if isinstance(raw_target, float):
            raw_int = int(raw_target)
            if raw_int in candidate_ids:
                return raw_int
            if 1 <= raw_int <= len(candidate_ids):
                return candidate_ids[raw_int - 1]
            return None
        
        # 如果是字符串，尝试解析数字
        if isinstance(raw_target, str):
            raw_target = raw_target.strip()
            import re
            match = re.search(r'\d+', raw_target)
            if not match:
                return None
            value = int(match.group())
            if value in candidate_ids:
                return value
            if 1 <= value <= len(candidate_ids):
                return candidate_ids[value - 1]
            return None
        
        return None
    
    async def _create_new_topic(
        self,
        event_group: Dict[str, Any],
        period: str
    ) -> Topic:
        """创建新 Topic"""
        items = event_group["items"]
        representative = event_group["representative"]
        
        try:
            # 创建 Topic
            topic = Topic(
                title_key=representative.title,
                first_seen=min(item.fetched_at for item in items),
                last_active=max(item.fetched_at for item in items),
                status="active",
                intensity_total=len(items),
                current_heat_normalized=sum(
                    item.heat_normalized or 0 for item in items
                ) / len(items) if items else 0
            )
            self.db.add(topic)
            await self.db.flush()  # 获取 topic.id
            
            # 创建 TopicNodes
            nodes_created = 0
            for item in items:
                node = TopicNode(
                    topic_id=topic.id,
                    source_item_id=item.id,
                    appended_at=now_cn()
                )
                self.db.add(node)
                nodes_created += 1
                
                # 更新 item 状态
                item.merge_status = "merged"
            
            # 更新半日热度记录
            await self._update_topic_heat(topic, event_group, period)
            
            # 提交前flush，确保nodes被保存
            await self.db.flush()
            
            # 最终提交
            await self.db.commit()
            
            print(f"  ✨ 创建新 Topic: {topic.id} - {topic.title_key} ({nodes_created} nodes)")

            # 立即写占位摘要向量，避免同轮重复创建
            await self._ensure_summary_vector(topic, representative)
            
            # 【性能优化】分类和摘要生成延迟到批量处理
            # 异步执行分类（不等待摘要生成）
            try:
                # 刷新会话以确保能查询到刚创建的nodes
                await self.db.refresh(topic)
                
                category, confidence, method = await self.classification_service.classify_topic(
                    self.db, topic, force_llm=False
                )
                topic.category = category
                topic.category_confidence = confidence
                topic.category_method = method
                topic.category_updated_at = now_cn()
                await self.db.commit()
                print(f"  📋 完成分类: {category} (置信度: {confidence:.2f}, 方法: {method})")
            except Exception as e:
                logger.error(f"分类失败: {e}")
                print(f"  ❌ 分类失败: {e}")
                # 分类失败不影响Topic创建
                await self.db.rollback()
                await self.db.commit()  # 重新提交topic创建
            
            # 摘要生成将在批量处理中完成
            return topic
            
        except Exception as e:
            logger.error(f"创建Topic失败: {e}")
            print(f"  ❌ 创建Topic失败: {e}")
            await self.db.rollback()
            raise  # 重新抛出异常，让上层处理
    
    async def _merge_to_topic(
        self,
        topic_id: int,
        event_group: Dict[str, Any],
        period: str
    ):
        """归并到已有 Topic"""
        items = event_group["items"]
        
        # 获取 Topic
        stmt = select(Topic).where(Topic.id == topic_id)
        result = await self.db.execute(stmt)
        topic = result.scalar_one_or_none()
        
        if not topic:
            print(f"  ❌ Topic {topic_id} 不存在")
            return
        
        # 更新 Topic
        topic.last_active = max(item.fetched_at for item in items)
        topic.intensity_total += len(items)
        
        # 追加 TopicNodes
        for item in items:
            node = TopicNode(
                topic_id=topic.id,
                source_item_id=item.id,
                appended_at=now_cn()
            )
            self.db.add(node)
            
            item.merge_status = "merged"
        
        # 更新半日热度
        await self._update_topic_heat(topic, event_group, period)
        
        # 获取新增的节点用于增量摘要
        new_nodes = []
        for item in items:
            stmt = select(TopicNode).where(
                and_(
                    TopicNode.topic_id == topic.id,
                    TopicNode.source_item_id == item.id
                )
            )
            result = await self.db.execute(stmt)
            node = result.scalar_one_or_none()
            if node:
                new_nodes.append(node)
        
        await self.db.commit()
        
        print(f"  🔗 归并到 Topic: {topic.id} - {topic.title_key}")

        # 若旧Topic缺摘要向量，立即补写占位摘要向量
        await self._ensure_summary_vector(topic, items[0])
        
        # 异步执行增量摘要更新
        try:
            print(f"  📝 开始增量摘要更新... (新节点数: {len(new_nodes)})")
            updated_summary = await self.summary_service.generate_or_update_summary(
                self.db, topic, new_nodes
            )
            if updated_summary:
                print(f"  ✅ 摘要更新完成 (方法: {updated_summary.method})")
            else:
                print(f"  ℹ️  无需更新摘要")
            
        except Exception as e:
            logger.error(f"摘要更新失败: {e}")
            import traceback
            logger.error(f"完整堆栈:\n{traceback.format_exc()}")
            print(f"  ❌ 摘要更新失败: {e}")
    
    async def _update_topic_heat(
        self,
        topic: Topic,
        event_group: Dict[str, Any],
        period: str
    ):
        """更新 Topic 的半日热度记录"""
        items = event_group["items"]
        
        # 解析半日时段
        date_str, period = period.split("_")
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # 计算半日热度
        heat_normalized = sum(
            item.heat_normalized or 0 for item in items
        ) / len(items) if items else 0
        
        # 查找或创建半日热度记录
        stmt = select(TopicPeriodHeat).where(
            and_(
                TopicPeriodHeat.topic_id == topic.id,
                TopicPeriodHeat.date == date_obj,
                TopicPeriodHeat.period == period
            )
        )
        result = await self.db.execute(stmt)
        heat_record = result.scalar_one_or_none()
        
        if heat_record:
            # 更新现有记录
            heat_record.heat_normalized = heat_normalized
            heat_record.heat_percentage = heat_normalized * 100
            heat_record.source_count += len(items)
        else:
            # 创建新记录
            heat_record = TopicPeriodHeat(
                topic_id=topic.id,
                date=date_obj,
                period=period,
                heat_normalized=heat_normalized,
                heat_percentage=heat_normalized * 100,
                source_count=len(items)
            )
            self.db.add(heat_record)
        
        # 更新 Topic 的当前热度
        topic.current_heat_normalized = heat_normalized
        topic.heat_percentage = heat_normalized * 100
    
    async def _batch_generate_summaries(self, topics: List[Topic]):
        """
        批量异步生成摘要（性能优化）
        
        Args:
            topics: 待生成摘要的Topic列表
        """
        if not topics:
            return
        
        summary_start = now_cn()
        success_count = 0
        failed_count = 0
        
        # 并行生成摘要（限制并发数）
        SUMMARY_CONCURRENT_SIZE = 5  # 摘要生成并发数较少，避免LLM限流
        
        for i in range(0, len(topics), SUMMARY_CONCURRENT_SIZE):
            batch = topics[i:i + SUMMARY_CONCURRENT_SIZE]
            
            # 并行生成当前批次的摘要
            results = await asyncio.gather(
                *[self._generate_single_summary(topic) for topic in batch],
                return_exceptions=True
            )
            
            # 统计结果
            for result in results:
                if isinstance(result, Exception):
                    failed_count += 1
                elif result:
                    success_count += 1
                else:
                    failed_count += 1
        
        summary_duration = (now_cn() - summary_start).total_seconds()
        print(f"✅ 摘要批量生成完成: 成功{success_count}, 失败{failed_count}, "
              f"耗时{summary_duration:.2f}秒 (平均{summary_duration/len(topics):.2f}秒/个)")
    
    async def _generate_single_summary(self, topic: Topic) -> bool:
        """
        为单个Topic生成摘要（使用独立数据库会话避免并发冲突）
        
        Returns:
            True if successful, False otherwise
        """
        from app.core.database import get_async_session
        
        topic_id = topic.id
        
        try:
            print(f"  📝 开始生成摘要... (Topic {topic_id})")
            
            # 为每个摘要生成任务创建独立的数据库会话，避免并发冲突
            async_session_factory = get_async_session()
            async with async_session_factory() as independent_db:
                # 重新查询 topic（在独立会话中）
                stmt = select(Topic).where(Topic.id == topic_id)
                result = await independent_db.execute(stmt)
                topic_in_session = result.scalar_one_or_none()
                
                if not topic_in_session:
                    print(f"  ❌ Topic {topic_id} 不存在")
                    return False
                
                # 使用独立会话生成摘要
                summary = await self.summary_service.generate_full_summary(
                    independent_db, 
                    topic_in_session
                )
                
                if summary and summary.method == "full":
                    print(f"  ✅ 摘要生成成功 (Topic {topic_id}, 方法: {summary.method})")
                    return True
                elif summary and summary.method == "placeholder":
                    print(f"  ⚠️  创建了占位摘要 (Topic {topic_id})")
                    return False
                else:
                    print(f"  ❌ 摘要生成失败 (Topic {topic_id})")
                    return False
                
        except Exception as e:
            logger.error(f"摘要生成失败 (Topic {topic_id}): {e}")
            import traceback
            logger.error(f"完整堆栈:\n{traceback.format_exc()}")
            print(f"  ❌ 摘要生成失败 (Topic {topic_id}): {e}")
            return False
