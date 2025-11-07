"""
Token 管理工具

用于管理 LLM 的上下文 Token 限制，确保不超过模型的最大上下文长度
特别针对 qwen3-32b 的 32k 上下文限制进行优化
"""
from typing import List, Dict, Tuple, Optional
import tiktoken


class TokenManager:
    """
    Token 管理器
    
    针对不同模型的上下文限制进行 Token 计数和截断
    """
    
    # 模型上下文限制配置（Token数）
    MODEL_CONTEXT_LIMITS = {
        "qwen3-32b": 32000,
        "qwen2-72b": 32000,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-3.5-turbo": 16385,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
    }
    
    # 保守的安全边界（留给系统prompt和回复）
    SAFETY_MARGIN = 2000  # 保留2k tokens给系统prompt和回复
    
    def __init__(self, model: str = "qwen3-32b", encoding_name: str = "cl100k_base"):
        """
        初始化 Token 管理器
        
        Args:
            model: 模型名称
            encoding_name: tiktoken 编码名称
        """
        self.model = model
        self.context_limit = self.MODEL_CONTEXT_LIMITS.get(model, 32000)
        
        # 初始化 tokenizer
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            # 如果 tiktoken 不可用，使用简单估算（1 token ≈ 4 字符）
            self.encoding = None
            
    def count_tokens(self, text: str) -> int:
        """
        计算文本的 Token 数量
        
        Args:
            text: 输入文本
            
        Returns:
            Token 数量
        """
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            # 简单估算：中文约 1.5 字符/token，英文约 4 字符/token
            # 保守估计用 2 字符/token
            return len(text) // 2
    
    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        计算消息列表的总 Token 数量
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            
        Returns:
            总 Token 数量
        """
        total = 0
        for msg in messages:
            # 角色标记约占 4 tokens
            total += 4
            # 内容
            total += self.count_tokens(msg.get("content", ""))
        
        # 消息结束标记
        total += 3
        
        return total
    
    def truncate_text(
        self,
        text: str,
        max_tokens: int,
        keep_start: bool = True
    ) -> str:
        """
        截断文本到指定 Token 数
        
        Args:
            text: 输入文本
            max_tokens: 最大 Token 数
            keep_start: 是否保留开头（True）还是结尾（False）
            
        Returns:
            截断后的文本
        """
        current_tokens = self.count_tokens(text)
        
        if current_tokens <= max_tokens:
            return text
        
        # 二分查找截断位置
        if keep_start:
            # 保留开头
            ratio = max_tokens / current_tokens
            estimated_chars = int(len(text) * ratio * 0.9)  # 保守估计
            
            truncated = text[:estimated_chars]
            while self.count_tokens(truncated) > max_tokens:
                estimated_chars = int(estimated_chars * 0.9)
                truncated = text[:estimated_chars]
            
            return truncated + "..."
        else:
            # 保留结尾
            ratio = max_tokens / current_tokens
            estimated_chars = int(len(text) * ratio * 0.9)
            
            truncated = text[-estimated_chars:]
            while self.count_tokens(truncated) > max_tokens:
                estimated_chars = int(estimated_chars * 0.9)
                truncated = text[-estimated_chars:]
            
            return "..." + truncated
    
    def truncate_context_chunks(
        self,
        chunks: List[Dict],
        max_tokens: int,
        text_key: str = "content"
    ) -> Tuple[List[Dict], int]:
        """
        截断上下文块列表，确保总 Token 数不超过限制
        
        Args:
            chunks: 上下文块列表 [{"content": "...", ...}, ...]
            max_tokens: 最大 Token 数
            text_key: 文本内容的键名
            
        Returns:
            (截断后的chunks, 实际使用的tokens)
        """
        result = []
        total_tokens = 0
        
        for chunk in chunks:
            text = chunk.get(text_key, "")
            chunk_tokens = self.count_tokens(text)
            
            if total_tokens + chunk_tokens <= max_tokens:
                # 完整添加
                result.append(chunk)
                total_tokens += chunk_tokens
            elif total_tokens < max_tokens:
                # 部分添加
                remaining_tokens = max_tokens - total_tokens
                truncated_text = self.truncate_text(text, remaining_tokens, keep_start=True)
                
                truncated_chunk = chunk.copy()
                truncated_chunk[text_key] = truncated_text
                result.append(truncated_chunk)
                
                total_tokens += self.count_tokens(truncated_text)
                break
            else:
                # 已达上限
                break
        
        return result, total_tokens
    
    def calculate_available_context_tokens(
        self,
        system_prompt: str = "",
        user_query: str = "",
        max_completion_tokens: int = 2000
    ) -> int:
        """
        计算可用于上下文的 Token 数量
        
        Args:
            system_prompt: 系统提示词
            user_query: 用户查询
            max_completion_tokens: 预留给回复的最大 Token 数
            
        Returns:
            可用于上下文的 Token 数量
        """
        # 计算已使用的 tokens
        used_tokens = 0
        
        if system_prompt:
            used_tokens += self.count_tokens(system_prompt)
        
        if user_query:
            used_tokens += self.count_tokens(user_query)
        
        # 计算可用 tokens
        available = self.context_limit - self.SAFETY_MARGIN - used_tokens - max_completion_tokens
        
        return max(0, available)
    
    def optimize_rag_context(
        self,
        query: str,
        context_chunks: List[Dict],
        system_prompt_template: str = "",
        max_completion_tokens: int = 2000,
        text_key: str = "content"
    ) -> Tuple[List[Dict], Dict[str, int]]:
        """
        优化 RAG 上下文，确保不超过模型上下文限制
        
        Args:
            query: 用户查询
            context_chunks: 上下文块列表
            system_prompt_template: 系统提示词模板
            max_completion_tokens: 预留给回复的最大 Token 数
            text_key: 文本内容的键名
            
        Returns:
            (优化后的chunks, token统计信息)
        """
        # 计算可用的上下文 tokens
        available_tokens = self.calculate_available_context_tokens(
            system_prompt=system_prompt_template,
            user_query=query,
            max_completion_tokens=max_completion_tokens
        )
        
        # 截断上下文块
        optimized_chunks, used_tokens = self.truncate_context_chunks(
            chunks=context_chunks,
            max_tokens=available_tokens,
            text_key=text_key
        )
        
        # 统计信息
        stats = {
            "total_context_limit": self.context_limit,
            "safety_margin": self.SAFETY_MARGIN,
            "system_prompt_tokens": self.count_tokens(system_prompt_template),
            "query_tokens": self.count_tokens(query),
            "max_completion_tokens": max_completion_tokens,
            "available_context_tokens": available_tokens,
            "used_context_tokens": used_tokens,
            "original_chunks": len(context_chunks),
            "optimized_chunks": len(optimized_chunks),
        }
        
        return optimized_chunks, stats


def estimate_tokens_simple(text: str) -> int:
    """
    简单的 Token 估算（不依赖 tiktoken）
    
    规则：
    - 中文：约 1.5 字符/token
    - 英文：约 4 字符/token
    - 保守估计：2 字符/token
    
    Args:
        text: 输入文本
        
    Returns:
        估算的 Token 数量
    """
    return len(text) // 2


def get_token_manager(model: str = "qwen3-32b") -> TokenManager:
    """
    获取 Token 管理器单例
    
    Args:
        model: 模型名称
        
    Returns:
        TokenManager 实例
    """
    return TokenManager(model=model)

