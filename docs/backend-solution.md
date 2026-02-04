# Echoman 后端方案设计

> **运行口径快照（2026-02-04）**
> - 向量库：已统一为 **Chroma**（不使用 pgvector）。
> - 归并流程：event_merge（历史名 halfday_merge）+ global_merge，每日 4 轮（MORN/AM/PM/EVE）。
> - 整体归并：候选召回 Top-K=3、相似度阈值 0.5、LLM 置信度阈值 0.75。
> - 新建 Topic 热度截断：`global_merge_new_topic_keep_ratio=1.0`（全部保留）。
> - 采集侧噪音过滤：在入库前拦截“点击查看更多实时热点”等噪音条目。

## 目标与范围

- 聚合平台：微博、知乎、今日头条、新浪新闻、网易新闻、百度热搜、虎扑。
- 采集策略：每天 8 次（8:00-22:00，每 2 小时一次），各平台默认抓取前 30 条（实际受平台返回与噪音过滤影响）。
- 归并逻辑：两阶段归并（event_merge → global_merge）。
- 对话侧：支持 topic/global 模式，global 模式需要 free_token。

## 总体架构

- **API 服务**：FastAPI（`backend/app/main.py`）
- **调度与任务队列**：Celery + Redis（`backend/app/tasks/*`）
  - 采集：8:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00
  - 归并阶段一：08:05, 12:05, 18:05, 22:05
  - 归并阶段二：08:20, 12:20, 18:20, 22:20
  - 分类指标重算：01:00
- **数据层**：PostgreSQL（业务数据） + Chroma（向量）
- **LLM**：Qwen/OpenAI/Azure 等（通过 Provider 抽象接入）

## 核心流程

### 1) 采集（Ingestion）
- 入口：`IngestionService`（`backend/app/services/ingestion/ingestion_service.py`）
- 入库：`source_items`
- 特点：
  - `dedup_key` 含 `run_id`，确保跨批次不去重
  - 噪音标题/链接入库前过滤
  - period 采用 MORN/AM/PM/EVE

### 2) 归并阶段一（event_merge）
- 入口：`EventMergeService`（`backend/app/services/halfday_merge.py`）
- 处理：
  - 热度归一化（Min-Max + 平台权重 + 全局归一）
  - 标题归一化 + 2-gram Jaccard 初筛
  - 向量聚类（Chroma）
  - LLM 判定同组事件
  - 出现次数过滤（默认 ≥2）
- 输出：`source_items.merge_status` → `pending_global_merge`

### 3) 归并阶段二（global_merge）
- 入口：`GlobalMergeService`（`backend/app/services/global_merge.py`）
- 处理：
  - 召回候选 Topics（优先 `topic_summary` 向量）
  - LLM 关联判定（merge / new）
  - 更新 `topics`、`topic_nodes`、`topic_period_heat`
  - 生成/更新摘要并写入摘要向量
  - 触发前端数据刷新（`FrontendUpdateService`）

### 4) 分类统计
- 服务：`CategoryMetricsService`（`backend/app/services/category_metrics_service.py`）
- 数据表：`category_day_metrics`
- 触发：每日 01:00 + 归并完成后刷新当日指标

### 5) 对话（RAG / Free Mode）
- 入口：`/chat/ask`（`backend/app/api/v1/chat.py`）
- 模式：
  - topic：基于指定话题检索
  - global：自由模式（需 free_token）
- 支持非流式与 SSE 流式

## 关键数据模型（与实现一致）

- `source_items`：采集原子项，含 `period`、`merge_status`、`heat_normalized`
- `topics`：主题表，含 `current_heat_normalized`、`category`、`summary_id`
- `topic_nodes`：时间线节点
- `topic_period_heat`：周期热度（MORN/AM/PM/EVE）
- `summaries`：摘要快照（full/incremental/placeholder）
- `embeddings`：pgvector 元数据表（运行时向量写入 Chroma）
- `llm_judgements`：LLM 判定记录
- `chats` / `chat_messages` / `citations`：对话与引用
- `runs_ingest` / `runs_pipeline`：运行记录
- `category_day_metrics`：分类日指标
- `topic_item_mv`：物化视图（RAG/Agent 查询）

## 向量与检索策略

- 向量库：Chroma（`backend/app/services/vector_service.py`）
- 存储对象：`source_item`、`topic_summary`
- global_merge 优先检索 `topic_summary` 向量

## 采集连接器现状

- Scrapers 路径：`backend/scrapers/*`
- 平台：weibo / zhihu / toutiao / sina / netease / baidu / hupu
- 实际采集条数由各 scraper 返回结果决定，默认 limit=30

## API 概览

- 详见 `docs/api-spec.md`（仅包含已实现接口）
- 路由入口：`backend/app/api/__init__.py`

## 配置与环境

- 配置文件：`backend/app/config/settings.py`
- 环境模板：`env.template`
- 关键配置：
  - `vector_db_type=chroma`
  - `global_merge_*` / `halfday_merge_*` / `platform_weights`
  - `rag_*` / `free_mode_*` / `classifier_*`

## 运行与部署

- 启动后端：`python backend.py` 或按 `HOW_TO_START.md`
- Celery worker/beat：由 `start.sh`/`stop.sh` 管理（如需）

---

## 变更记录

- **v2.1 (2026-02-04)**
  - 与当前实现对齐：Chroma 向量、event_merge/global_merge、SSE 对话
  - 移除未实现与历史规划内容
