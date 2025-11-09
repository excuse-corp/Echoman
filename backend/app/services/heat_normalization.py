"""
热度归一化服务

根据文档要求实现 Min-Max 归一化 + 平台权重加权
"""
from typing import List, Dict, Any
from datetime import datetime
from app.utils.timezone import now_cn
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.config import settings
from app.models import SourceItem


class HeatNormalizationService:
    """热度归一化服务"""
    
    def __init__(self, db: AsyncSession):
        """
        初始化服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
        self.platform_weights = settings.platform_weights_dict
    
    async def normalize_period_heat(self, period: str) -> Dict[str, Any]:
        """
        对归并周期内的热度值进行归一化
        
        Args:
            period: 归并周期标识（如 "2025-10-29_AM"、"2025-10-29_PM"、"2025-10-29_EVE"）
            
        Returns:
            归一化结果统计
        """
        # 1. 获取该归并周期内所有待归一化的数据
        stmt = select(SourceItem).where(
            and_(
                SourceItem.period == period,
                SourceItem.merge_status == "pending_event_merge"
            )
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()
        
        if not items:
            return {
                "status": "no_data",
                "period": period,
                "total_items": 0
            }
        
        # 2. 按平台分组
        platform_groups: Dict[str, List[SourceItem]] = {}
        for item in items:
            if item.platform not in platform_groups:
                platform_groups[item.platform] = []
            platform_groups[item.platform].append(item)
        
        # 3. 对每个平台进行 Min-Max 归一化
        normalized_items = []
        
        for platform, platform_items in platform_groups.items():
            # 获取该平台的热度值列表（过滤掉 None）
            heat_values = [
                item.heat_value for item in platform_items 
                if item.heat_value is not None
            ]
            
            # 如果该平台无热度值（如 sina、hupu），使用默认值 0.5
            if not heat_values:
                for item in platform_items:
                    item.heat_normalized = 0.5  # 中等热度
                    normalized_items.append(item)
                continue
            
            # Min-Max 归一化
            min_heat = min(heat_values)
            max_heat = max(heat_values)
            
            for item in platform_items:
                if item.heat_value is None:
                    # 无热度值，使用默认值
                    item.heat_normalized = 0.5
                elif max_heat == min_heat:
                    # 所有值相同，赋值为 0.5
                    item.heat_normalized = 0.5
                else:
                    # Min-Max 归一化: (value - min) / (max - min)
                    normalized = (item.heat_value - min_heat) / (max_heat - min_heat)
                    item.heat_normalized = normalized
                
                normalized_items.append(item)
        
        # 4. 应用平台权重
        weighted_items = []
        total_weight = sum(self.platform_weights.values())
        
        for item in normalized_items:
            # 获取平台权重（默认为 1.0）
            platform_weight = self.platform_weights.get(item.platform, 1.0)
            
            # 加权: normalized * platform_weight / sum(all_platform_weights)
            weighted = item.heat_normalized * platform_weight / total_weight
            item.heat_normalized = weighted
            weighted_items.append(item)
        
        # 5. 全局归一化（使归并周期内所有事件热度和为 1.0）
        total_heat = sum(item.heat_normalized for item in weighted_items)
        
        if total_heat > 0:
            for item in weighted_items:
                item.heat_normalized = item.heat_normalized / total_heat
        
        # 6. 保存到数据库
        await self.db.commit()
        
        # 7. 返回统计信息
        return {
            "status": "success",
            "period": period,
            "total_items": len(items),
            "platforms": len(platform_groups),
            "platform_stats": {
                platform: {
                    "count": len(platform_items),
                    "avg_heat": sum(
                        item.heat_normalized for item in platform_items
                    ) / len(platform_items) if platform_items else 0
                }
                for platform, platform_items in platform_groups.items()
            },
            "total_heat": total_heat
        }
    
    def calculate_period(self, dt: datetime = None) -> str:
        """
        计算归并周期标识（每日三次归并）
        
        Args:
            dt: 时间（默认为当前时间）
            
        Returns:
            时段标识（如 "2025-11-07_AM", "2025-11-07_PM", "2025-11-07_EVE"）
            
        周期划分：
        - AM: 8:00-12:00 的采集（3次）→ 12:15归并
        - PM: 14:00-18:00 的采集（3次）→ 18:15归并
        - EVE: 20:00-22:00 的采集（2次）→ 22:15归并
        """
        if dt is None:
            dt = now_cn()
        
        date_str = dt.strftime("%Y-%m-%d")
        
        # 根据时间确定归并周期
        if dt.hour < 14:
            period = "AM"
        elif dt.hour < 20:
            period = "PM"
        else:
            period = "EVE"
        
        return f"{date_str}_{period}"
    
    async def get_platform_heat_stats(self, period: str) -> Dict[str, Any]:
        """
        获取各平台热度统计
        
        Args:
            period: 半日时段标识
            
        Returns:
            各平台热度统计
        """
        stmt = select(SourceItem).where(
            SourceItem.period == period
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()
        
        if not items:
            return {}
        
        # 按平台分组统计
        platform_stats = {}
        
        for item in items:
            if item.platform not in platform_stats:
                platform_stats[item.platform] = {
                    "count": 0,
                    "total_heat_raw": 0,
                    "total_heat_normalized": 0,
                    "avg_heat_normalized": 0,
                    "weight": self.platform_weights.get(item.platform, 1.0)
                }
            
            stats = platform_stats[item.platform]
            stats["count"] += 1
            
            if item.heat_value is not None:
                stats["total_heat_raw"] += item.heat_value
            
            if item.heat_normalized is not None:
                stats["total_heat_normalized"] += item.heat_normalized
        
        # 计算平均值
        for platform, stats in platform_stats.items():
            if stats["count"] > 0:
                stats["avg_heat_normalized"] = (
                    stats["total_heat_normalized"] / stats["count"]
                )
        
        return platform_stats

