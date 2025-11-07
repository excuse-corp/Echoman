"""
Qwen Provider 实现

支持本地部署的 Qwen 模型（通过 vLLM/Ollama 提供 OpenAI 兼容 API）
"""
from typing import List, Dict, Any
import httpx
from .base import BaseLLMProvider


class QwenProvider(BaseLLMProvider):
    """Qwen Provider"""
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        对话补全
        
        使用 OpenAI 兼容的 API 接口
        """
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
        
        # 如果请求 JSON 输出
        if kwargs.get("response_format") == "json":
            payload["response_format"] = {"type": "json_object"}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # 提取结果
        choice = data["choices"][0]
        content = choice["message"]["content"]
        
        return {
            "content": content,
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model),
            "finish_reason": choice.get("finish_reason")
        }
    
    async def embedding(
        self,
        texts: List[str],
        **kwargs
    ) -> List[List[float]]:
        """
        文本向量化
        
        使用 OpenAI 兼容的 Embedding API
        """
        url = f"{self.base_url}/embeddings"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 获取嵌入模型（如果指定）
        embedding_model = kwargs.get("model", self.model)
        
        payload = {
            "model": embedding_model,
            "input": texts
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # 提取向量
        embeddings = [item["embedding"] for item in data["data"]]
        
        return embeddings

