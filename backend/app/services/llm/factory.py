"""
LLM Provider Factory

根据配置创建对应的 Provider 实例
"""
from typing import Optional
from app.config import settings
from .base import BaseLLMProvider
from .qwen_provider import QwenProvider
from .openai_provider import OpenAIProvider, AzureOpenAIProvider, OpenAICompatibleProvider


def get_llm_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None
) -> BaseLLMProvider:
    """
    获取 LLM Provider 实例
    
    Args:
        provider_name: Provider 名称（不指定则使用配置）
        model: 模型名称（不指定则使用配置）
        
    Returns:
        LLM Provider 实例
    """
    provider_name = provider_name or settings.llm_provider
    provider_name = provider_name.lower()
    
    if provider_name == "qwen":
        return QwenProvider(
            model=model or settings.qwen_model,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_api_base,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds
        )
    
    elif provider_name == "openai":
        return OpenAIProvider(
            model=model or settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds
        )
    
    elif provider_name == "azure":
        return AzureOpenAIProvider(
            model=model or settings.azure_deployment_name,
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            deployment_name=settings.azure_deployment_name,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds
        )
    
    elif provider_name == "openai_compatible":
        return OpenAICompatibleProvider(
            model=model or settings.openai_compatible_model,
            api_key=settings.openai_compatible_api_key,
            base_url=settings.openai_compatible_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds
        )
    
    else:
        raise ValueError(f"不支持的 LLM Provider: {provider_name}")


def get_embedding_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None
) -> BaseLLMProvider:
    """
    获取 Embedding Provider 实例
    
    Args:
        provider_name: Provider 名称（不指定则使用配置）
        model: 模型名称（不指定则使用配置）
        
    Returns:
        Embedding Provider 实例
    """
    provider_name = provider_name or settings.llm_provider
    provider_name = provider_name.lower()
    
    if provider_name == "qwen":
        return QwenProvider(
            model=model or settings.qwen_embedding_model,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_api_base,
            timeout=settings.llm_timeout_seconds
        )
    
    elif provider_name == "openai":
        return OpenAIProvider(
            model=model or settings.openai_embedding_model,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds
        )
    
    elif provider_name == "azure":
        # Azure 使用相同的模型配置
        return AzureOpenAIProvider(
            model=model or "text-embedding-ada-002",
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            timeout=settings.llm_timeout_seconds
        )
    
    elif provider_name == "openai_compatible":
        # 如果配置了单独的 embedding base URL，则使用；否则使用通用的 base URL
        embedding_base_url = (
            settings.openai_compatible_embedding_base_url 
            if settings.openai_compatible_embedding_base_url 
            else settings.openai_compatible_base_url
        )
        # 如果配置了单独的 embedding API key，则使用；否则使用通用的 API key
        embedding_api_key = (
            settings.openai_compatible_embedding_api_key 
            if settings.openai_compatible_embedding_api_key 
            else settings.openai_compatible_api_key
        )
        return OpenAICompatibleProvider(
            model=model or settings.openai_compatible_embedding_model,
            api_key=embedding_api_key,
            base_url=embedding_base_url,
            timeout=settings.llm_timeout_seconds
        )
    
    else:
        raise ValueError(f"不支持的 Embedding Provider: {provider_name}")

