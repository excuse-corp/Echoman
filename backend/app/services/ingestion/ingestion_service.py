"""
采集服务

负责调度和管理各平台的数据采集
"""
import hashlib
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import SourceItem, RunIngest
from app.utils.timezone import now_cn

# 导入现有的scrapers
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))
from scrapers import (
    WeiboScraper,
    ZhihuScraper,
    ToutiaoScraper,
    SinaScraper,
    NeteaseScraper,
    BaiduScraper,
    HupuScraper
)


class IngestionService:
    """采集服务"""
    
    # 平台爬虫映射
    SCRAPERS = {
        "weibo": WeiboScraper,
        "zhihu": ZhihuScraper,
        "toutiao": ToutiaoScraper,
        "sina": SinaScraper,
        "netease": NeteaseScraper,
        "baidu": BaiduScraper,
        "hupu": HupuScraper,
    }
    
    def __init__(self, db: AsyncSession):
        """
        初始化采集服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
    
    async def run_ingestion(
        self,
        platforms: Optional[List[str]] = None,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        执行采集任务
        
        Args:
            platforms: 平台列表（不填则采集所有启用平台）
            limit: 每平台采集条数
            
        Returns:
            运行结果字典
        """
        # 生成运行ID
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        started_at = now_cn()
        
        # 确定要采集的平台
        if platforms is None:
            platforms = settings.enabled_platforms_list
        else:
            # 过滤出支持的平台
            platforms = [p for p in platforms if p in self.SCRAPERS]
        
        # 创建运行记录
        run_record = RunIngest(
            run_id=run_id,
            started_at=started_at,
            status="running",
            total_platforms=len(platforms),
            config={"platforms": platforms, "limit": limit}
        )
        self.db.add(run_record)
        await self.db.commit()
        
        # 采集各平台
        platform_results = []
        total_items = 0
        success_items = 0
        failed_items = 0
        success_platforms = 0
        failed_platforms = 0
        
        for platform in platforms:
            try:
                result = await self._fetch_platform(
                    platform=platform,
                    limit=limit,
                    run_id=run_id
                )
                platform_results.append(result)
                
                total_items += result.get("total", 0)
                success_items += result.get("success", 0)
                failed_items += result.get("failed", 0)
                
                if result.get("status") == "success":
                    success_platforms += 1
                else:
                    failed_platforms += 1
                    
            except Exception as e:
                # 记录平台采集失败
                platform_results.append({
                    "platform": platform,
                    "status": "failed",
                    "error": str(e),
                    "total": 0,
                    "success": 0,
                    "failed": 0
                })
                failed_platforms += 1
        
        # 更新运行记录
        ended_at = now_cn()
        duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        
        run_record.status = "success" if failed_platforms == 0 else ("partial" if success_platforms > 0 else "failed")
        run_record.ended_at = ended_at
        run_record.duration_ms = duration_ms
        run_record.total_platforms = len(platforms)
        run_record.success_platforms = success_platforms
        run_record.failed_platforms = failed_platforms
        run_record.total_items = total_items
        run_record.success_items = success_items
        run_record.failed_items = failed_items
        run_record.platform_results = platform_results
        
        await self.db.commit()
        
        return {
            "run_id": run_id,
            "status": run_record.status,
            "duration_ms": duration_ms,
            "platforms": len(platforms),
            "total_items": total_items,
            "success_items": success_items,
            "platform_results": platform_results
        }
    
    async def _fetch_platform(
        self,
        platform: str,
        limit: int,
        run_id: str
    ) -> Dict[str, Any]:
        """
        采集单个平台
        
        Args:
            platform: 平台名称
            limit: 采集条数
            run_id: 运行ID
            
        Returns:
            采集结果字典
        """
        scraper_class = self.SCRAPERS.get(platform)
        if not scraper_class:
            return {
                "platform": platform,
                "status": "failed",
                "error": f"不支持的平台: {platform}",
                "total": 0,
                "success": 0,
                "failed": 0
            }
        
        try:
            # 创建爬虫实例并抓取（在线程池中运行同步代码）
            import asyncio
            
            def _fetch_sync():
                try:
                    scraper = scraper_class()
                    return scraper.fetch_hot_list(limit=limit)
                except Exception as e:
                    print(f"❌ {platform} 爬虫执行失败: {e}")
                    return []
            
            # 使用asyncio.to_thread（Python 3.9+）或默认线程池
            try:
                items = await asyncio.to_thread(_fetch_sync)
            except AttributeError:
                # Python <3.9 fallback
                loop = asyncio.get_event_loop()
                items = await loop.run_in_executor(None, _fetch_sync)
            
            # 保存到数据库
            success_count = 0
            failed_count = 0
            
            for item in items:
                try:
                    await self._save_source_item(item, run_id)
                    success_count += 1
                except Exception as e:
                    print(f"保存数据失败: {e}")
                    failed_count += 1
            
            await self.db.commit()
            
            return {
                "platform": platform,
                "status": "success",
                "total": len(items),
                "success": success_count,
                "failed": failed_count
            }
            
        except Exception as e:
            return {
                "platform": platform,
                "status": "failed",
                "error": str(e),
                "total": 0,
                "success": 0,
                "failed": 0
            }
    
    async def _save_source_item(self, item: Dict[str, Any], run_id: str):
        """
        保存采集项到数据库（不去重，直接入库）
        
        Args:
            item: 采集项数据
            run_id: 运行ID
        """
        # 计算哈希
        url = item.get("url", "")
        title = item.get("title", "")
        summary = item.get("summary", "")
        
        url_hash = hashlib.md5(url.encode()).hexdigest()
        content_hash = hashlib.md5(f"{title}{summary}".encode()).hexdigest()
        # 包含run_id，确保每次采集的相同URL都有独立记录
        dedup_key = f"{item['platform']}:{url_hash}:{run_id}"
        
        # 计算时段标识（三周期归并模式）
        current_time = now_cn()
        date_str = current_time.strftime("%Y-%m-%d")
        # 三周期划分：AM(8-12点), PM(14-18点), EVE(20-22点)
        if current_time.hour < 14:
            period_type = "AM"
        elif current_time.hour < 20:
            period_type = "PM"
        else:
            period_type = "EVE"
        period = f"{date_str}_{period_type}"
        
        # 直接创建新记录（不检查重复）
        source_item = SourceItem(
            platform=item["platform"],
            title=title,
            summary=summary,
            url=url,
            published_at=item.get("published_at"),
            fetched_at=current_time,
            interactions=item.get("interactions"),
            heat_value=item.get("hot_value"),
            url_hash=url_hash,
            content_hash=content_hash,
            dedup_key=dedup_key,
            run_id=run_id,
            merge_status="pending_event_merge",
            period=period,
            occurrence_count=1  # 初始为1，在归并阶段会根据聚类结果更新
        )
        
        self.db.add(source_item)
    
    async def get_runs_history(self, limit: int = 20) -> List[RunIngest]:
        """
        获取运行历史
        
        Args:
            limit: 返回条数
            
        Returns:
            运行记录列表
        """
        stmt = select(RunIngest).order_by(RunIngest.started_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_platform_status(self) -> List[Dict[str, Any]]:
        """
        获取各平台状态
        
        Returns:
            平台状态列表
        """
        # TODO: 实现更详细的平台状态统计
        # 这里先返回基础信息
        statuses = []
        
        for platform in settings.enabled_platforms_list:
            # 查询最近的成功运行
            stmt = select(RunIngest).where(
                RunIngest.status == "success"
            ).order_by(RunIngest.started_at.desc()).limit(10)
            result = await self.db.execute(stmt)
            recent_runs = result.scalars().all()
            
            # 计算统计信息
            success_count = len([r for r in recent_runs if r.status == "success"])
            success_rate = success_count / len(recent_runs) if recent_runs else 0
            
            avg_latency = 0
            if recent_runs:
                latencies = [r.duration_ms for r in recent_runs if r.duration_ms]
                avg_latency = sum(latencies) // len(latencies) if latencies else 0
            
            last_success = recent_runs[0] if recent_runs else None
            
            statuses.append({
                "platform": platform,
                "last_success_at": last_success.ended_at if last_success else None,
                "last_error": None,
                "success_rate_24h": success_rate,
                "avg_latency_ms": avg_latency,
                "records_per_run": settings.fetch_limit_per_platform,
                "auth_mode": "api",
                "notes": f"使用 {platform} API/爬虫"
            })
        
        return statuses

