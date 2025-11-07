"""
OpenAI Provider 实现

支持 OpenAI 和 Azure OpenAI
支持流式输出（SSE）
"""
from typing import List, Dict, Any, AsyncGenerator
import httpx
import json
from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # OpenAI 默认 base_url
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """对话补全"""
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        # JSON 输出模式
        if kwargs.get("response_format") == "json":
            payload["response_format"] = {"type": "json_object"}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        choice = data["choices"][0]
        content = choice["message"]["content"]
        
        return {
            "content": content,
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model),
            "finish_reason": choice.get("finish_reason")
        }
    
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """对话补全（流式）"""
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": True  # 启用流式输出
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                
                # 读取SSE流
                async for line in response.aiter_lines():
                    line = line.strip()
                    
                    # 跳过空行和注释
                    if not line or line.startswith(":"):
                        continue
                    
                    # 移除 "data: " 前缀
                    if line.startswith("data: "):
                        line = line[6:]
                    
                    # 检查是否为结束信号
                    if line == "[DONE]":
                        break
                    
                    try:
                        # 解析JSON
                        chunk_data = json.loads(line)
                        
                        # 提取内容
                        if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                            choice = chunk_data["choices"][0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            finish_reason = choice.get("finish_reason")
                            
                            if content or finish_reason:
                                yield {
                                    "content": content,
                                    "finish_reason": finish_reason
                                }
                    
                    except json.JSONDecodeError:
                        # 跳过无法解析的行
                        continue
    
    async def embedding(
        self,
        texts: List[str],
        **kwargs
    ) -> List[List[float]]:
        """文本向量化"""
        url = f"{self.base_url}/embeddings"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        embedding_model = kwargs.get("model", self.model)
        
        payload = {
            "model": embedding_model,
            "input": texts
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        embeddings = [item["embedding"] for item in data["data"]]
        
        return embeddings


class OpenAICompatibleProvider(OpenAIProvider):
    """OpenAI-Compatible Provider
    
    支持任何兼容 OpenAI API 格式的服务，例如：
    - Ollama
    - LM Studio  
    - vLLM
    - LocalAI
    - FastChat
    等等
    """
    
    def __init__(
        self,
        model: str,
        api_key: str = "not-needed",
        base_url: str = "http://localhost:11434/v1",
        **kwargs
    ):
        """
        初始化 OpenAI-Compatible Provider
        
        Args:
            model: 模型名称
            api_key: API 密钥（某些服务不需要，可以传入任意值）
            base_url: API 基础 URL
            **kwargs: 其他参数
        """
        super().__init__(model, api_key, base_url=base_url, **kwargs)
    
    def get_provider_name(self) -> str:
        """获取 Provider 名称"""
        return "openai_compatible"


class AzureOpenAIProvider(OpenAIProvider):
    """Azure OpenAI Provider"""
    
    def __init__(
        self,
        model: str,
        api_key: str,
        endpoint: str,
        api_version: str = "2024-02-15-preview",
        deployment_name: str = None,
        **kwargs
    ):
        """
        初始化 Azure OpenAI Provider
        
        Args:
            model: 模型名称
            api_key: API 密钥
            endpoint: Azure endpoint
            api_version: API 版本
            deployment_name: 部署名称
        """
        super().__init__(model, api_key, **kwargs)
        self.endpoint = endpoint
        self.api_version = api_version
        self.deployment_name = deployment_name or model
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """对话补全（Azure 格式）"""
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment_name}/"
            f"chat/completions?api-version={self.api_version}"
        )
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }
        
        payload = {
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        choice = data["choices"][0]
        content = choice["message"]["content"]
        
        return {
            "content": content,
            "usage": data.get("usage", {}),
            "model": self.deployment_name,
            "finish_reason": choice.get("finish_reason")
        }

