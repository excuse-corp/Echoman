"""
Celery 应用配置
"""
from celery import Celery
from celery.schedules import crontab

from app.config import settings


# 创建 Celery 应用
app = Celery(
    "echoman",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.ingestion_tasks",
        "app.tasks.merge_tasks",
        "app.tasks.category_metrics_tasks",
    ]
)

# Celery 配置
app.conf.update(
    # 时区设置（使用中国时区）
    timezone="Asia/Shanghai",
    enable_utc=False,
    
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # 结果过期时间
    result_expires=3600,
    
    # 任务执行限制
    task_time_limit=3600,  # 1小时硬限制
    task_soft_time_limit=3000,  # 50分钟软限制
    
    # 并发设置
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    
    # 任务路由（已禁用，所有任务使用默认celery队列）
    # task_routes={
    #     "app.tasks.ingestion_tasks.*": {"queue": "ingestion"},
    #     # "app.tasks.merge_tasks.*": {"queue": "merge"},
    # },
    
    # 定时任务配置（Celery Beat）
    beat_schedule={
        # 采集任务：每天8次（8:00-22:00，每2小时）
        "ingest-scheduled": {
            "task": "app.tasks.ingestion_tasks.scheduled_ingestion",
            "schedule": crontab(
                hour="8,10,12,14,16,18,20,22",
                minute=0
            ),
        },
        
        # ========== 归并任务（3次/天：上午、下午、傍晚） ==========
        
        # 上午归并 (处理 AM 时段数据: 8:00, 10:00, 12:00)
        "halfday-merge-am": {
            "task": "app.tasks.merge_tasks.halfday_merge",
            "schedule": crontab(hour=12, minute=15),
        },
        "global-merge-am": {
            "task": "app.tasks.merge_tasks.global_merge",
            "schedule": crontab(hour=12, minute=30),
        },
        
        # 下午归并 (处理 PM 时段数据: 14:00, 16:00, 18:00)
        "halfday-merge-pm": {
            "task": "app.tasks.merge_tasks.halfday_merge",
            "schedule": crontab(hour=18, minute=15),
        },
        "global-merge-pm": {
            "task": "app.tasks.merge_tasks.global_merge",
            "schedule": crontab(hour=18, minute=30),
        },
        
        # 傍晚归并 (处理 EVE 时段数据: 20:00, 22:00)
        "halfday-merge-eve": {
            "task": "app.tasks.merge_tasks.halfday_merge",
            "schedule": crontab(hour=22, minute=15),
        },
        "global-merge-eve": {
            "task": "app.tasks.merge_tasks.global_merge",
            "schedule": crontab(hour=22, minute=30),
        },
        
        # ========== 分类统计重算（每日1:00） ==========
        
        # 每日重算分类统计指标（一年窗口）
        "daily-recompute-category-metrics": {
            "task": "app.tasks.category_metrics_tasks.daily_recompute_metrics",
            "schedule": crontab(hour=1, minute=0),
        },
    }
)

# 自动发现任务
app.autodiscover_tasks()


if __name__ == "__main__":
    app.start()

