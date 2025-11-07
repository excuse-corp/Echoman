"""
LLM Provider 基类

定义统一的 LLM 调用接口
支持：非流式和流式对话
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime


class BaseLLMProvider(ABC):
    """LLM Provider 基类"""
    
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 60
    ):
        """
        初始化 Provider
        
        Args:
            model: 模型名称
            api_key: API 密钥
            base_url: API 基础 URL（可选）
            temperature: 温度参数
            max_tokens: 最大 Token 数
            timeout: 超时时间（秒）
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        对话补全
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            **kwargs: 其他参数
            
        Returns:
            {
                "content": "回复内容",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "model": "模型名称"
            }
        """
        pass
    
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        对话补全（流式）
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            **kwargs: 其他参数
            
        Yields:
            {
                "content": "增量内容",
                "finish_reason": null | "stop" | "length"
            }
        """
        # 默认实现：调用非流式API，模拟流式输出
        response = await self.chat_completion(messages, **kwargs)
        content = response.get("content", "")
        
        # 逐字输出（模拟流式）
        for i, char in enumerate(content):
            yield {
                "content": char,
                "finish_reason": None
            }
        
        # 最后发送完成信号
        yield {
            "content": "",
            "finish_reason": "stop"
        }
    
    @abstractmethod
    async def embedding(
        self,
        texts: List[str],
        **kwargs
    ) -> List[List[float]]:
        """
        文本向量化
        
        Args:
            texts: 文本列表
            **kwargs: 其他参数
            
        Returns:
            向量列表 [[0.1, 0.2, ...], ...]
        """
        pass
    
    async def batch_judge(
        self,
        prompt_template: str,
        items: List[Dict[str, Any]],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        批量判定（用于归并判定）
        
        Args:
            prompt_template: Prompt 模板
            items: 待判定项列表
            **kwargs: 其他参数
            
        Returns:
            判定结果列表
        """
        # 构建 prompt
        prompt = prompt_template.format(items=items)
        
        messages = [
            {"role": "system", "content": "你是一个专业的新闻事件分析助手。"},
            {"role": "user", "content": prompt}
        ]
        
        # 调用 LLM
        response = await self.chat_completion(messages, **kwargs)
        
        # 解析结果（假设返回 JSON）
        import json
        try:
            result = json.loads(response["content"])
            return result if isinstance(result, list) else [result]
        except:
            return []
    
    def get_provider_name(self) -> str:
        """获取 Provider 名称"""
        return self.__class__.__name__.replace("Provider", "").lower()

