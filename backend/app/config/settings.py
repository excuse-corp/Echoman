"""
应用配置管理

使用 pydantic-settings 从环境变量加载配置
"""
import json
from typing import Dict, List
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置"""
    
    # ========== 基础配置 ==========
    env: str = Field(default="development", description="运行环境")
    debug: bool = Field(default=True, description="调试模式")
    app_name: str = Field(default="Echoman", description="应用名称")
    api_v1_prefix: str = Field(default="/api/v1", description="API v1路径前缀")
    
    # ========== 数据库配置 ==========
    db_host: str = Field(default="localhost", description="数据库主机")
    db_port: int = Field(default=5432, description="数据库端口")
    db_user: str = Field(default="echoman", description="数据库用户")
    db_password: str = Field(default="echoman_password", description="数据库密码")
    db_name: str = Field(default="echoman", description="数据库名称")
    
    @property
    def database_url(self) -> str:
        """构建数据库URL"""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def database_url_sync(self) -> str:
        """构建同步数据库URL（用于Alembic）"""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    # ========== Redis配置 ==========
    redis_host: str = Field(default="localhost", description="Redis主机")
    redis_port: int = Field(default=6379, description="Redis端口")
    redis_password: str = Field(default="", description="Redis密码")
    redis_db: int = Field(default=0, description="Redis数据库")
    
    @property
    def redis_url(self) -> str:
        """构建Redis URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    # ========== Celery配置 ==========
    celery_broker_url: str = Field(default="redis://localhost:6379/1", description="Celery broker")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", description="Celery结果后端")
    
    # ========== 采集调度配置 ==========
    cron_ingest_schedule: str = Field(default="0 8,10,12,14,16,18,20,22 * * *", description="采集Cron表达式")
    cron_halfday_merge_schedule_noon: str = Field(default="15 12 * * *", description="上半日归并Cron")
    cron_halfday_merge_schedule_night: str = Field(default="15 22 * * *", description="下半日归并Cron")
    cron_global_merge_schedule_noon: str = Field(default="30 12 * * *", description="上半日整体归并Cron")
    cron_global_merge_schedule_night: str = Field(default="30 22 * * *", description="下半日整体归并Cron")
    
    # ========== 采集配置 ==========
    enabled_platforms: str = Field(
        default="weibo,zhihu,toutiao,sina,netease,baidu,hupu",
        description="启用的平台列表"
    )
    fetch_limit_per_platform: int = Field(default=30, description="每平台采集条数")
    fetch_timeout_seconds: int = Field(default=10, description="采集超时秒数")
    fetch_max_retries: int = Field(default=3, description="采集最大重试次数")
    
    @property
    def enabled_platforms_list(self) -> List[str]:
        """返回启用的平台列表"""
        return [p.strip() for p in self.enabled_platforms.split(",")]
    
    # ========== 归并配置 ==========
    halfday_merge_min_occurrence: int = Field(default=2, description="半日归并最小出现次数")
    halfday_merge_vector_threshold: float = Field(default=0.85, description="半日归并向量相似度阈值")
    halfday_merge_title_threshold: float = Field(default=0.6, description="半日归并标题Jaccard阈值")
    global_merge_vector_threshold: float = Field(default=0.80, description="整体归并向量相似度阈值")
    global_merge_confidence_threshold: float = Field(default=0.75, description="整体归并LLM置信度阈值")
    global_merge_topk_candidates: int = Field(default=3, description="候选召回数量（最多3个）")
    global_merge_similarity_threshold: float = Field(default=0.5, description="整体归并向量相似度阈值（候选过滤）")
    
    # ========== 热度归一化配置 ==========
    heat_normalization_method: str = Field(default="minmax_weighted", description="热度归一化方法")
    platform_weights: str = Field(
        default='{"weibo":1.2,"zhihu":1.1,"baidu":1.1,"toutiao":1.0,"netease":0.9,"sina":0.8,"hupu":0.8}',
        description="平台权重配置JSON"
    )
    
    @property
    def platform_weights_dict(self) -> Dict[str, float]:
        """返回平台权重字典"""
        return json.loads(self.platform_weights)
    
    # ========== LLM配置 ==========
    llm_provider: str = Field(default="qwen", description="LLM提供商")
    llm_base_url: str = Field(default="http://localhost:8000/v1", description="LLM API基础URL")
    llm_api_key: str = Field(default="sk-xxx", description="LLM API密钥")
    
    # Qwen配置
    qwen_model: str = Field(default="qwen3-32b", description="Qwen模型")
    qwen_embedding_model: str = Field(default="Qwen3-Embedding-8B", description="Qwen嵌入模型")
    qwen_api_base: str = Field(default="http://localhost:8000/v1", description="Qwen API基础URL")
    qwen_api_key: str = Field(default="sk-xxx", description="Qwen API密钥")
    
    # OpenAI配置
    openai_api_key: str = Field(default="", description="OpenAI API密钥")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI模型")
    openai_embedding_model: str = Field(default="text-embedding-3-large", description="OpenAI嵌入模型")
    
    # Azure配置
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API密钥")
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI端点")
    azure_openai_api_version: str = Field(default="2024-02-15-preview", description="Azure API版本")
    azure_deployment_name: str = Field(default="", description="Azure部署名称")
    
    # OpenAI-Compatible配置（支持 Ollama、LM Studio、vLLM 等）
    openai_compatible_base_url: str = Field(default="http://localhost:11434/v1", description="OpenAI兼容服务的基础URL（对话模型）")
    openai_compatible_api_key: str = Field(default="not-needed", description="OpenAI兼容服务的API密钥（某些服务不需要）")
    openai_compatible_model: str = Field(default="llama3", description="OpenAI兼容服务的模型名称")
    openai_compatible_embedding_model: str = Field(default="nomic-embed-text", description="OpenAI兼容服务的嵌入模型名称")
    openai_compatible_embedding_base_url: str = Field(default="", description="OpenAI兼容服务的嵌入模型基础URL（如果与对话模型地址不同则配置）")
    openai_compatible_embedding_api_key: str = Field(default="", description="OpenAI兼容服务的嵌入模型API密钥（如果与对话模型密钥不同则配置）")
    
    # ========== LLM调用配置 ==========
    # 注意：qwen3-32b 只有 32k 上下文，需要合理分配 token 预算
    llm_max_tokens: int = Field(default=2048, description="LLM生成最大Token数（单次回复）")
    llm_context_limit: int = Field(default=32000, description="LLM上下文限制（总Token数）")
    llm_safety_margin: int = Field(default=2000, description="安全边界（为系统prompt预留）")
    llm_temperature: float = Field(default=0.3, description="LLM温度参数")
    llm_timeout_seconds: int = Field(default=60, description="LLM超时秒数")
    llm_max_retries: int = Field(default=3, description="LLM最大重试次数")
    llm_batch_size: int = Field(default=10, description="LLM批处理大小")
    
    # ========== 向量检索配置 ==========
    embedding_dimension: int = Field(default=4096, description="向量维度")
    vector_similarity_metric: str = Field(default="cosine", description="向量相似度度量")
    vector_index_type: str = Field(default="ivfflat", description="向量索引类型")
    
    # Chroma向量数据库配置
    vector_db_type: str = Field(default="chroma", description="向量数据库类型（chroma|postgres）")
    chroma_persist_directory: str = Field(default="./data/chroma", description="Chroma持久化目录")
    chroma_collection_name: str = Field(default="echoman_embeddings", description="Chroma集合名称")
    
    # ========== RAG对话配置 ==========
    # 考虑到 qwen3-32b 的 32k 限制，合理分配上下文预算
    rag_topk: int = Field(default=5, description="RAG召回TopK")
    citation_required: bool = Field(default=True, description="是否强制引用")
    rag_rerank_enabled: bool = Field(default=True, description="是否启用重排序")
    rag_max_context_tokens: int = Field(default=20000, description="RAG最大上下文Token数（包括检索内容）")
    rag_max_completion_tokens: int = Field(default=2000, description="RAG生成回复最大Token数")
    rag_enable_token_optimization: bool = Field(default=True, description="是否启用Token优化")
    
    # ========== 分类配置 ==========
    classifier_provider: str = Field(default="llm", description="分类器提供商")
    classifier_model: str = Field(default="qwen3-32b", description="分类器模型")
    classifier_threshold: float = Field(default=0.6, description="分类器阈值")
    classifier_debounce_delta: float = Field(default=0.25, description="分类防抖Delta")
    category_metrics_window_days: int = Field(default=30, description="分类指标窗口天数")
    
    # ========== 限流配置 ==========
    rate_limit_per_platform: int = Field(default=60, description="每平台限流数")
    rate_limit_window_seconds: int = Field(default=60, description="限流窗口秒数")
    
    # ========== 监控配置 ==========
    prometheus_port: int = Field(default=9090, description="Prometheus端口")
    metrics_enabled: bool = Field(default=True, description="是否启用指标")
    log_level: str = Field(default="INFO", description="日志级别")
    structured_logging: bool = Field(default=True, description="是否使用结构化日志")
    
    # ========== 安全配置 ==========
    secret_key: str = Field(default="your-secret-key-change-in-production", description="密钥")
    access_token_expire_minutes: int = Field(default=1440, description="访问令牌过期分钟数")
    allowed_origins: str = Field(default="http://localhost:3000,http://localhost:5173,http://202.114.234.85:5173", description="允许的CORS源")
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """返回允许的CORS源列表"""
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    # ========== 对象存储配置 ==========
    use_object_storage: bool = Field(default=False, description="是否使用对象存储")
    s3_bucket: str = Field(default="echoman-snapshots", description="S3存储桶")
    s3_region: str = Field(default="us-east-1", description="S3区域")
    s3_access_key: str = Field(default="", description="S3访问密钥")
    s3_secret_key: str = Field(default="", description="S3密钥")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# 全局配置实例
settings = Settings()

