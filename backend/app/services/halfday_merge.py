"""
【归并阶段一】新事件归并服务

⚠️ 命名说明：
- 本文件名为 halfday_merge.py，但实际功能是【归并阶段一：新事件归并】
- "halfday" 是历史命名，指的是对半日周期内采集的数据进行归并
- 核心功能：对新采集的数据去噪、验证真实热点

【归并总体流程】
每日执行3次完整归并（上午 12:15-12:30，下午 18:15-18:30，傍晚 22:15-22:30）：
  ┌─────────────────────────────────────────────────────────────┐
  │ 阶段一：新事件归并（本模块，12:15/18:15/22:15）             │
  │ - 对新爬取数据去噪                                           │
  │ - 热度归一化（Min-Max + 平台权重）                          │
  │ - 向量聚类（相似度 > 0.85）                                 │
  │ - LLM判定（确认同组事件）                                   │
  │ - 出现次数筛选（≥2次保留，过滤单次噪音）                    │
  │ - 输出：pending_global_merge                                │
  └─────────────────────────────────────────────────────────────┘
                             ↓
  ┌─────────────────────────────────────────────────────────────┐
  │ 阶段二：整体归并（global_merge.py，12:30/18:30/22:30）      │
  │ - 与历史Topic库比对                                          │
  │ - 决策：归入已有主题 or 创建新主题                          │
  │ - 输出：更新Topics表 + 前端数据更新                         │
  └─────────────────────────────────────────────────────────────┘

【本模块功能】阶段一：新事件归并
- 输入：period 内的 pending_event_merge 数据
- 处理：去噪 + 验证真实性
- 输出：保留的真实热点事件 → pending_global_merge

优化：添加上下文长度限制以处理 qwen3-32b 的 32k 上下文限制
"""
import json
import uuid
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings
from app.models import SourceItem, Embedding, LLMJudgement, RunPipeline
from app.services.llm import get_llm_provider, get_embedding_provider
from app.services.vector_service import get_vector_service
from app.utils.token_manager import get_token_manager
from app.utils.timezone import now_cn

logger = logging.getLogger(__name__)


class EventMergeService:
    """
    【归并阶段一】新事件归并服务
    
    职责：
    - 对归并周期（AM/PM/EVE）内新采集的数据去噪、验证真实热点
    - 过滤单次出现的噪音数据（出现次数 < 2）
    - 保留经过验证的真实热点事件
    
    输入：status=pending_event_merge 且 period 匹配的数据
    输出：status=pending_global_merge（进入阶段二）或 status=discarded（噪音数据）
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
        self.llm_provider = get_llm_provider()
        self.embedding_provider = get_embedding_provider()
        self.token_manager = get_token_manager(model=settings.qwen_model)
        # Token 限制：归并任务上下文通常包含多个新闻条目
        self.max_prompt_tokens = 2000  # 输入上下文最大 token
        self.max_completion_tokens = 300  # 判定结果最大 token
        self.max_item_summary_tokens = 150  # 每个新闻摘要最大 token
    
    async def run_event_merge(self, period: str) -> Dict[str, Any]:
        """
        执行新事件归并
        
        Args:
            period: 归并周期标识（如 "2025-10-29_AM"、"2025-10-29_PM"、"2025-10-29_EVE"）
            
        Returns:
            归并结果统计
        """
        print(f"🔄 开始新事件归并: {period}")
        
        # 创建运行记录
        run_id = f"event_merge_{uuid.uuid4().hex[:12]}"
        started_at = now_cn()
        run_record = RunPipeline(
            run_id=run_id,
            stage="event_merge",
            status="running",
            started_at=started_at
        )
        self.db.add(run_record)
        await self.db.commit()
        
        try:
            # 1. 获取待归并的数据
            items = await self._get_pending_items(period)
            if not items:
                run_record.status = "success"
                run_record.ended_at = now_cn()
                run_record.duration_ms = int((run_record.ended_at - started_at).total_seconds() * 1000)
                run_record.input_count = 0
                run_record.output_count = 0
                run_record.success_count = 0
                run_record.results = {
                    "status": "no_data",
                    "period": period,
                    "input_items": 0
                }
                await self.db.commit()
                return {
                    "status": "no_data",
                    "period": period,
                    "input_items": 0
                }
            
            print(f"📊 待归并数据: {len(items)} 条")
            
            # 2. 向量化
            print("🔤 开始向量化...")
            await self._vectorize_items(items)
            
            # 3. 向量聚类
            print("🔗 开始向量聚类...")
            candidate_groups = await self._vector_clustering(items)
            print(f"📦 初步聚类: {len(candidate_groups)} 个候选组")
            
            # 4. LLM 精确判定
            print("🤖 开始 LLM 判定...")
            merge_groups = await self._llm_judge_merge(candidate_groups, period)
            print(f"✅ LLM 判定完成: {len(merge_groups)} 个归并组")
            
            # 5. 出现次数统计与筛选
            print("🔍 统计出现次数并筛选...")
            kept_items, dropped_items = await self._filter_by_occurrence(
                merge_groups,
                min_occurrence=settings.halfday_merge_min_occurrence
            )
            print(f"✅ 保留 {len(kept_items)} 条，丢弃 {len(dropped_items)} 条")
            
            # 6. 热度聚合
            await self._aggregate_heat(merge_groups)
            
            # 7. 准备返回结果
            result = {
                "status": "success",
                "period": period,
                "input_items": len(items),
                "kept_items": len(kept_items),
                "dropped_items": len(dropped_items),
                "keep_rate": len(kept_items) / len(items) if items else 0,
                "drop_rate": len(dropped_items) / len(items) if items else 0,
                "merge_groups": len(merge_groups),
                "avg_occurrence": sum(
                    len(group['items']) for group in merge_groups
                ) / len(merge_groups) if merge_groups else 0
            }
            
            # 更新运行记录
            run_record.status = "success"
            run_record.ended_at = now_cn()
            run_record.duration_ms = int((run_record.ended_at - started_at).total_seconds() * 1000)
            run_record.input_count = len(items)
            run_record.output_count = len(kept_items)
            run_record.success_count = len(kept_items)
            run_record.failed_count = len(dropped_items)
            run_record.results = result
            await self.db.commit()
            return result
        
        except Exception as e:
            # 更新运行记录为失败状态
            run_record.status = "failed"
            run_record.ended_at = now_cn()
            run_record.duration_ms = int((run_record.ended_at - started_at).total_seconds() * 1000)
            run_record.error_summary = str(e)
            await self.db.commit()
            raise
    
    async def _get_pending_items(self, period: str) -> List[SourceItem]:
        """获取待归并的数据"""
        stmt = select(SourceItem).where(
            and_(
                SourceItem.period == period,
                SourceItem.merge_status == "pending_event_merge"
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def _vectorize_items(self, items: List[SourceItem]):
        """向量化数据项"""
        # 准备文本
        texts = [
            f"{item.title} {item.summary or ''}" 
            for item in items
        ]
        
        try:
            # 批量向量化
            vectors = await self.embedding_provider.embedding(texts)
            
            # 保存向量到PostgreSQL
            embeddings_to_create = []
            for item, vector in zip(items, vectors):
                embedding = Embedding(
                    object_type="source_item",
                    object_id=item.id,
                    provider=self.embedding_provider.get_provider_name(),
                    model=self.embedding_provider.model,
                    vector=vector
                )
                self.db.add(embedding)
                embeddings_to_create.append((item, embedding))
            
            # 先提交以获取embedding的ID
            await self.db.flush()
            
            # 更新 source_item 的 embedding_id
            for item, embedding in embeddings_to_create:
                item.embedding_id = embedding.id
            
            await self.db.commit()
            
            # 同步保存到Chroma向量数据库
            try:
                vector_service = get_vector_service()
                if vector_service.db_type == "chroma":
                    ids = [f"source_item_{item.id}" for item in items]
                    metadatas = [
                        {
                            "object_type": "source_item",
                            "object_id": int(item.id),
                            "platform": item.platform,
                            "title": item.title[:200]  # 限制长度
                        }
                        for item in items
                    ]
                    documents = [f"{item.title} {item.summary or ''}"[:500] for item in items]
                    
                    vector_service.add_embeddings(
                        ids=ids,
                        embeddings=vectors,
                        metadatas=metadatas,
                        documents=documents
                    )
                    print(f"✅ 已同步 {len(vectors)} 个向量到Chroma")
            except Exception as chroma_error:
                print(f"⚠️  Chroma同步失败（不影响主流程）: {chroma_error}")
            
        except Exception as e:
            print(f"❌ 向量化失败: {e}")
            # 失败时使用模拟向量
            for item in items:
                # 使用随机向量代替（仅用于开发测试）
                mock_vector = np.random.rand(settings.embedding_dimension).tolist()
                embedding = Embedding(
                    object_type="source_item",
                    object_id=item.id,
                    provider="mock",
                    model="mock",
                    vector=mock_vector
                )
                self.db.add(embedding)
            
            await self.db.commit()
    
    async def _vector_clustering(
        self,
        items: List[SourceItem]
    ) -> List[Dict[str, Any]]:
        """
        向量聚类
        
        Returns:
            候选归并组列表
        """
        # 获取向量
        item_vectors = []
        for item in items:
            stmt = select(Embedding).where(
                and_(
                    Embedding.object_type == "source_item",
                    Embedding.object_id == item.id
                )
            ).order_by(Embedding.created_at.desc()).limit(1)
            result = await self.db.execute(stmt)
            embedding = result.scalar_one_or_none()
            
            if embedding:
                item_vectors.append((item, embedding.vector))
        
        if not item_vectors:
            return []
        
        # 计算相似度矩阵
        vectors = np.array([vec for _, vec in item_vectors])
        similarity_matrix = cosine_similarity(vectors)
        
        # 简单的贪心聚类
        threshold = settings.halfday_merge_vector_threshold
        used = set()
        groups = []
        
        for i, (item_i, _) in enumerate(item_vectors):
            if i in used:
                continue
            
            group_items = [item_i]
            group_indices = [i]
            used.add(i)
            
            for j, (item_j, _) in enumerate(item_vectors):
                if j in used or j == i:
                    continue
                
                # 检查相似度
                if similarity_matrix[i][j] >= threshold:
                    # 额外检查标题相似度
                    title_sim = self._title_jaccard(item_i.title, item_j.title)
                    if title_sim >= settings.halfday_merge_title_threshold:
                        group_items.append(item_j)
                        group_indices.append(j)
                        used.add(j)
            
            if len(group_items) > 0:
                groups.append({
                    "items": group_items,
                    "indices": group_indices
                })
        
        return groups
    
    def _title_jaccard(self, title1: str, title2: str) -> float:
        """计算标题 Jaccard 相似度（n-gram）"""
        n = 2  # 2-gram
        
        def get_ngrams(text: str, n: int) -> set:
            return set(text[i:i+n] for i in range(len(text) - n + 1))
        
        ngrams1 = get_ngrams(title1, n)
        ngrams2 = get_ngrams(title2, n)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        
        return intersection / union if union > 0 else 0.0
    
    async def _llm_judge_merge(
        self,
        candidate_groups: List[Dict[str, Any]],
        period: str
    ) -> List[Dict[str, Any]]:
        """
        LLM 判定是否为同一事件
        
        Returns:
            最终归并组列表
        """
        merge_groups = []
        
        for group in candidate_groups:
            items = group["items"]
            
            if len(items) == 1:
                # 单个项，直接保留
                group_id = f"halfday_{uuid.uuid4().hex[:8]}"
                merge_groups.append({
                    "group_id": group_id,
                    "items": items,
                    "is_same_event": True,
                    "confidence": 1.0
                })
                continue
            
            # 构建 Prompt（带文本截断）
            items_desc = []
            for idx, item in enumerate(items, 1):
                # 截断标题和摘要，防止过长
                title = self.token_manager.truncate_text(
                    item.title,
                    max_tokens=80  # 每个标题最多 80 tokens
                )
                summary = item.summary or '无'
                if summary != '无':
                    summary = self.token_manager.truncate_text(
                        summary,
                        max_tokens=self.max_item_summary_tokens  # 每个摘要最多 150 tokens
                    )
                
                items_desc.append(
                    f"[Item {idx}] 标题: {title}  "
                    f"摘要: {summary}  "
                    f"平台: {item.platform}  "
                    f"时间: {item.fetched_at.strftime('%H:%M')}"
                )
            
            prompt = f"""判断以下新闻条目是否为同一事件的不同报道（半日内采集）：

{chr(10).join(items_desc)}

要求输出 JSON 格式：
{{
  "is_same_event": true/false,
  "confidence": 0.0-1.0,
  "reason": "判断理由"
}}
"""
            
            # Token 优化：确保 prompt 不超过限制
            prompt_tokens = self.token_manager.count_tokens(prompt)
            if prompt_tokens > self.max_prompt_tokens:
                logger.warning(
                    f"半日归并 prompt 过长 ({prompt_tokens} tokens)，需要截断"
                )
                prompt = self.token_manager.truncate_text(
                    prompt,
                    max_tokens=self.max_prompt_tokens
                )
                logger.info(f"截断后 prompt: {self.token_manager.count_tokens(prompt)} tokens")
            
            try:
                # 调用 LLM
                messages = [
                    {"role": "system", "content": "你是专业的新闻事件分析助手，擅长判断不同新闻是否报道同一事件。"},
                    {"role": "user", "content": prompt}
                ]
                
                response = await self.llm_provider.chat_completion(
                    messages,
                    response_format="json",
                    max_tokens=self.max_completion_tokens  # 使用配置的值（300）
                )
                
                # 解析结果
                result = json.loads(response["content"])
                
                # 记录 Token 使用
                logger.info(
                    f"半日归并判定完成 - Prompt: {prompt_tokens} tokens, "
                    f"Completion: {response.get('usage', {}).get('completion_tokens', 0)} tokens, "
                    f"结果: {result.get('is_same_event')} (置信度: {result.get('confidence')})"
                )
                
                # 记录判定结果
                judgement = LLMJudgement(
                    type="halfday_merge",
                    status="success",
                    request={"items": [{"id": item.id, "title": item.title} for item in items]},
                    response=result,
                    latency_ms=0,  # TODO: 记录实际延迟
                    tokens_prompt=response["usage"].get("prompt_tokens"),
                    tokens_completion=response["usage"].get("completion_tokens"),
                    provider=self.llm_provider.get_provider_name(),
                    model=self.llm_provider.model
                )
                self.db.add(judgement)
                # 先flush确保ID立即分配，避免并行冲突
                await self.db.flush()
                
                # 如果判定为同一事件，归并
                if result.get("is_same_event") and result.get("confidence", 0) >= 0.8:
                    group_id = f"halfday_{uuid.uuid4().hex[:8]}"
                    
                    # 更新所有 item 的 group_id
                    for item in items:
                        item.period_merge_group_id = group_id
                    
                    merge_groups.append({
                        "group_id": group_id,
                        "items": items,
                        "is_same_event": True,
                        "confidence": result.get("confidence", 0),
                        "reason": result.get("reason", "")
                    })
                else:
                    # 不是同一事件，拆分为单独的组
                    for item in items:
                        group_id = f"halfday_{uuid.uuid4().hex[:8]}"
                        item.period_merge_group_id = group_id
                        merge_groups.append({
                            "group_id": group_id,
                            "items": [item],
                            "is_same_event": False,
                            "confidence": 1.0 - result.get("confidence", 0)
                        })
                
            except Exception as e:
                print(f"❌ LLM 判定失败: {e}")
                # 失败时每个item单独成组
                for item in items:
                    group_id = f"halfday_{uuid.uuid4().hex[:8]}"
                    item.period_merge_group_id = group_id
                    merge_groups.append({
                        "group_id": group_id,
                        "items": [item],
                        "is_same_event": False,
                        "confidence": 0.5
                    })
        
        await self.db.commit()
        
        return merge_groups
    
    async def _filter_by_occurrence(
        self,
        merge_groups: List[Dict[str, Any]],
        min_occurrence: int = 2
    ) -> Tuple[List[SourceItem], List[SourceItem]]:
        """
        根据出现次数筛选
        
        Args:
            merge_groups: 归并组列表
            min_occurrence: 最小出现次数阈值
            
        Returns:
            (保留的items, 丢弃的items)
        """
        kept_items = []
        dropped_items = []
        
        for group in merge_groups:
            items = group["items"]
            occurrence = len(items)
            
            # 更新出现次数
            for item in items:
                item.occurrence_count = occurrence
            
            if occurrence >= min_occurrence:
                # 保留
                for item in items:
                    item.merge_status = "pending_global_merge"
                    kept_items.append(item)
            else:
                # 丢弃
                for item in items:
                    item.merge_status = "discarded"
                    dropped_items.append(item)
        
        await self.db.commit()
        
        return kept_items, dropped_items
    
    async def _aggregate_heat(self, merge_groups: List[Dict[str, Any]]):
        """聚合每个归并组的热度"""
        for group in merge_groups:
            items = group["items"]
            
            if not items:
                continue
            
            # 计算组内热度（使用平均值或最大值）
            heat_values = [
                item.heat_normalized for item in items 
                if item.heat_normalized is not None
            ]
            
            if heat_values:
                group["avg_heat"] = sum(heat_values) / len(heat_values)
                group["max_heat"] = max(heat_values)
            else:
                group["avg_heat"] = 0.0
                group["max_heat"] = 0.0
