"""
话题相关API路由
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import joinedload

from app.core import get_db
from app.models import Topic, TopicNode, SourceItem
from app.schemas.common import PaginatedResponse
from app.schemas.topic import TopicResponse, TimelineNodeResponse

router = APIRouter()


@router.get("")
async def list_topics(
    status: Optional[str] = Query(None, description="状态筛选（active|ended）"),
    category: Optional[str] = Query(None, description="分类筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    order: str = Query("echo_rank", description="排序方式"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    获取话题列表
    
    - **status**: 状态筛选（active|ended）
    - **category**: 分类筛选（entertainment|current_affairs|sports_esports）
    - **keyword**: 关键词搜索
    - **order**: 排序方式（echo_rank|last_active_desc|heat_desc|intensity_desc）
    - **page**: 页码
    - **size**: 每页大小（默认50）
    """
    try:
        # 构建查询
        query = select(Topic)
        
        # 状态筛选
        if status:
            query = query.where(Topic.status == status)
        
        # 分类筛选
        if category:
            query = query.where(Topic.category == category)
        
        # 关键词搜索
        if keyword:
            query = query.where(Topic.title_key.contains(keyword))
        
        # 排序
        if order == "echo_rank":
            # 新的排序逻辑：先按回声长度（小时）降序，相同时按归一化热度降序
            # 计算时长（秒）并转换为小时
            length_seconds = func.extract('epoch', Topic.last_active - Topic.first_seen)
            length_hours = length_seconds / 3600.0
            
            # 先按长度（小时）降序，再按归一化热度降序
            query = query.order_by(
                desc(length_hours),
                desc(func.coalesce(Topic.current_heat_normalized, 0))
            )
        elif order == "last_active_desc":
            query = query.order_by(desc(Topic.last_active))
        elif order == "heat_desc":
            query = query.order_by(desc(Topic.current_heat_normalized))
        elif order == "intensity_desc":
            query = query.order_by(desc(Topic.intensity_total))
        else:
            # 默认使用新的排序逻辑
            length_seconds = func.extract('epoch', Topic.last_active - Topic.first_seen)
            length_hours = length_seconds / 3600.0
            query = query.order_by(
                desc(length_hours),
                desc(func.coalesce(Topic.current_heat_normalized, 0))
            )
        
        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        result = await db.execute(count_query)
        total = result.scalar()
        
        # 分页
        query = query.offset((page - 1) * size).limit(size)
        result = await db.execute(query)
        topics = result.scalars().all()
        
        # 转换为响应模型（适配前端格式）
        items = []
        for topic in topics:
            # 计算回声时长（小时数）
            length_hours = (topic.last_active - topic.first_seen).total_seconds() / 3600 if topic.last_active and topic.first_seen else 0
            
            # 获取平台分布（从TopicNodes查询）
            nodes_query = select(SourceItem.platform, func.count(SourceItem.id)).select_from(TopicNode).join(
                SourceItem, TopicNode.source_item_id == SourceItem.id
            ).where(TopicNode.topic_id == topic.id).group_by(SourceItem.platform)
            nodes_result = await db.execute(nodes_query)
            platform_mentions = dict(nodes_result.all())
            platforms = list(platform_mentions.keys())
            
            # 计算归一化热度（保持0-1范围，前端负责转换为百分比）
            heat_normalized = topic.current_heat_normalized or 0
            
            items.append({
                "topic_id": str(topic.id),  # 前端期望string类型
                "title": topic.title_key,  # 字段名改为title
                "summary": topic.title_key,  # 临时使用title作为summary
                "intensity_raw": topic.intensity_total,  # 保留原始强度值
                "intensity_norm": round(heat_normalized, 4) if heat_normalized > 0 else 0,  # 0-1范围，前端转换为百分比
                "length_hours": round(length_hours, 1),  # 回声长度（小时）
                "length_days": round(length_hours / 24, 2),  # 保留天数字段（兼容性）
                "first_seen": topic.first_seen.isoformat() if topic.first_seen else None,
                "last_active": topic.last_active.isoformat() if topic.last_active else None,
                "platforms": platforms,
                "platform_mentions": platform_mentions,
                "status": topic.status
            })
        
        return {
            "page": page,
            "size": size,
            "total": total,
            "items": items
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{topic_id}")
async def get_topic_detail(
    topic_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取话题详情
    
    - **topic_id**: 话题ID
    """
    try:
        stmt = select(Topic).where(Topic.id == topic_id)
        result = await db.execute(stmt)
        topic = result.scalar_one_or_none()
        
        if not topic:
            raise HTTPException(status_code=404, detail="话题不存在")
        
        # 计算回声时长
        length_delta = topic.last_active - topic.first_seen
        days = length_delta.days
        hours = length_delta.seconds // 3600
        length_display = f"{days}天{hours}小时"
        
        return {
            "id": topic.id,
            "title_key": topic.title_key,
            "first_seen": topic.first_seen,
            "last_active": topic.last_active,
            "status": topic.status,
            "category": topic.category,
            "intensity_total": topic.intensity_total,
            "interaction_total": topic.interaction_total,
            "current_heat_normalized": topic.current_heat_normalized,
            "heat_percentage": topic.heat_percentage,
            "length_display": length_display,
            "summary": None  # TODO: 查询摘要
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{topic_id}/timeline", response_model=PaginatedResponse[TimelineNodeResponse])
async def get_topic_timeline(
    topic_id: int,
    platform: Optional[str] = Query(None, description="平台筛选（weibo|zhihu|toutiao|sina|netease|baidu|hupu）"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(50, ge=1, le=100, description="每页大小"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取话题时间线
    
    返回该话题下的所有事件节点，按时间倒序排列。
    
    - **topic_id**: 话题ID
    - **platform**: 可选，平台筛选
    - **page**: 页码
    - **size**: 每页大小（默认50，最大100）
    """
    try:
        # 验证话题是否存在
        topic_stmt = select(Topic).where(Topic.id == topic_id)
        topic_result = await db.execute(topic_stmt)
        topic = topic_result.scalar_one_or_none()
        
        if not topic:
            raise HTTPException(status_code=404, detail="话题不存在")
        
        # 构建查询 - JOIN topic_nodes 和 source_items
        query = (
            select(TopicNode)
            .options(joinedload(TopicNode.source_item))
            .where(TopicNode.topic_id == topic_id)
        )
        
        # 平台筛选（需要通过 JOIN 实现）
        if platform:
            query = query.join(SourceItem, TopicNode.source_item_id == SourceItem.id)
            query = query.where(SourceItem.platform == platform)
        
        # 获取总数
        count_query = select(func.count()).select_from(
            select(TopicNode.id)
            .where(TopicNode.topic_id == topic_id)
            .subquery()
        )
        if platform:
            count_query = select(func.count()).select_from(
                select(TopicNode.id)
                .join(SourceItem, TopicNode.source_item_id == SourceItem.id)
                .where(TopicNode.topic_id == topic_id, SourceItem.platform == platform)
                .subquery()
            )
        
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        # 按 appended_at 倒序排序
        query = query.order_by(desc(TopicNode.appended_at))
        
        # 分页
        query = query.offset((page - 1) * size).limit(size)
        
        # 执行查询
        result = await db.execute(query)
        nodes = result.scalars().all()
        
        # 转换为响应模型
        items = []
        for node in nodes:
            source = node.source_item
            if not source:
                continue
            
            # 计算互动数（从 interactions 字段提取）
            engagement = None
            if source.interactions:
                # 尝试从不同字段提取互动数
                engagement = (
                    source.interactions.get('hot_score') or
                    source.interactions.get('engagement') or
                    source.interactions.get('interactions')
                )
                if engagement and isinstance(engagement, str):
                    try:
                        engagement = int(engagement)
                    except ValueError:
                        engagement = None
            
            items.append(
                TimelineNodeResponse(
                    node_id=node.id,
                    topic_id=topic_id,
                    timestamp=source.published_at if source.published_at else source.fetched_at,
                    title=source.title,
                    content=source.summary or source.title,
                    source_platform=source.platform,
                    source_url=source.url,
                    captured_at=source.fetched_at,
                    engagement=engagement
                )
            )
        
        return PaginatedResponse(
            page=page,
            size=size,
            total=total,
            items=items
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

