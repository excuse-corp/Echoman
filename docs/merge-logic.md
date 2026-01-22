# Echoman 归并逻辑（最新）

## 整体框架
- **每日四个时段**：08:05 / 12:05 / 18:05 / 22:05 触发阶段一；08:20 / 12:20 / 18:20 / 22:20 触发阶段二。
- **两阶段**：
  1. **阶段一：新事件归并（halfday_merge/event_merge）** —— 去噪与合并当期重复新闻，输出 `pending_global_merge`。
  2. **阶段二：整体归并（global_merge）** —— 与历史 Topic 库比对，决定并入旧 Topic 或创建新 Topic，并更新摘要、分类、热度。

## 阶段一：新事件归并（去噪）
- **输入**：同一归并周期内采集到的 `source_items`，`merge_status=pending_event_merge`。
- **周期命名**：按采集小时切分 period：`<10 → MORN`，`<14 → AM`，`<18 → PM`，其余 `EVE`。
- **预处理**：标题标准化（全角转半角、去标点、数字归一化、小写）。
- **采集侧噪音过滤**：拦截误操作条目（如“点击查看更多实时热点”或列表页链接），避免进入归并与入库。
- **向量化**：标题+摘要 → Embedding（Chroma `source_item_<id>` 持久化）。
- **聚类**：
  - 余弦相似度阈值 `0.80`。
  - 标题 2-gram Jaccard 阈值 `0.40` 辅助过滤。
  - 贪心分组得到候选事件组。
- **LLM 精判**：对候选组判定是否同一事件；`confidence >= 0.8` 视为同组，否则拆成单条。
- **出现次数筛选**：`occurrence_count >= 2` 保留，其他标记 `discarded`。
- **输出**：保留条目标记 `pending_global_merge`，带 `period_merge_group_id` 与 `occurrence_count`。

## 阶段二：整体归并（关联历史）
**目标**：把阶段一保留的事件组与历史 Topic 关联，构建时间线，更新前端可见数据。

### 关键参数
- 候选时间窗：最近 **180 天** 内的 active Topic。
- 候选数量：Top-K **3**（硬上限）。
- 相似度过滤：Chroma 相似度 ≥ **0.50**（距离转相似度）。
- LLM 置信度：`decision=merge` 且 `confidence ≥ 0.75` 才并入旧 Topic。
- 批量上限：每轮最多处理 **200** 个事件组。
- Token 控制：prompt≈2500，候选摘要截断 200，completion 300。
- 向量库：纯 **Chroma**，集合 `echoman_embeddings`，对象类型 `source_item` / `topic_summary`（已弃用 pgvector）。
- 新建 Topic 热度截断：`GLOBAL_MERGE_NEW_TOPIC_KEEP_RATIO`（默认 1.0，当前配置 1.0）。当前不进行截断，全部新建 Topic 保留。

### 流程
1. **代表项**：每组取一条代表 item（标题+摘要）。
2. **向量召回**（主路径）  
   - 用代表项向量检索 `topic_summary` 向量；时间窗 180 天；Top-K=3；低于 0.5 直接丢弃。  
   - 若召回失败/为空，回退取最近活跃 Topic（≤3）交给 LLM 判定。
3. **LLM 关联判定**  
   - 输入：代表项 + 候选 Topic（标题+摘要截断 200）。  
   - 输出 JSON：`merge/new`、`target_topic_id`、`confidence`。满足阈值则合并，否则新建。
4. **合并路径**  
   - 追加 TopicNodes；更新 `last_active`、`intensity_total`、`TopicPeriodHeat`、`current_heat_normalized/heat_percentage`（若本期更高则更新峰值）。  
   - 若 Topic 缺摘要或摘要向量，**即时写占位摘要+向量**，再做增量摘要。
5. **新建路径**  
   - 创建 Topic；写节点与半日热度。  
   - 同步写占位摘要+向量（可被后续召回命中），批量阶段生成完整摘要并覆盖向量。  
   - 调用 LLM 分类写入 `category`、`category_confidence`。
6. **摘要与向量**  
   - 占位摘要：同步，确保 Chroma 可检索。  
   - 完整摘要：批量并发（默认并发 5），完成后重写 `topic_summary_*` 向量。
7. **前端与指标刷新**  
   - 更新 `system_config.last_merge_time`；刷新 Topic 节点计数；重算 `category_day_metrics`。  
   - 运行记录写入 `runs_pipeline`（stage=global_merge；另有 merge_completed 辅助记录）。

### 输出
- 更新的 `topics`、`topic_nodes`、`topic_period_heat`、`summaries`（占位+完整）。
- Chroma 向量：`source_item_*`、`topic_summary_*`。
- 运行日志：`runs_pipeline`。

## 近期改动要点
- 新增晨间归并时段：08:05（阶段一）/08:20（阶段二），period=MORN。  
- 阶段二候选时间窗由 7 天扩至 **180 天**；候选数量固定 **Top-K=3**。  
- 新建/合并时**同步写占位摘要+向量**，防止同一轮出现重复 Topic。  
- 新建 Topic 热度截断：`GLOBAL_MERGE_NEW_TOPIC_KEEP_RATIO` 支持按热度比例保留（默认 1.0）；当前配置 1.0，不进行截断。  
- 纯 Chroma 模式（不再使用 pgvector）；摘要向量作为主要召回索引。  
- 晨间首轮因采集时间高度集中，部分 Topic 的 `length_hours` 可能接近 0，属正常；前端可显示为“低于2小时”以避免 0 时长的视觉噪声。  

## 前端关注点
- 归并完成时间：08:20 / 12:20 / 18:20 / 22:20；前端可通过 `system_config.last_merge_time` 或最新 Topics 的 `updated_at` 变化检测刷新。  
- 热度、分类、摘要在阶段二完成后保证一致性。  
