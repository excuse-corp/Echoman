"""
分类统计服务

计算各分类（娱乐八卦、社会时事、体育电竞）的回声时长等指标
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, delete

from app.models import Topic, CategoryDayMetrics
from app.utils.timezone import now_cn

logger = logging.getLogger(__name__)


class CategoryMetricsService:
    """分类统计服务"""
    
    # 分类定义
    CATEGORIES = {
        "entertainment": "娱乐八卦类事件",
        "current_affairs": "社会实事类事件",
        "sports_esports": "体育电竞类事件"
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_category_metrics_summary(
        self,
        window_days: int = 365,
        ended_only: bool = False
    ) -> Dict[str, Any]:
        """
        获取分类统计摘要
        
        Args:
            window_days: 统计窗口天数，默认365天（一年）
            ended_only: 是否只统计已结束的话题
            
        Returns:
            分类统计结果
        """
        logger.info(f"获取分类统计摘要: window_days={window_days}, ended_only={ended_only}")
        
        # 计算时间范围
        now = now_cn()
        since = now - timedelta(days=window_days)
        
        items = []
        
        for category_key in self.CATEGORIES.keys():
            metrics = await self._compute_category_metrics(
                category=category_key,
                since=since,
                ended_only=ended_only
            )
            items.append(metrics)
        
        return {
            "window_days": window_days,
            "ended_only": ended_only,
            "computed_at": now.isoformat(),
            "items": items
        }
    
    async def _compute_category_metrics(
        self,
        category: str,
        since: datetime,
        ended_only: bool
    ) -> Dict[str, Any]:
        """
        计算单个分类的统计指标
        
        Args:
            category: 分类key
            since: 统计开始时间
            ended_only: 是否只统计已结束的话题
            
        Returns:
            分类统计指标
        """
        # 构建查询条件
        conditions = [
            Topic.category == category,
            Topic.first_seen >= since
        ]
        
        if ended_only:
            conditions.append(Topic.status == "ended")
        
        # 查询所有符合条件的Topics
        stmt = select(Topic).where(and_(*conditions))
        result = await self.db.execute(stmt)
        topics = result.scalars().all()
        
        if not topics:
            return {
                "category": category,
                "avg_length_hours": 0.0,
                "max_length_hours": 0.0,
                "min_length_hours": 0.0,
                "avg_length_display": "0天0小时",
                "max_length_display": "0天0小时",
                "min_length_display": "0天0小时",
                "max_length_topic_id": None,
                "min_length_topic_id": None,
                "topics_count": 0,
                "topics_active": 0,
                "topics_ended": 0,
                "intensity_sum": 0,
                "intensity_avg": 0.0
            }
        
        # 计算回声时长（小时）
        lengths = []
        for topic in topics:
            if topic.first_seen and topic.last_active:
                length_hours = (topic.last_active - topic.first_seen).total_seconds() / 3600
                lengths.append({
                    "hours": length_hours,
                    "topic_id": topic.id
                })
        
        if not lengths:
            # 没有有效时长数据
            avg_hours = 0.0
            max_hours = 0.0
            min_hours = 0.0
            max_topic_id = None
            min_topic_id = None
        else:
            # 计算统计值
            avg_hours = sum(l["hours"] for l in lengths) / len(lengths)
            max_item = max(lengths, key=lambda x: x["hours"])
            min_item = min(lengths, key=lambda x: x["hours"])
            max_hours = max_item["hours"]
            min_hours = min_item["hours"]
            max_topic_id = max_item["topic_id"]
            min_topic_id = min_item["topic_id"]
        
        # 统计其他指标
        topics_count = len(topics)
        topics_active = sum(1 for t in topics if t.status == "active")
        topics_ended = sum(1 for t in topics if t.status == "ended")
        intensity_sum = sum(t.intensity_total or 0 for t in topics)
        intensity_avg = intensity_sum / topics_count if topics_count > 0 else 0.0
        
        return {
            "category": category,
            "avg_length_hours": round(avg_hours, 2),
            "max_length_hours": round(max_hours, 2),
            "min_length_hours": round(min_hours, 2),
            "avg_length_display": self._format_hours_to_display(avg_hours),
            "max_length_display": self._format_hours_to_display(max_hours),
            "min_length_display": self._format_hours_to_display(min_hours),
            "max_length_topic_id": max_topic_id,
            "min_length_topic_id": min_topic_id,
            "topics_count": topics_count,
            "topics_active": topics_active,
            "topics_ended": topics_ended,
            "intensity_sum": intensity_sum,
            "intensity_avg": round(intensity_avg, 2)
        }
    
    def _format_hours_to_display(self, hours: float) -> str:
        """
        将小时数格式化为人性化显示
        
        Args:
            hours: 小时数
            
        Returns:
            格式化字符串，如 "3天4小时"
        """
        if hours <= 0:
            return "0天0小时"
        
        days = int(hours // 24)
        remaining_hours = int(hours % 24)
        
        return f"{days}天{remaining_hours}小时"
    
    async def recompute_and_save_metrics(
        self,
        since_date: Optional[datetime] = None,
        rebuild: bool = False
    ) -> Dict[str, Any]:
        """
        重新计算并保存分类指标到数据库
        
        Args:
            since_date: 从哪个日期开始重算，None表示从今天开始
            rebuild: 是否重建（删除旧数据）
            
        Returns:
            计算结果统计
        """
        logger.info(f"开始重算分类指标: since={since_date}, rebuild={rebuild}")
        
        now = now_cn()
        target_date = since_date or now.date()
        
        if rebuild:
            # 删除旧数据（按日覆盖）
            delete_stmt = delete(CategoryDayMetrics).where(
                CategoryDayMetrics.day == target_date
            )
            result = await self.db.execute(delete_stmt)
            deleted_count = result.rowcount or 0
            logger.info(f"删除了 {deleted_count} 条旧数据")
        
        # 计算截止到目标日期的近一年数据
        since = datetime.combine(target_date, datetime.min.time()) - timedelta(days=365)
        
        saved_count = 0
        for category_key in self.CATEGORIES.keys():
            metrics = await self._compute_category_metrics(
                category=category_key,
                since=since,
                ended_only=False
            )
            
            # 保存到数据库
            record = CategoryDayMetrics(
                day=target_date,
                category=category_key,
                topics_count=metrics["topics_count"],
                topics_active=metrics["topics_active"],
                topics_ended=metrics["topics_ended"],
                avg_length_hours=metrics["avg_length_hours"],
                max_length_hours=metrics["max_length_hours"],
                min_length_hours=metrics["min_length_hours"],
                max_length_topic_id=metrics["max_length_topic_id"],
                min_length_topic_id=metrics["min_length_topic_id"],
                intensity_sum=metrics["intensity_sum"],
                intensity_avg=metrics["intensity_avg"]
            )
            self.db.add(record)
            saved_count += 1
        
        await self.db.commit()
        
        logger.info(f"重算完成，保存了 {saved_count} 条记录")
        
        return {
            "status": "success",
            "target_date": target_date.isoformat(),
            "saved_count": saved_count,
            "computed_at": now.isoformat()
        }
    
    async def get_latest_precomputed_metrics(self) -> Optional[Dict[str, Any]]:
        """
        获取最新的预计算指标
        
        Returns:
            预计算的指标数据，如果没有则返回None
        """
        # 查询最新日期的指标
        stmt = (
            select(CategoryDayMetrics)
            .order_by(desc(CategoryDayMetrics.day))
            .limit(3)  # 最多3个分类
        )
        result = await self.db.execute(stmt)
        records = result.scalars().all()
        
        if not records:
            return None
        
        items = []
        for record in records:
            items.append({
                "category": record.category,
                "avg_length_hours": record.avg_length_hours or 0.0,
                "max_length_hours": record.max_length_hours or 0.0,
                "min_length_hours": record.min_length_hours or 0.0,
                "avg_length_display": self._format_hours_to_display(record.avg_length_hours or 0.0),
                "max_length_display": self._format_hours_to_display(record.max_length_hours or 0.0),
                "min_length_display": self._format_hours_to_display(record.min_length_hours or 0.0),
                "max_length_topic_id": record.max_length_topic_id,
                "min_length_topic_id": record.min_length_topic_id,
                "topics_count": record.topics_count or 0,
                "topics_active": record.topics_active or 0,
                "topics_ended": record.topics_ended or 0,
                "intensity_sum": record.intensity_sum or 0,
                "intensity_avg": record.intensity_avg or 0.0
            })
        
        return {
            "window_days": 365,
            "ended_only": False,
            "computed_at": records[0].day.isoformat() if records else None,
            "source": "precomputed",
            "items": items
        }

