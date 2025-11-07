"""
事件分类服务

实现三分类：娱乐八卦、社会时事、体育电竞
采用规则优先 + LLM兜底的混合策略

优化：添加文本截断以处理 qwen3-32b 的 32k 上下文限制
"""
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import re
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Topic, TopicNode, SourceItem, LLMJudgement
from app.services.llm.factory import get_llm_provider
from app.config import settings
from app.utils.token_manager import get_token_manager

logger = logging.getLogger(__name__)


class ClassificationService:
    """事件分类服务"""
    
    # 分类枚举
    ENTERTAINMENT = "entertainment"
    CURRENT_AFFAIRS = "current_affairs"
    SPORTS_ESPORTS = "sports_esports"
    
    # 规则关键词库
    KEYWORDS = {
        ENTERTAINMENT: {
            "strong": ["明星", "娱乐", "八卦", "绯闻", "爆料", "综艺", "电影", "电视剧", 
                      "演员", "歌手", "偶像", "爱豆", "粉丝", "娱乐圈", "影视", "节目",
                      "出轨", "离婚", "恋情", "结婚", "生子", "颁奖", "首映", "热播"],
            "medium": ["导演", "编剧", "制作人", "经纪人", "造型师", "剧组", "片场",
                      "首播", "上映", "票房", "收视率", "口碑", "评分", "豆瓣"]
        },
        CURRENT_AFFAIRS: {
            "strong": ["政策", "法规", "政府", "国务院", "发改委", "司法", "法院", "检察",
                      "公安", "警方", "事故", "案件", "民生", "舆情", "公共", "社会",
                      "财经", "经济", "股市", "央行", "监管", "治理", "改革", "疫情"],
            "medium": ["会议", "通知", "公告", "声明", "调查", "处理", "整治", "专项",
                      "民众", "市民", "居民", "群众", "网友", "热议", "关注", "讨论"]
        },
        SPORTS_ESPORTS: {
            "strong": ["比赛", "联赛", "世界杯", "总决赛", "季后赛", "决赛", "半决赛",
                      "球队", "球员", "教练", "俱乐部", "战队", "电竞", "赛事", "夺冠",
                      "冠军", "亚军", "金牌", "银牌", "铜牌", "破纪录", "MVP"],
            "medium": ["足球", "篮球", "网球", "羽毛球", "乒乓球", "游泳", "田径", "体操",
                      "LOL", "DOTA", "王者荣耀", "吃鸡", "CS", "转会", "签约", "续约"]
        }
    }
    
    # 平台权重（某些平台偏向特定分类）
    PLATFORM_BIAS = {
        "hupu": {SPORTS_ESPORTS: 0.3},  # 虎扑偏体育
    }
    
    def __init__(self):
        self.settings = settings
        self.llm_provider = get_llm_provider()
        self.token_manager = get_token_manager(model=settings.qwen_model)
        self.rule_threshold = 0.6  # 规则置信度阈值
        # Token 限制：分类任务相对简单，预留较少 token
        self.max_prompt_tokens = 1500  # 输入上下文最大 token
        self.max_completion_tokens = 300  # 分类结果最大 token
        
    async def classify_topic(
        self, 
        db: AsyncSession,
        topic: Topic,
        force_llm: bool = False
    ) -> Tuple[str, float, str]:
        """
        对主题进行分类
        
        Args:
            db: 数据库会话
            topic: 主题对象
            force_llm: 是否强制使用LLM（跳过规则）
            
        Returns:
            (category, confidence, method)
        """
        # 1. 获取主题的关键节点（用于分类）
        nodes = await self._get_topic_key_nodes(db, topic.id)
        
        if not nodes:
            # 无节点数据，使用默认分类
            return self.CURRENT_AFFAIRS, 0.3, "default"
        
        # 2. 提取文本内容
        texts = []
        platforms = set()
        for node in nodes:
            if node.source_item:
                texts.append(node.source_item.title)
                if node.source_item.summary:
                    texts.append(node.source_item.summary)
                platforms.add(node.source_item.platform)
        
        combined_text = " ".join(texts)
        
        # 3. 规则分类（如果不强制LLM）
        if not force_llm:
            rule_category, rule_confidence = self._rule_based_classification(
                combined_text, 
                list(platforms)
            )
            
            if rule_confidence >= self.rule_threshold:
                return rule_category, rule_confidence, "rule"
        
        # 4. LLM分类
        llm_category, llm_confidence = await self._llm_classification(
            db,
            topic,
            nodes[:10]  # 最多使用前10个节点
        )
        
        return llm_category, llm_confidence, "llm"
    
    def _rule_based_classification(
        self, 
        text: str, 
        platforms: List[str]
    ) -> Tuple[str, float]:
        """
        基于规则的分类
        
        Args:
            text: 文本内容
            platforms: 来源平台列表
            
        Returns:
            (category, confidence)
        """
        scores = {
            self.ENTERTAINMENT: 0.0,
            self.CURRENT_AFFAIRS: 0.0,
            self.SPORTS_ESPORTS: 0.0
        }
        
        # 关键词匹配评分
        for category, keywords in self.KEYWORDS.items():
            for keyword in keywords["strong"]:
                if keyword in text:
                    scores[category] += 0.15
            for keyword in keywords["medium"]:
                if keyword in text:
                    scores[category] += 0.05
        
        # 平台偏好加权
        for platform in platforms:
            if platform in self.PLATFORM_BIAS:
                for category, bias in self.PLATFORM_BIAS[platform].items():
                    scores[category] += bias
        
        # 归一化到 [0, 1]
        max_score = max(scores.values())
        if max_score > 0:
            for cat in scores:
                scores[cat] = min(scores[cat] / max_score, 1.0)
        
        # 选择得分最高的类别
        best_category = max(scores, key=scores.get)
        confidence = scores[best_category]
        
        # 如果所有得分都很低，默认为时事类
        if confidence < 0.2:
            return self.CURRENT_AFFAIRS, confidence
        
        return best_category, confidence
    
    async def _llm_classification(
        self,
        db: AsyncSession,
        topic: Topic,
        nodes: List[TopicNode]
    ) -> Tuple[str, float]:
        """
        基于LLM的分类
        
        Args:
            db: 数据库会话
            topic: 主题对象
            nodes: 节点列表
            
        Returns:
            (category, confidence)
        """
        # 构造Prompt（带文本截断）
        nodes_text = []
        for i, node in enumerate(nodes[:5], 1):  # 最多5个节点
            if node.source_item:
                title = self.token_manager.truncate_text(
                    node.source_item.title,
                    max_tokens=50  # 每个标题最多 50 tokens
                )
                nodes_text.append(
                    f"{i}. [{node.source_item.platform}] {title}"
                )
                if node.source_item.summary:
                    summary = self.token_manager.truncate_text(
                        node.source_item.summary,
                        max_tokens=80  # 每个摘要最多 80 tokens
                    )
                    nodes_text.append(f"   摘要: {summary}")
        
        prompt = f"""请对以下热点事件进行分类，从三个类别中选择一个：

【分类定义】
1. entertainment（娱乐八卦类）：明星、影视、综艺、娱乐圈八卦、粉丝文化等
2. current_affairs（社会时事类）：政策法规、社会事件、民生新闻、经济财经、公共事务等
3. sports_esports（体育电竞类）：体育赛事、电竞比赛、球队球员、体育新闻等

【事件信息】
主题标题: {topic.title_key}
持续时长: {self._calculate_duration(topic)}
来源平台数: {await self._count_platforms(db, topic.id)}

【关键内容】（按时间顺序）
{chr(10).join(nodes_text)}

请分析事件的主要内容和性质，输出JSON格式：
{{
  "category": "entertainment | current_affairs | sports_esports",
  "confidence": 0.0-1.0,
  "reason": "分类理由（简明扼要）"
}}

注意：
1. confidence应反映分类的确定性（0.0-1.0）
2. 如果事件涉及多个领域，选择最主要的一个
3. reason应说明为什么选择这个分类
"""
        
        # Token 优化：确保 prompt 不超过限制
        prompt_tokens = self.token_manager.count_tokens(prompt)
        if prompt_tokens > self.max_prompt_tokens:
            logger.warning(
                f"分类 prompt 过长 ({prompt_tokens} tokens)，需要截断"
            )
            prompt = self.token_manager.truncate_text(
                prompt,
                max_tokens=self.max_prompt_tokens
            )
            logger.info(f"截断后 prompt: {self.token_manager.count_tokens(prompt)} tokens")
        
        try:
            # 调用LLM
            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=self.max_completion_tokens  # 使用配置的值（300）
            )
            
            # 解析响应
            result = self._parse_llm_response(response)
            
            # 记录 Token 使用
            logger.info(
                f"分类完成 - Prompt: {prompt_tokens} tokens, "
                f"Completion: {response.get('usage', {}).get('completion_tokens', 0)} tokens, "
                f"分类: {result['category']} (置信度: {result['confidence']})"
            )
            
            # 记录判定任务
            await self._record_judgement(
                db,
                topic_id=topic.id,
                prompt=prompt,
                response=response,
                result=result
            )
            
            return result["category"], result["confidence"]
            
        except Exception as e:
            print(f"LLM分类失败: {e}")
            # 降级到规则分类
            return self.CURRENT_AFFAIRS, 0.3
    
    def _parse_llm_response(self, response) -> Dict:
        """解析LLM响应"""
        try:
            # 如果response是dict（来自LLM provider），提取content字段
            if isinstance(response, dict):
                content = response.get("content", "")
            else:
                content = response
            
            # 尝试直接解析JSON
            result = json.loads(content)
            
            # 验证字段
            if "category" not in result:
                raise ValueError("Missing category field")
            
            # 验证类别值
            valid_categories = [
                self.ENTERTAINMENT, 
                self.CURRENT_AFFAIRS, 
                self.SPORTS_ESPORTS
            ]
            if result["category"] not in valid_categories:
                raise ValueError(f"Invalid category: {result['category']}")
            
            # 确保confidence在有效范围
            result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.5))))
            
            return result
            
        except json.JSONDecodeError:
            # 尝试从文本中提取
            text_content = content if isinstance(content, str) else str(content)
            text_lower = text_content.lower()
            
            if "entertainment" in text_lower:
                category = self.ENTERTAINMENT
            elif "sports" in text_lower or "esports" in text_lower:
                category = self.SPORTS_ESPORTS
            else:
                category = self.CURRENT_AFFAIRS
            
            return {
                "category": category,
                "confidence": 0.5,
                "reason": "Parsed from text"
            }
    
    async def _get_topic_key_nodes(
        self, 
        db: AsyncSession, 
        topic_id: int
    ) -> List[TopicNode]:
        """获取主题的关键节点"""
        from app.models import TopicNode
        from sqlalchemy.orm import joinedload
        
        stmt = (
            select(TopicNode)
            .options(joinedload(TopicNode.source_item))
            .where(TopicNode.topic_id == topic_id)
            .order_by(TopicNode.appended_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def _count_platforms(self, db: AsyncSession, topic_id: int) -> int:
        """统计主题涉及的平台数"""
        from sqlalchemy import func, distinct
        
        stmt = (
            select(func.count(distinct(SourceItem.platform)))
            .select_from(TopicNode)
            .join(SourceItem)
            .where(TopicNode.topic_id == topic_id)
        )
        result = await db.execute(stmt)
        return result.scalar() or 0
    
    def _calculate_duration(self, topic: Topic) -> str:
        """计算事件持续时长"""
        if not topic.first_seen or not topic.last_active:
            return "未知"
        
        delta = topic.last_active - topic.first_seen
        days = delta.days
        hours = delta.seconds // 3600
        
        if days > 0:
            return f"{days}天{hours}小时"
        else:
            return f"{hours}小时"
    
    async def _record_judgement(
        self,
        db: AsyncSession,
        topic_id: int,
        prompt: str,
        response: str,
        result: Dict
    ):
        """记录LLM判定任务"""
        judgement = LLMJudgement(
            type="classify",
            status="completed",
            request={
                "topic_id": topic_id,
                "prompt": prompt
            },
            response=result,
            provider=self.llm_provider.get_provider_name(),
            model=self.llm_provider.model,
            latency_ms=0,  # TODO: 记录实际延迟
            tokens_prompt=0,  # TODO: 从LLM响应中获取
            tokens_completion=0
        )
        db.add(judgement)
        # 先flush确保ID立即分配，避免并行冲突
        await db.flush()
        await db.commit()

