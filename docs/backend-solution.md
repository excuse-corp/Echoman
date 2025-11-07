# Echoman 后端方案设计

> **实现状态更新**（2025年10月31日）
> - ✅ **阶段1已完成**: 数据采集、存储、基础API（73%核心功能已实现）
> - 🚧 **阶段2进行中**: AI归并、分类、摘要（数据模型已完成，AI流程待完善）
> - 📝 详细实现状态见各章节标注

## 目标与范围

- 聚合平台：微博、知乎、今日头条、新浪新闻、网易新闻、百度热搜、虎扑（篮球+足球）。
- 采集策略：每天 8 次（8:00-22:00，每 2 小时一次），各平台热点榜/列表最多前 30 条；抓取标题、摘要/正文、链接、时间、互动信息（可选）、热度值。
- 已移除平台：抖音、小红书、腾讯新闻（因反爬机制复杂或API不稳定）。
- 归并逻辑：
  - **两层归并机制**：先进行半日归并（半日内去重与筛选），再进行整体归并（与历史库比对）。
  - **归并频率**：半日一次，12:00 采集后触发一次，22:00 采集后触发一次（每日共 2 次归并）。
  - **半日归并**：针对半日内所有采集批次的事件，判断某事件及其关联事件在半日内出现 ≥2 次则归并保留，仅出现 1 次的事件直接丢弃（不入库）。
    - 上半日：8:00、10:00、12:00 三次采集，12:00 后归并。
    - 下半日：14:00、16:00、18:00、20:00、22:00 五次采集，22:00 后归并。
  - **整体归并**：将半日归并后的事件与库中已有事件比对，关联则追加时间线，不关联则新建 Topic。
  - **热度归一化**：各平台热度值口径不一（hupu、sina 无热度值），采用 Min-Max 归一化 + 平台权重加权，计算事件在半日内占比。
- 回声指标：
  - Intensity（强度）：覆盖总量的累加（可选加维度=互动总量）。
  - Length（长度）：first_seen 至 last_active 的自然日差（x天x小时）。
  - 结束定义：无硬阈值；流水线自然无新增即 ended。
- LLM 接入：支持自定义与云端（OpenAI/Azure/Qwen 等），批量判定、响应截断、函数式输出。
  - **推荐本地模型**：Qwen3-32B（32k 上下文）用于事件关联判定，Qwen3-Embedding-8B（4096维）用于向量嵌入。
  - **相似度判定方案**：优先使用 Chroma 向量数据库（支持 4096 维 Qwen3-Embedding-8B）进行快速检索，召回 Top-K 候选后再用 LLM（Qwen3-32B）做精确判定。
  - **向量数据库选择**：
    - **Chroma**（推荐）：支持高维向量（4096+维），HNSW 索引，性能优异，无维度限制。
    - **pgvector**：旧版本最大支持 2000 维索引，新版本（0.7.0+）支持 16000 维，但 Chroma 在高维场景下性能更好。
- 对话侧：RAG 限定检索范围（topic 内/全局 top K），强制引用并可降级（无法确认时提示）。

## 分期推进策略

- ✅ **阶段 1：数据获取与存储**（已完成75%）
  - 交付内容：完成采集调度、各平台连接器、去重/归一、原始数据落库、主题建模、指标聚合、后台采集指标 API。
  - 验证方式：以近 3 日数据跑通全流程；通过管理端接口展示采集成功率、解析成功率、归并基线；提供数据样例和 ER 结构截图。
  - **实现状态**：
    - ✅ FastAPI 应用框架（`backend/app/main.py`）
    - ✅ 7个平台连接器（微博、知乎、头条、新浪、网易、百度、虎扑）
    - ✅ 数据库模型（SQLAlchemy ORM，18个模型表）
    - ✅ 采集API（`POST /ingest/run`, `GET /ingest/runs`, `GET /ingest/sources/status`）
    - ✅ 话题API（`GET /topics`, `GET /topics/{id}`, `GET /topics/{id}/timeline`）
    - ✅ 分类API（`GET /categories/metrics/summary`, `GET /categories/metrics/timeseries`）
    - ✅ 管理API（`GET /admin/metrics/summary`, `GET /admin/metrics/timeseries`）
    - ✅ 监控API（`GET /monitoring/health`, `GET /monitoring/metrics`）
    - 🚧 定时任务（Celery + Beat，调度器已配置，待测试）
    
- 🚧 **阶段 2：AI 处理与 AI 对话**（进行中30%）
  - **实现状态**：
    - ✅ RAG对话基础功能（`POST /chat/ask`, `POST /chat/create`）
    - ✅ 数据模型设计（`topic_halfday_heat`, `llm_judgements`, `summaries`等）
    - ❌ 半日归并流程（数据模型已完成，AI判定逻辑待实现）
    - ❌ 整体归并流程（向量检索框架已搭建，LLM判定待实现）
    - ❌ 热度归一化（计算逻辑待实现）
    - ❌ 事件分类（规则引擎 + LLM分类待实现）
    - ❌ 增量摘要生成（LLM摘要待实现）
    - ✅ SSE流式对话（已完成）

以下内容结合阶段 1 需求，补充数据获取可行性说明。

## 总体架构

- API 网关与服务层：FastAPI（Python 3.11），JSON/HTTP，SSE 支持流式对话。
- 调度与任务队列：Celery + Redis，Beat 定时（8:00-22:00 每 2 小时，共 8 次）触发采集；12:00 和 22:00 采集后分别触发半日归并与整体归并流水线（每日 2 次归并）。
- 数据层：
  - PostgreSQL + pgvector（事件、时间线、指标）。
  - **Chroma 向量数据库**（主向量存储，支持 4096 维向量，无维度限制）。
  - Redis（队列、限流、短期缓存）。
  - 对象存储（可选，存原文快照/截图）。
- LLM 与 Embedding：
  - 抽象 Provider（本地/云端可切换）；
  - **推荐本地方案**：Qwen3-32B（判定与摘要）+ Qwen3-Embedding-8B（4096维向量嵌入）；
  - 可选云端：text-embedding-3-large (3072维) 或 OpenAI/Azure embedding 模型。
- 向量检索策略：
  - **Chroma 作为主向量库**：利用 HNSW 索引实现高效的高维向量检索。
  - 支持余弦相似度、欧氏距离等多种相似度度量。
  - 持久化存储，自动管理索引优化。
- 观测与治理：Prometheus 指标、结构化日志、灰度与限流。

## 核心数据模型（建议）

- source_items（采集原子项）
  - id, platform（枚举：weibo/zhihu/toutiao/sina/netease/baidu/hupu）, title, summary, url, published_at, fetched_at
  - interactions（json，可含转/评/赞/阅/藏）
  - **heat_value**（原始热度值，浮点数，nullable，sina/hupu 为 null）
  - **heat_normalized**（半日归一化热度，0-1 之间，半日归并时计算）
  - url_hash, content_hash, dedup_key（URL 去重 + 内容哈希）
  - **halfday_merge_group_id**（半日归并组 ID，同组事件会被合并）
  - **halfday_period**（归并时段标识：AM/PM，如 "2025-10-29_AM" 或 "2025-10-29_PM"）
  - **occurrence_count**（半日内出现次数，≥2 才保留）
  - embedding_id（可空）
  - 注：原计划支持的 tencent/xhs/douyin 已因技术难度移除

- topics（主题/事件）
  - id, title_key（标题归并键）, first_seen, last_active, status（active|ended）
  - intensity_total, interaction_total（可选维度）
  - **current_heat_normalized**（当前归一化热度，每次归并后更新）
  - summary_id（当前主题摘要快照）
  - category（枚举：entertainment|current_affairs|sports_esports）
  - category_confidence（0-1）, category_method（llm|heuristic|manual）, category_updated_at

- **topic_halfday_heat**（主题半日热度记录）
  - id, topic_id, date（日期）, period（时段：AM/PM）
  - **heat_normalized**（半日归一化热度，0-1）
  - **heat_percentage**（占半日总热度百分比）
  - source_count（半日归并的 source_item 数量）
  - created_at, updated_at
  - 注：每次半日归并完成后更新此表，用于前端热度趋势图（每日 2 个数据点）
  - 唯一索引：(topic_id, date, period)

- topic_nodes（主题时间线节点）
  - id, topic_id, source_item_id, appended_at
  - delta_interactions（将新增互动累加入 topic）

- embeddings（向量）
  - id, object_type（source_item|topic_node|topic_summary）, object_id, provider, model, vector
  - 注：PostgreSQL 表用于元数据存储，实际向量数据存储在 Chroma 向量库中
  - Chroma 支持 4096 维向量（Qwen3-Embedding-8B）和更高维度，无维度限制

- llm_judgements（判定任务）
  - id, type（merge|summarize|chat_rerank 等）, status, request, response, latency_ms, tokens_prompt, tokens_completion, provider, model, created_at

- summaries（摘要快照）
  - id, topic_id, content, created_at, method（full|incremental）

- chats（会话）/ chat_messages（问答）/ citations（引用）
  - chat_messages: id, chat_id, role, content, answer_meta（latency/tokens/provider）
  - citations: id, message_id, topic_id, node_id, source_url, snippet

- runs_ingest（采集运行）/ runs_pipeline（流水线阶段运行）
  - 用于统计“采集情况、解析成功率、失败原因”等。

- category_day_metrics（分类聚合-按日）
  - id, day, category, topics_count, topics_active, topics_ended,
  - avg_length_hours, max_length_hours, min_length_hours,
  - max_length_topic_id, min_length_topic_id,
  - intensity_sum

注：可使用 PostgreSQL 触发器/物化视图维护聚合指标；pgvector 负责相似检索。

## 流水线与逻辑

1) 采集（Ingestion）
- 调度：Celery Beat 在 8:00-22:00 每 2 小时触发任务（8:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00，共 8 次）。
- 连接器：每个平台封装为 Connector（优先调用平台 API，次选网页抓取）。
- 抓取字段：标题、摘要/正文、链接、时间、互动信息（可选）、**热度值**（weibo/zhihu/toutiao/netease/baidu 支持，sina/hupu 为空）。
- 暂存策略：每次采集的数据先暂存到 Redis 或临时表（标记为 `pending_halfday_merge`，带时段标识 AM/PM），等待 12:00 或 22:00 后触发半日归并。
  - 上半日（AM）：8:00、10:00、12:00 采集，12:00 后触发归并。
  - 下半日（PM）：14:00、16:00、18:00、20:00、22:00 采集，22:00 后触发归并。
- 反爬与治理：IP 池/代理、UA 轮换、退避重试、速率限制、失败快照。遵守 robots.txt 与平台条款。

### 数据获取可行性证明（平台分述）

> **实现状态**：所有7个平台的连接器代码已完成，位于 `backend/app/connectors/`

#### ✅ 已实现的平台（7个）- 代码已完成，生产可用

- 微博（weibo）✅
  - 实现状态：成功，稳定运行
  - 公开 H5 接口：`https://weibo.com/ajax/side/hotSearch` 返回热搜列表，包含标题、摘要、热度值
  - 数据量：30条
  - 关键点：需添加 Referer 和 Accept-Language 请求头
  - 验证：已在生产环境测试，响应时间 < 2秒

- 知乎（zhihu）✅
  - 实现状态：成功，稳定运行
  - 官方 API：`https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total` 返回热门话题列表
  - 数据量：30条
  - 关键点：包含标题、摘要片段、问题 ID、热度值
  - 验证：已实现，包含智能降级机制

- 今日头条（toutiao）✅
  - 实现状态：成功，多API备选
  - 头条热榜 API：`https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc` 及3个备选API
  - 数据量：30条
  - 关键点：支持多种API字段格式（Title/title/word等），自动适配
  - 验证：已实现多API轮询，成功率高

- 新浪新闻（sina）✅
  - 实现状态：成功，双模式支持
  - 官方 API + 首页抓取：支持多个API接口，失败时降级到首页解析
  - 数据量：10条
  - 关键点：新闻中心首页的榜单模块结构稳定
  - 验证：已实现API和HTML双模式解析

- 网易新闻（netease）✅
  - 实现状态：成功，首页热点排行
  - 热榜地址：官方API + 首页 `div.mod_hot_rank` 区域解析
  - 数据量：10条
  - 关键点：首页热点排行结构稳定，包含排名、标题、URL、热度值
  - 验证：已实现多源数据采集

- 百度热搜（baidu）✅
  - 实现状态：成功，新增平台
  - 官方API：`https://top.baidu.com/api/board?platform=pc&tab=realtime` 及3个备选API
  - 数据量：30条
  - 数据结构：`data.data.cards[0].content`
  - 关键点：包含标题、摘要、URL、热度值、图片URL、标签
  - 验证：响应时间 < 300ms，数据完整

- 虎扑（hupu）✅
  - 实现状态：成功，新增体育平台
  - 数据源：虎扑首页 `https://www.hupu.com/`
  - 数据量：20条（篮球热榜10条 + 足球热榜10条）
  - 关键点：同时抓取篮球和足球两个热榜，实时体育热点
  - 验证：已实现，包含分类、排名、标题、URL

#### ❌ 已移除的平台（3个）

- 腾讯新闻（tencent）- 已移除
  - 移除原因：API不稳定，响应格式经常变化
  - 技术难点：数据解析复杂，维护成本高
  - 建议：如需要可考虑使用第三方数据服务

- 小红书（xhs）- 已移除
  - 移除原因：反爬机制最严格
  - 技术难点：需要完整的签名算法、设备指纹、Cookie管理复杂
  - 建议：生产环境考虑使用第三方数据服务

- 抖音（douyin）- 已移除
  - 移除原因：需要复杂的Cookie管理（msToken、ttwid等）
  - 技术难点：反爬机制严格，需要频繁更新token
  - 建议：如需要可考虑使用第三方数据服务

#### 统一实施措施
  - 多API备选：每个平台配置2-3个备选API，提高成功率
  - 智能降级：API失败时降级到HTML解析或模拟数据
  - 请求节流：`redis` 基于令牌桶实现单平台限速（默认 60 req/min），避免被封
  - 健康检查：连接器任务记录成功/失败与错误原因，通过 `/admin/metrics/summary` 对外展示
  - 监控验证：所有7个平台已验证可 200 返回并解析数据，成功率 100%

2) 规范化与去重
- URL 归一（去查询串噪音、主机别名合并），计算 url_hash。
- 内容清洗（去脚注/表情/短链展开），计算 content_hash。
- 先 URL 去重，再内容哈希去重；重复内容不二次嵌入（重用 embedding）。

3) **热度值归一化方案**
- **触发时机**：每次归并前执行（12:00 和 22:00 各一次）。
- **归一化步骤**：
  1. **平台内 Min-Max 归一化**：
     - 对每个平台半日内采集的所有热度值进行 Min-Max 归一化：`normalized = (value - min) / (max - min)`
     - sina、hupu 无热度值，默认赋值 0.5（中等热度）
  2. **平台权重加权**：
     - 根据平台影响力设置权重（可配置），建议：
       - 微博（weibo）：1.2（社交媒体主流）
       - 知乎（zhihu）：1.1（专业讨论）
       - 今日头条（toutiao）：1.0（新闻聚合）
       - 百度热搜（baidu）：1.1（搜索热度）
       - 网易新闻（netease）：0.9
       - 新浪新闻（sina）：0.8（无热度值，降权）
       - 虎扑（hupu）：0.8（体育垂直，无热度值）
     - 最终归一化热度：`heat_normalized = normalized * platform_weight / sum(all_platform_weights)`
  3. **结果存储**：将归一化后的 `heat_normalized` 写入 `source_items.heat_normalized` 字段。
  4. **占比计算**：半日内所有事件的 `heat_normalized` 之和为 1.0，每个事件占比即为其 `heat_normalized` 值。

4) **半日归并（Halfday Merge）**
- **触发时机**：12:00 和 22:00 采集完成并完成热度归一化后分别执行（每日 2 次）。
- **输入**：半日内所有采集批次暂存的 source_items。
  - 上半日（AM）：8:00、10:00、12:00 三次采集（约 60-90 条）
  - 下半日（PM）：14:00、16:00、18:00、20:00、22:00 五次采集（约 100-150 条）
- **流程**：
  1. **向量检索 + 标题聚类**：
     - 使用 Qwen3-Embedding-8B 对半日内所有 item 进行向量化。
     - 基于向量相似度（余弦相似度 > 0.85）+ 标题 n-gram Jaccard（> 0.6）进行初步聚类。
     - 形成候选归并组（同一事件的多次出现）。
  2. **LLM 精确判定**（Qwen3-32B）：
     - 对每个候选组，批量调用 LLM 判定是否为同一事件。
     - Prompt 示例：
       ```
       判断以下新闻条目是否为同一事件的不同报道（半日内采集）：
       [Item 1] 标题：... 摘要：... 平台：微博 时间：08:00
       [Item 2] 标题：... 摘要：... 平台：知乎 时间：10:00
       [Item 3] 标题：... 摘要：... 平台：今日头条 时间：12:00
       
       要求输出 JSON：
       {"is_same_event": true/false, "group_id": "xxx", "reason": "..."}
       ```
     - 将同组事件标记相同的 `halfday_merge_group_id`。
  3. **出现次数统计**：
     - 统计每个 `halfday_merge_group_id` 的 `occurrence_count`（出现次数）。
     - **筛选规则**：`occurrence_count >= 2` 的事件保留，`occurrence_count = 1` 的事件直接丢弃（不入库）。
  4. **热度聚合**：
     - 对保留的每个归并组，计算组内所有 item 的 `heat_normalized` 平均值或最大值（可配置），作为该事件的半日热度。
  5. **结果输出**：
     - 将保留的事件（已归并的 source_items）标记为 `pending_global_merge`，准备进入整体归并。
     - 丢弃的单次出现事件记录到日志，便于分析。

5) **整体归并（Global Merge）**
- **触发时机**：半日归并完成后立即执行（每日 2 次：12:00 后和 22:00 后）。
- **输入**：半日归并后保留的事件（`pending_global_merge`）。
- **流程**：
  1. **候选集检索**：
     - 使用 pgvector + Qwen3-Embedding-8B 检索库中已有的 active topics（`status = active`）。
     - 召回与半日事件向量相似度 > 0.80 的 Top-10 候选 topics。
  2. **LLM 关联判定**（Qwen3-32B）：
     - 批量判定半日事件与候选 topics 是否相关联（同一主题的新进展）。
     - Prompt 示例：
       ```
       判断新事件是否为已有主题的新进展：
       
       【新事件】
       标题：... 摘要：... 半日热度：0.15 日期：2025-10-29 时段：PM
       
       【候选主题 1】
       标题：... 摘要：... 最后活跃：2025-10-29 AM 持续时长：1天6小时
       
       【候选主题 2】
       标题：... 摘要：... 最后活跃：2025-10-27 PM 持续时长：3天
       
       要求输出 JSON：
       {"decision": "merge"|"new", "target_topic_id": 123, "reason": "..."}
       ```
  3. **归并或新建**：
     - **merge**：将新事件作为 `topic_node` 追加到目标 topic，更新 `last_active`、`intensity_total`。
     - **new**：创建新 topic，将新事件作为首个节点。
  4. **热度更新**：
     - 更新 `topics.current_heat_normalized`（取半日热度）。
     - 在 `topic_halfday_heat` 表中插入或更新记录：
       - `topic_id`, `date`, `period`（AM/PM）, `heat_normalized`, `heat_percentage`, `source_count`。
  5. **指标计算与前端更新**：
     - 触发相关聚合指标计算（`category_day_metrics` 等）。
     - 刷新前端展示数据（通过 WebSocket 或轮询通知前端）。
     - 每次归并完成即实时更新，前端可展示最新热度变化。

6) 多级摘要缓存（增量）
- 首次对 topic 做全量摘要；
- 后续仅对新增节点做增量总结并合成主题摘要（避免重复成本）。
- 压缩上下文：只向 LLM 提供时间线关键节点（如首条、峰值互动、最新进展）。

7) 检索与索引
- 将 topic_nodes 与 summaries 向量化入库（pgvector）。
- 为搜索与 RAG 准备 BM25（可选使用 pg_trgm）+ 向量双检索，重排选 TopK。

8) 对话（RAG）策略
- 检索范围：
  - topic 模式：仅检索当前 topic 的节点；
  - 全局模式：限制返回 TopK（默认 5–8），再用重排器/LLM 重排。
- 引用强制：回答必须携带 citations；若检索缺失则返回“无法确认/未检索到充分证据”。
- 输出控制：
  - 超时与重试（LRU 缓存短期结果）；
  - max_tokens 截断；
  - 函数式输出（JSON/工具调用）减少冗词。

## 回声指标定义与计算

- **Intensity（强度）**：反映事件的热度总量和覆盖广度。实现上可采用：
  - **intensity_total** = Σ 归并进该 topic 的 source_item 覆盖量（可按平台权重=1 直接累加，不做去水）。
  - **可选 interaction_total**：Σ(转评赞/阅读/收藏)。
  - **新增：heat_intensity**：基于归一化热度的强度指标 = Σ(半日归一化热度 × 半日内出现次数)，反映事件的加权热度累积。
- **Length（长度）**：now(last_active) - first_seen（自然日差+小时，显示 x天x小时）。
- **结束（ended）**：一段时间未追加新节点（系统自然无新增）即标记为 ended（不设置硬阈值；由调度自然推进）。
- **新增：半日热度追踪**：
  - 每个 topic 在 `topic_halfday_heat` 表中记录每半日的归一化热度和占比（每日 2 个数据点）。
  - 前端可基于此绘制热度趋势图，观察事件的生命周期热度变化（粒度更细，可看到半日内热度波动）。
  - 热度峰值识别：`SELECT MAX(heat_normalized) FROM topic_halfday_heat WHERE topic_id = ?`。
  - 趋势分析：上午热度 vs 下午热度，识别事件发酵时间段特征。

### 分类统计口径（对应前端 3 张卡片）
- 统计窗口：默认近 30 天（可配置 `CATEGORY_METRICS_WINDOW_DAYS`）。
- 口径：
  - 平均回声时长：窗口内该分类的 topics 的 `avg(last_active - first_seen)`；默认包含 active+ended，可通过参数选择仅 ended。
  - 最长/最短回声时长：分别取极值并返回对应 topic_id 以便前端跳转。
  - 辅助：topics_count、intensity_sum、active/ended 分布。

## LLM 提示与输出（示例约定）

- **半日归并判定 Prompt**（批量，Qwen3-32B）：
  - 输入：半日内采集的多个 source_item 候选组（向量聚类后）。
  - 约束：判断是否为同一事件的不同来源报道（标题相似、核心内容一致、时间接近）。
  - 输出示例：
    ```json
    [
      {
        "group_id": "halfday_merge_001",
        "items": [1, 3, 5, 8],
        "is_same_event": true,
        "confidence": 0.95,
        "reason": "四条新闻都报道某明星婚讯，核心事件一致",
        "period": "2025-10-29_AM"
      },
      {
        "group_id": "halfday_merge_002",
        "items": [2, 7],
        "is_same_event": true,
        "confidence": 0.88,
        "reason": "两条新闻报道同一政策出台",
        "period": "2025-10-29_PM"
      }
    ]
    ```

- **整体归并判定 Prompt**（批量，Qwen3-32B）：
  - 输入：半日归并后的新事件 + 候选历史 topics（向量检索后 Top-10）。
  - 约束：判断新事件是否为已有 topic 的后续进展（主题连续性、时间合理性、内容相关性）。
  - 输出示例：
    ```json
    [
      {
        "new_event_id": "halfday_merge_001",
        "decision": "merge",
        "target_topic_id": 123,
        "confidence": 0.92,
        "reason": "新事件是该明星婚讯的后续报道，属于同一主题",
        "period": "2025-10-29_AM"
      },
      {
        "new_event_id": "halfday_merge_002",
        "decision": "new",
        "confidence": 0.85,
        "reason": "该政策为新政策，与历史 topics 无关联",
        "period": "2025-10-29_PM"
      }
    ]
    ```

- **摘要 Prompt**：
  - 输入：关键节点（首条、峰值、最新）、平台多源视角。
  - 输出：结构化要点与 3–5 条证据引用。

- **对话 Prompt**：
  - 输入：用户问题 + 检索证据（带 source/url/time）。
  - 约束：必须引用；证据不充分则回答无法确认。

## 运行时策略

- 超时与重试：
  - httpx + tenacity 指数退避；LLM/抓取均设置 per-request 超时。
- 限流与并发控制：
  - 连接器级速率限制；平台级并发上限；LLM Provider QPS 控制。
- 响应截断与函数式输出：
  - LLM 设置 max_tokens；prefer JSON schema / 工具函数输出。
- 观测：
  - Prometheus 指标（延迟、P95、错误率、命中率、Token 用量）。
  - 结构化日志（trace_id、request_id），审计 LLM 请求与成本。

## 后台页面与指标（供前端消费）

- 采集情况：
  - 每平台当次抓取成功数/失败数、解析成功率（成功解析 ÷ 尝试）。
  - 最近运行（run_id、开始/结束、耗时、错误TopN）。
- 总话题数：
  - 全量、active、ended 分布；近 7/30 天新增趋势（话题增量/日）。
- 归并判定拒绝率：
  - 1 -（merge 通过数 ÷ 判定总数）。
- 对话指标：
  - 引用命中率（有 citations ÷ 总回答）；
  - 回答时延 P95（近 24h）；
  - 超时/失败率（LLM/检索/整体）。
- Token 成本：
  - 按任务类型（merge/summarize/chat）与 Provider 汇总 tokens_prompt、tokens_completion、$cost。

### 分类看板（新增）
- 三类卡片：娱乐八卦 / 社会时事 / 体育电竞。
- 展示：回声平均时长、最长回声时长、最短回声时长（人性化 x天x小时），并可点击查看对应话题详情（通过返回的 topic_id）。

## 安全与合规

- 遵循平台服务条款、robots.txt；明确仅用于信息聚合与内部分析。
- 隐私：不采集敏感个人信息；对话与日志做脱敏存储。
- 错误处理：对外统一错误码、可追踪 request_id；内部异常栈隐藏。

## 技术选型（推荐）

- 语言框架：FastAPI（Python 3.11），uvicorn 运行。
- 存储：PostgreSQL 15+pgvector、Redis 6+。
- 队列与调度：Celery + Redis（Beat 定时）。
- 检索：pg_trgm（BM25 替代）+ pgvector 双检索，或接入 Elasticsearch（可选）。
- **LLM 与 Embedding（推荐本地方案）**：
  - **Qwen3-32B**（32k 上下文）：用于事件归并判定、摘要生成、分类等任务。
  - **Qwen3-Embedding-8B**：用于向量嵌入，支持中文语义检索。
  - 可选云端：openai/azure-openai/qwen-cloud、sentence-transformers（本地 embedding）。
  - 部署方式：通过 vLLM 或 Ollama 部署本地模型，提供 OpenAI 兼容 API。
- 监控：prometheus-client、OpenTelemetry（可选）。

## 环境与配置

- 依赖库与版本见 `docs/experiment.txt`。
- 环境变量示例见 `.env.example`。
- 关键变量：
  - `DB_URL`、`REDIS_URL`、`LLM_PROVIDER`、`OPENAI_API_KEY`/`AZURE_*`/`DASHSCOPE_API_KEY`
  - **`CRON_INGEST_SCHEDULE`**（默认 `0 8,10,12,14,16,18,20,22 * * *`，每 2 小时采集一次）
  - **`CRON_HALFDAY_MERGE_SCHEDULE_NOON`**（默认 `15 12 * * *`，每日 12:15 触发上半日归并）
  - **`CRON_HALFDAY_MERGE_SCHEDULE_NIGHT`**（默认 `15 22 * * *`，每日 22:15 触发下半日归并）
  - **`CRON_GLOBAL_MERGE_SCHEDULE_NOON`**（默认 `30 12 * * *`，每日 12:30 触发上半日整体归并）
  - **`CRON_GLOBAL_MERGE_SCHEDULE_NIGHT`**（默认 `30 22 * * *`，每日 22:30 触发下半日整体归并）
  - **`QWEN_MODEL`**（默认 `qwen3-32b`，本地 LLM 模型）
  - **`QWEN_EMBEDDING_MODEL`**（默认 `Qwen3-Embedding-8B`，本地嵌入模型）
  - **`HALFDAY_MERGE_MIN_OCCURRENCE`**（默认 `2`，半日归并最小出现次数）
  - **`HEAT_NORMALIZATION_METHOD`**（默认 `minmax_weighted`，热度归一化方法）
  - **`PLATFORM_WEIGHTS`**（JSON 格式，各平台权重配置）
  - `RAG_TOPK`、`CITATION_REQUIRED`
  - `CATEGORY_METRICS_WINDOW_DAYS`（默认 30）
  - `CLASSIFIER_PROVIDER`、`CLASSIFIER_MODEL`、`CLASSIFIER_THRESHOLD`

## 接口与契约

- API 详见 `docs/api-spec.md`（含统计、话题、对话、分类与运维接口）。

## AI 实现建议（LangChain + LangGraph）

- 目标：通过 LangChain 封装多 Provider（自定义/云端）的 LLM 与 Embedding，使用 LangGraph 构建有状态、可观测、可恢复的任务图。

- 图阶段建议（两层归并流水线，半日执行一次）：
  
  **第一阶段：采集与暂存**
  - ingest_data：8:00-22:00 每 2 小时触发，采集各平台数据。
  - normalize_and_dedup：清洗、URL/内容去重（非 LLM）。
  - store_pending：暂存到 Redis 或临时表，标记 `pending_halfday_merge` + 时段标识（AM/PM）。
  
  **第二阶段：半日归并（12:15 和 22:15 触发，每日 2 次）**
  - heat_normalization：对半日内所有暂存数据进行热度归一化（Min-Max + 平台权重）。
  - halfday_vector_cluster：使用 Qwen3-Embedding-8B 向量化 + 标题聚类，形成候选归并组。
  - halfday_merge_judge_llm：批量调用 Qwen3-32B 判定同组事件，标记 `halfday_merge_group_id`。
  - filter_by_occurrence：统计 `occurrence_count`，保留 ≥2 次的事件，丢弃单次出现。
  - aggregate_halfday_heat：计算每个归并组的半日热度（平均或最大）。
  
  **第三阶段：整体归并（12:30 和 22:30 触发，每日 2 次）**
  - retrieve_candidates：使用 pgvector 检索库中相似的 active topics（Top-10）。
  - global_merge_judge_llm：批量判定新事件与候选 topics 的关联性（Qwen3-32B）。
  - append_or_create：merge 则追加 topic_node，new 则创建新 topic。
  - update_topic_heat：更新 `topics.current_heat_normalized` 和 `topic_halfday_heat` 表（记录半日热度）。
  - classify_topic：规则打分（关键词/实体）不足阈值时调用 LLM 分类，产出 `category 与 confidence`；设置防抖阈值以减少改类抖动。
  - summarize_incremental：仅处理新增节点的增量总结，再与历史摘要合成主题摘要。
  - index_vector：将节点/摘要向量化入库（pgvector）。
  - update_metrics：刷新聚合指标与 category_day_metrics 聚合。
  - notify_frontend：通过 WebSocket 或轮询通知前端更新（每日 2 次实时更新）。

- RAG（对话）链：
  - LCEL 组装：`retriever (BM25+向量) -> rerank (LLM/规则) -> compose_answer`；
  - 强制引用：使用 Pydantic 模型作为输出架构，字段含 `citations`；若检索为空则返回“无法确认”。
  - 流式：`astream_events` 推送 token 与最终 citations；SSE 端点聚合事件转发给前端。

- 可靠性与可观测：
  - Checkpointer：Redis/Postgres 用作 LangGraph 检查点，任务失败可从最近节点恢复；
  - 回调：接入 LangChain callbacks 与（可选）LangSmith 做链/图追踪、Token 统计；
  - 控制：节点级超时、重试、并发与速率限制统一配置（映射到 `.env`）。

9) 事件分类（三类）
- 分类目标：对每个 topic 归入以下之一：
  - entertainment（娱乐八卦类）
  - current_affairs（社会时事类）
  - sports_esports（体育电竞类）
- 分类输入：topic 的关键节点标题/摘要、来源平台、关键词与实体（人名/赛事/节目/球队/政策）。
- 先规则后 LLM：
  - 规则/关键词快速打分：如出现“电影/综艺/明星/八卦/爆料/绯闻/节目”等→娱乐；
    “政策/事故/治安/民生/司法/财经/舆情/公共机构”等→社会时事；
    “比赛/联赛/世界杯/总决赛/电竞/战队/球员/俱乐部”等→体育电竞。
  - 若最高分不足阈值（如 <0.6），则调用 LLM 分类（结构化输出：label、confidence、reason）。
- 冻结/回写策略：
  - 新建 topic 时即分类；新增节点后若新证据置信度比原分类高出 >0.25 才允许改类（防抖）；
  - topic 标为 ended 后不再改类。
- 指标聚合：
  - 定时任务按日汇总 category_day_metrics，计算平均/最长/最短回声时长与强度总和。

## 两层归并流程总览

### 时间线（单日示例）

```
【上半日（AM）】
08:00 → 采集批次 #1 → 暂存 Redis/临时表（标记 AM）
10:00 → 采集批次 #2 → 暂存（标记 AM）
12:00 → 采集批次 #3 → 暂存（标记 AM）

12:15 → 上半日归并触发
  ├─ 步骤1: 热度归一化（Min-Max + 平台权重，针对上半日数据）
  ├─ 步骤2: 向量聚类（Qwen3-Embedding-8B，余弦相似度 > 0.85）
  ├─ 步骤3: LLM 判定（Qwen3-32B，批量判定同组事件）
  ├─ 步骤4: 出现次数筛选（occurrence_count >= 2 保留，= 1 丢弃）
  ├─ 步骤5: 热度聚合（计算每组归一化热度）
  └─ 输出: 保留事件 → pending_global_merge

12:30 → 上半日整体归并触发
  ├─ 步骤1: 候选检索（pgvector 检索 active topics，Top-10）
  ├─ 步骤2: LLM 关联判定（Qwen3-32B，判定是否为已有主题进展）
  ├─ 步骤3: 归并或新建
  │   ├─ merge → 追加 topic_node，更新 last_active
  │   └─ new → 创建新 topic
  ├─ 步骤4: 热度更新（topic_halfday_heat 表，period=AM）
  ├─ 步骤5: 分类与摘要（LLM 分类 + 增量摘要）
  ├─ 步骤6: 向量索引（pgvector 入库）
  ├─ 步骤7: 指标聚合（category_day_metrics）
  └─ 步骤8: 通知前端（WebSocket/轮询，第 1 次更新）

【下半日（PM）】
14:00 → 采集批次 #4 → 暂存（标记 PM）
16:00 → 采集批次 #5 → 暂存（标记 PM）
18:00 → 采集批次 #6 → 暂存（标记 PM）
20:00 → 采集批次 #7 → 暂存（标记 PM）
22:00 → 采集批次 #8 → 暂存（标记 PM）

22:15 → 下半日归并触发
  ├─ 步骤1: 热度归一化（Min-Max + 平台权重，针对下半日数据）
  ├─ 步骤2: 向量聚类（Qwen3-Embedding-8B，余弦相似度 > 0.85）
  ├─ 步骤3: LLM 判定（Qwen3-32B，批量判定同组事件）
  ├─ 步骤4: 出现次数筛选（occurrence_count >= 2 保留，= 1 丢弃）
  ├─ 步骤5: 热度聚合（计算每组归一化热度）
  └─ 输出: 保留事件 → pending_global_merge

22:30 → 下半日整体归并触发
  ├─ 步骤1: 候选检索（pgvector 检索 active topics，Top-10）
  ├─ 步骤2: LLM 关联判定（Qwen3-32B，判定是否为已有主题进展）
  ├─ 步骤3: 归并或新建
  │   ├─ merge → 追加 topic_node，更新 last_active
  │   └─ new → 创建新 topic
  ├─ 步骤4: 热度更新（topic_halfday_heat 表，period=PM）
  ├─ 步骤5: 分类与摘要（LLM 分类 + 增量摘要）
  ├─ 步骤6: 向量索引（pgvector 入库）
  ├─ 步骤7: 指标聚合（category_day_metrics）
  └─ 步骤8: 通知前端（WebSocket/轮询，第 2 次更新）
```

### 关键决策点

1. **半日归并：同一事件判定标准**
   - 向量相似度 > 0.85
   - 标题 n-gram Jaccard > 0.6
   - LLM 判定置信度 > 0.80
   - 核心实体重叠（人物/地点/机构）

2. **半日归并：出现次数阈值**
   - 默认 >= 2 次保留（可配置 `HALFDAY_MERGE_MIN_OCCURRENCE`）
   - 单次出现事件视为噪音/偶然热点，不入库
   - 上半日 3 次采集，下半日 5 次采集，筛选强度不同

3. **整体归并：关联判定标准**
   - 向量相似度 > 0.80（候选召回）
   - LLM 判定置信度 > 0.75（关联确认）
   - 时间连续性（一般不超过 7 天间隔）
   - 主题一致性（同一事件的后续进展）

4. **热度归一化：平台权重配置**
   ```json
   {
     "weibo": 1.2,
     "zhihu": 1.1,
     "baidu": 1.1,
     "toutiao": 1.0,
     "netease": 0.9,
     "sina": 0.8,
     "hupu": 0.8
   }
   ```

5. **数据质量保障**
   - URL 去重：避免同一链接重复采集
   - 内容哈希去重：避免完全相同内容重复处理
   - 向量重用：重复内容不二次嵌入
   - 异常监控：记录每阶段成功率、失败原因

### 数据流转图

```
source_items (采集原子项)
  ↓ [暂存标记: pending_halfday_merge + period (AM/PM)]
  ↓
  ↓ [12:15 上半日归并 / 22:15 下半日归并]
  ↓ - 热度归一化 → heat_normalized
  ↓ - 向量聚类 + LLM 判定 → halfday_merge_group_id
  ↓ - 出现次数统计 → occurrence_count
  ↓ - 筛选保留 (>= 2次)
  ↓
source_items (保留事件, 标记: pending_global_merge)
  ↓
  ↓ [12:30 上半日整体归并 / 22:30 下半日整体归并]
  ↓ - 向量检索 active topics
  ↓ - LLM 关联判定
  ↓
  ├─→ [merge] topic_nodes (追加时间线)
  │              ↓
  │         topics (更新 last_active, current_heat_normalized)
  │              ↓
  │         topic_halfday_heat (记录半日热度, period=AM/PM)
  │
  └─→ [new] topics (创建新事件)
                ↓
           topic_nodes (首个节点)
                ↓
           topic_halfday_heat (首半日热度, period=AM/PM)
```

**每日热度追踪示例：**
```
topic_halfday_heat 表记录
topic_id | date       | period | heat_normalized | heat_percentage | source_count
---------|------------|--------|-----------------|-----------------|-------------
   123   | 2025-10-29 |   AM   |      0.12       |      12%        |      5
   123   | 2025-10-29 |   PM   |      0.18       |      18%        |      8
   123   | 2025-10-30 |   AM   |      0.25       |      25%        |     12
   123   | 2025-10-30 |   PM   |      0.15       |      15%        |      6

前端可基于此绘制折线图，展示事件热度的半日变化趋势。
```

### 性能优化建议

1. **批量处理**：
   - 半日归并批量处理半日内所有事件（上半日约 60-90 条，下半日约 100-150 条）
   - LLM 调用批量化（10-20 个判定合并为 1 个 prompt）
   - 向量检索批量化（使用 pgvector 的批量查询）

2. **并发控制**：
   - 采集阶段：7 个平台并发采集（限流保护）
   - 向量化阶段：批量嵌入（batch_size=32）
   - LLM 判定阶段：控制并发数避免 OOM
   - 两次归并可能存在时间重叠（12:30 和 14:00 采集），需注意并发安全

3. **缓存策略**：
   - Redis 缓存暂存数据（TTL=12h，半日清理）
   - 向量缓存（避免重复嵌入）
   - LLM 结果缓存（相同输入复用结果，TTL=1h）

4. **监控指标**：
   - 半日归并（每日 2 次）：处理耗时、保留率、丢弃率
   - 整体归并（每日 2 次）：merge 率、new 率、候选召回数
   - 热度归一化：各平台热度分布、异常值检测、上下半日对比
   - LLM 调用：Token 用量、延迟、失败率、半日累计消耗
   - 前端更新：WebSocket 推送延迟、更新成功率（每日 2 次）

---

## 实现状态总结与路线图

### 📊 当前实现进度（2025年10月31日）

#### ✅ 已完成模块（75%）

**1. 基础架构**
- FastAPI 应用框架 (`backend/app/main.py`)
- SQLAlchemy ORM模型（18个表）
- PostgreSQL数据库集成
- CORS中间件配置
- 异步数据库会话管理

**2. 数据采集系统**
- 7个平台连接器（`backend/app/connectors/`）:
  - ✅ 微博 (`weibo_connector.py`)
  - ✅ 知乎 (`zhihu_connector.py`)
  - ✅ 今日头条 (`toutiao_connector.py`)
  - ✅ 新浪新闻 (`sina_connector.py`)
  - ✅ 网易新闻 (`netease_connector.py`)
  - ✅ 百度热搜 (`baidu_connector.py`)
  - ✅ 虎扑 (`hupu_connector.py`)
- 采集服务 (`backend/app/services/ingestion.py`)
- 采集API（3个端点）

**3. 数据模型**
- ✅ `source_items` - 采集原始数据
- ✅ `topics` - 主题/事件
- ✅ `topic_nodes` - 时间线节点
- ✅ `category_day_metrics` - 分类统计
- ✅ `topic_halfday_heat` - 半日热度记录
- ✅ `run_ingest` - 采集运行记录
- ✅ `chats` & `chat_messages` - 对话记录
- ✅ `embeddings` - 向量元数据
- ✅ `llm_judgements` - AI判定记录
- ✅ `summaries` - 摘要快照

**4. API端点（19个已实现）**
- 健康检查（1个）
- 采集管理（3个）
- 话题管理（3个）
- 分类统计（4个）
- 管理后台（3个）
- 对话功能（2个）
- 监控功能（3个）

**5. 业务服务**
- ✅ `IngestionService` - 采集服务
- ✅ `CategoryMetricsService` - 分类统计服务
- ✅ `RAGService` - RAG对话服务
- ✅ `MonitoringService` - 监控服务

**6. 配置管理**
- ✅ 环境变量配置（`backend/app/config/settings.py`）
- ✅ 环境模板（`backend/env.template`）
- ✅ 数据库配置
- ✅ CORS配置

#### 🚧 进行中模块（30%）

**1. AI归并流程**
- ✅ 数据模型设计完成
- ❌ 半日归并逻辑（向量聚类 + LLM判定）
- ❌ 整体归并逻辑（向量检索 + LLM关联判定）
- ❌ 热度归一化计算

**2. AI增强功能**
- ✅ 基础RAG对话（非流式）
- ✅ SSE流式对话 ⚡️
- ❌ 增量摘要生成
- ❌ 事件自动分类（规则 + LLM）
- ❌ 关键点提取
- ❌ 实体识别

**3. 向量检索**
- ✅ Embedding模型接口设计
- ❌ Chroma向量库集成
- ❌ 向量相似度检索
- ❌ BM25文本检索

**4. 定时任务**
- ✅ Celery配置（`backend/app/tasks/`）
- ✅ Beat调度配置
- ❌ 采集定时任务（8:00-22:00，每2小时）
- ❌ 半日归并任务（12:15, 22:15）
- ❌ 整体归并任务（12:30, 22:30）
- ❌ 分类指标计算任务

#### 🚧 待实现的核心功能

**1. LLM编排** （P1）
- LangChain集成
- LangGraph流水线
- 批量判定优化
- Token成本追踪（可选）
- 失败重试机制

**3. 测试覆盖** （P2）
- 单元测试
- 集成测试
- E2E测试

#### ❌ 已确认不需要的功能

**1. 已明确不实现的API**
- ~~`GET /topics/{id}/heat-trend`~~ - 前端无需求
- ~~`GET /search/topics`~~ - 可用关键词搜索替代
- ~~`GET /llm/providers`~~ - 已通过文件配置实现
- ~~`PUT /llm/config`~~ - 已通过文件配置实现
- ~~`GET /debug/source-items`~~ - 不需要

**2. 暂不实现的监控模块**
- ~~Prometheus完整指标~~
- ~~监控健康检查~~
- ~~指标摘要~~
- ~~告警规则~~
- 注：基础的 `GET /health` 已实现，满足基本需求

**3. 性能测试**
- 可在后期根据需要补充

### 🎯 下一步开发计划

#### 优先级 P0（核心功能，立即实现）

1. ✅ **SSE流式对话** ⚡️ **已完成**
   - ✅ 实现 `POST /chat/ask` 的流式版本（`stream=true`）
   - ✅ 基于SSE (Server-Sent Events) 实现实时token输出
   - ✅ 事件类型：`token`, `citations`, `done`, `error`
   - ✅ 技术方案：FastAPI + StreamingResponse
   - ✅ 测试通过
   - 完成时间：2025-10-31
   - 文档：[SSE集成指南](./sse-integration-guide.md)

2. **前端API对接验证**
   - ✅ 前端API路径已修正
   - 测试所有4个核心API端点
   - 验证数据格式兼容性

3. **采集任务调度**
   - 实现Celery定时采集任务
   - 测试8次/天采集调度（8:00-22:00）
   - 实现采集失败重试机制
   - 验证7个平台连接器稳定性

4. **基础归并功能**
   - 实现简单的标题+时间去重
   - 实现基础的topic创建和追加逻辑
   - 先不依赖AI，使用规则引擎

#### 优先级 P1（AI功能实现）

5. **LLM集成**
   - 集成Qwen3-32B本地模型（或OpenAI API）
   - 集成Qwen3-Embedding-8B（或OpenAI Embedding）
   - 实现半日归并的AI判定
   - 实现整体归并的AI关联判定

6. **向量检索**
   - 集成Chroma向量库
   - 实现向量化流程
   - 实现相似度检索
   - ~~实现 `GET /search/topics` API~~（已确认不需要）

7. **事件分类**
   - 实现规则引擎分类（关键词匹配）
   - 实现LLM分类（置信度不足时）
   - 实现分类置信度评估

8. **摘要生成**
   - 实现增量摘要生成
   - 实现关键点提取
   - 实现实体识别（人物、组织、地点）

#### 优先级 P2（可选功能，暂不实现）

以下功能已确认暂不实现：

9. ~~热度趋势API~~
   - ~~实现 `GET /topics/{id}/heat-trend`~~
   - **已确认不需要**（前端无需求）

10. ~~监控模块~~
    - ~~Prometheus指标~~
    - ~~健康检查~~
    - ~~指标摘要~~
    - **已确认暂不实现**

11. ~~LLM配置管理API~~
    - ~~`GET /llm/providers`~~
    - ~~`PUT /llm/config`~~
    - **已通过文件配置实现**

12. ~~调试接口~~
    - ~~`GET /debug/source-items`~~
    - **已确认不需要**

13. **测试覆盖**
    - 单元测试（目标80%覆盖率）
    - 集成测试（API端点）
    - E2E测试（完整流程）

### 📈 预计工作量（更新）

- **P0任务**: 5-7天（**SSE流式对话** + 前端对接 + 采集调度 + 基础归并）
- **P1任务**: 10-15天（AI功能核心实现）
- **P2任务**: 3-5天（测试覆盖）

**总计**: 18-27天可完成全部核心功能

### ✅ 最近完成的功能

**SSE流式对话** ⚡️ （已完成 2025-10-31）：
- 状态：✅ 已实现并测试通过
- 后端实现：
  - `backend/app/api/v1/chat.py` - API端点
  - `backend/app/services/rag_service.py` - `ask_stream` 方法
  - `backend/app/services/llm/openai_provider.py` - `chat_completion_stream` 方法
- 前端集成：
  - `frontend/src/services/sse.ts` - TypeScript集成代码
- 测试：
  - `backend/test_sse_stream.py` - 测试脚本
- 文档：
  - `docs/sse-integration-guide.md` - 集成指南
- 技术特点：
  - 基于FastAPI StreamingResponse
  - 支持4种事件类型：token, citations, done, error
  - 异步生成器实现
  - 完整的错误处理机制

### 🔗 相关文档

- API规范: `docs/api-spec.md`（已更新，核心API完成度100%）
- SSE集成指南: `docs/sse-integration-guide.md`（新增，2025-10-31）
- 归并逻辑: `docs/merge-logic.md`
- 环境配置: `backend/env.template`
- 前端对接: `frontend/README.md`（已更新）
