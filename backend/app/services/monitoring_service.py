"""
监控服务

提供Prometheus指标收集和系统健康检查
"""
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from typing import Dict, Any
from datetime import datetime, timedelta
from app.utils.timezone import now_cn
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
import psutil
import platform

from app.models import (
    SourceItem, Topic, TopicNode, LLMJudgement,
    RunIngest
)


# ========== Prometheus 指标定义 ==========

# 采集指标
ingest_total = Counter(
    'echoman_ingest_total',
    '采集总次数',
    ['platform', 'status']
)

ingest_items = Counter(
    'echoman_ingest_items_total',
    '采集条目总数',
    ['platform']
)

ingest_duration = Histogram(
    'echoman_ingest_duration_seconds',
    '采集耗时（秒）',
    ['platform']
)

# 归并指标
merge_halfday_total = Counter(
    'echoman_merge_halfday_total',
    '半日归并总次数',
    ['status']
)

merge_global_total = Counter(
    'echoman_merge_global_total',
    '整体归并总次数',
    ['action']  # merge / new
)

merge_duration = Histogram(
    'echoman_merge_duration_seconds',
    '归并耗时（秒）',
    ['merge_type']  # halfday / global
)

# 主题指标
topics_total = Gauge(
    'echoman_topics_total',
    '主题总数',
    ['status']  # active / ended
)

topics_created = Counter(
    'echoman_topics_created_total',
    '创建的主题总数'
)

# LLM调用指标
llm_calls_total = Counter(
    'echoman_llm_calls_total',
    'LLM调用总次数',
    ['type', 'provider', 'status']  # type: classify/summarize/merge/chat
)

llm_tokens_total = Counter(
    'echoman_llm_tokens_total',
    'LLM Token消耗总数',
    ['type', 'token_type']  # token_type: prompt/completion
)

llm_duration = Histogram(
    'echoman_llm_duration_seconds',
    'LLM调用耗时（秒）',
    ['type', 'provider']
)

# RAG对话指标
chat_queries_total = Counter(
    'echoman_chat_queries_total',
    '对话查询总次数',
    ['mode', 'status']  # mode: topic/global
)

chat_duration = Histogram(
    'echoman_chat_duration_seconds',
    '对话耗时（秒）',
    ['mode']
)

# 系统资源指标
system_cpu_percent = Gauge(
    'echoman_system_cpu_percent',
    'CPU使用率'
)

system_memory_percent = Gauge(
    'echoman_system_memory_percent',
    '内存使用率'
)

system_disk_percent = Gauge(
    'echoman_system_disk_percent',
    '磁盘使用率'
)

# 系统信息
system_info = Info(
    'echoman_system',
    '系统信息'
)


class MonitoringService:
    """监控服务"""
    
    def __init__(self):
        # 初始化系统信息
        system_info.info({
            'version': '1.0.0',
            'python_version': platform.python_version(),
            'platform': platform.system(),
            'hostname': platform.node()
        })
    
    async def update_metrics(self, db: AsyncSession):
        """
        更新所有指标
        
        定期调用以更新Gauge类型的指标
        """
        # 1. 更新主题统计
        await self._update_topic_metrics(db)
        
        # 2. 更新系统资源
        self._update_system_metrics()
    
    async def _update_topic_metrics(self, db: AsyncSession):
        """更新主题相关指标"""
        # 统计active主题数
        active_stmt = select(func.count(Topic.id)).where(Topic.status == 'active')
        active_count = await db.scalar(active_stmt) or 0
        topics_total.labels(status='active').set(active_count)
        
        # 统计ended主题数
        ended_stmt = select(func.count(Topic.id)).where(Topic.status == 'ended')
        ended_count = await db.scalar(ended_stmt) or 0
        topics_total.labels(status='ended').set(ended_count)
    
    def _update_system_metrics(self):
        """更新系统资源指标"""
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        system_cpu_percent.set(cpu_percent)
        
        # 内存使用率
        memory = psutil.virtual_memory()
        system_memory_percent.set(memory.percent)
        
        # 磁盘使用率
        disk = psutil.disk_usage('/')
        system_disk_percent.set(disk.percent)
    
    async def get_health_status(self, db: AsyncSession) -> Dict[str, Any]:
        """
        获取系统健康状态
        
        Returns:
            健康状态信息
        """
        status = {
            "status": "healthy",
            "timestamp": now_cn().isoformat(),
            "components": {}
        }
        
        # 1. 检查数据库连接
        try:
            await db.execute(text("SELECT 1"))
            status["components"]["database"] = {"status": "up"}
        except Exception as e:
            status["components"]["database"] = {
                "status": "down",
                "error": str(e)
            }
            status["status"] = "unhealthy"
        
        # 2. 检查最近的采集情况
        try:
            recent_run_stmt = (
                select(RunIngest)
                .order_by(RunIngest.started_at.desc())
                .limit(1)
            )
            recent_run = await db.scalar(recent_run_stmt)
            
            if recent_run:
                time_since_last = now_cn() - recent_run.started_at
                
                if time_since_last > timedelta(hours=3):
                    status["components"]["ingestion"] = {
                        "status": "stale",
                        "last_run": recent_run.started_at.isoformat(),
                        "warning": "最后一次采集距今超过3小时"
                    }
                else:
                    status["components"]["ingestion"] = {
                        "status": "active",
                        "last_run": recent_run.started_at.isoformat()
                    }
            else:
                status["components"]["ingestion"] = {
                    "status": "unknown",
                    "warning": "未找到采集记录"
                }
        except Exception as e:
            status["components"]["ingestion"] = {
                "status": "error",
                "error": str(e)
            }
        
        # 3. 检查系统资源
        cpu_percent = psutil.cpu_percent()
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        
        resource_status = "healthy"
        warnings = []
        
        if cpu_percent > 90:
            resource_status = "warning"
            warnings.append(f"CPU使用率过高: {cpu_percent}%")
        
        if memory_percent > 90:
            resource_status = "warning"
            warnings.append(f"内存使用率过高: {memory_percent}%")
        
        if disk_percent > 90:
            resource_status = "critical"
            warnings.append(f"磁盘使用率过高: {disk_percent}%")
            status["status"] = "unhealthy"
        
        status["components"]["resources"] = {
            "status": resource_status,
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(memory_percent, 2),
            "disk_percent": round(disk_percent, 2),
            "warnings": warnings
        }
        
        return status
    
    async def get_metrics_summary(self, db: AsyncSession) -> Dict[str, Any]:
        """
        获取指标摘要
        
        Returns:
            指标统计摘要
        """
        # 统计最近24小时的数据
        since = now_cn() - timedelta(hours=24)
        
        # 采集统计
        ingest_stmt = (
            select(
                RunIngest.status,
                func.count(RunIngest.id).label('count')
            )
            .where(RunIngest.started_at >= since)
            .group_by(RunIngest.status)
        )
        ingest_result = await db.execute(ingest_stmt)
        ingest_stats = {row[0]: row[1] for row in ingest_result}
        
        # 主题统计
        topics_stmt = (
            select(
                Topic.status,
                func.count(Topic.id).label('count')
            )
            .group_by(Topic.status)
        )
        topics_result = await db.execute(topics_stmt)
        topics_stats = {row[0]: row[1] for row in topics_result}
        
        # LLM调用统计
        llm_stmt = (
            select(
                LLMJudgement.type,
                func.count(LLMJudgement.id).label('count'),
                func.sum(LLMJudgement.tokens_prompt).label('total_prompt_tokens'),
                func.sum(LLMJudgement.tokens_completion).label('total_completion_tokens'),
                func.avg(LLMJudgement.latency_ms).label('avg_latency_ms')
            )
            .where(LLMJudgement.created_at >= since)
            .group_by(LLMJudgement.type)
        )
        llm_result = await db.execute(llm_stmt)
        llm_stats = {}
        for row in llm_result:
            llm_stats[row[0]] = {
                'count': row[1],
                'total_prompt_tokens': row[2] or 0,
                'total_completion_tokens': row[3] or 0,
                'avg_latency_ms': round(row[4], 2) if row[4] else 0
            }
        
        return {
            "period": "24h",
            "timestamp": now_cn().isoformat(),
            "ingestion": ingest_stats,
            "topics": topics_stats,
            "llm": llm_stats
        }
    
    def get_prometheus_metrics(self) -> tuple:
        """
        获取Prometheus格式的指标
        
        Returns:
            (metrics_text, content_type)
        """
        return generate_latest(), CONTENT_TYPE_LATEST


# 全局监控服务实例
monitoring_service = MonitoringService()


# 便捷函数用于记录指标
def record_ingest(platform: str, status: str, duration: float, items_count: int = 0):
    """记录采集指标"""
    ingest_total.labels(platform=platform, status=status).inc()
    ingest_duration.labels(platform=platform).observe(duration)
    if items_count > 0:
        ingest_items.labels(platform=platform).inc(items_count)


def record_merge(merge_type: str, duration: float, action: str = None):
    """记录归并指标"""
    if merge_type == 'halfday':
        merge_halfday_total.labels(status='success').inc()
    elif merge_type == 'global':
        if action:
            merge_global_total.labels(action=action).inc()
    
    merge_duration.labels(merge_type=merge_type).observe(duration)


def record_llm_call(call_type: str, provider: str, status: str, 
                   duration: float, prompt_tokens: int = 0, 
                   completion_tokens: int = 0):
    """记录LLM调用指标"""
    llm_calls_total.labels(type=call_type, provider=provider, status=status).inc()
    llm_duration.labels(type=call_type, provider=provider).observe(duration)
    
    if prompt_tokens > 0:
        llm_tokens_total.labels(type=call_type, token_type='prompt').inc(prompt_tokens)
    if completion_tokens > 0:
        llm_tokens_total.labels(type=call_type, token_type='completion').inc(completion_tokens)


def record_chat_query(mode: str, status: str, duration: float):
    """记录对话查询指标"""
    chat_queries_total.labels(mode=mode, status=status).inc()
    chat_duration.labels(mode=mode).observe(duration)

