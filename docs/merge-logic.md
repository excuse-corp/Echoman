# Echoman 归并逻辑（最新）

> 更新时间：2026-02-04

## 整体框架
- **每日四个时段**：08:05 / 12:05 / 18:05 / 22:05 触发阶段一；08:20 / 12:20 / 18:20 / 22:20 触发阶段二。
- **两阶段**：
  1. **阶段一：新事件归并（event_merge / halfday_merge）** —— 去噪与合并当期重复新闻，输出 `pending_global_merge`。
  2. **阶段二：整体归并（global_merge）** —— 与历史 Topic 库比对，决定并入旧 Topic 或创建新 Topic，并更新摘要、分类、热度。

## 阶段一：新事件归并（event_merge）
- **输入**：同一归并周期内采集到的 `source_items`，`merge_status=pending_event_merge`。
- **周期命名**：按小时切分 period：`<10 → MORN`，`<14 → AM`，`<20 → PM`，其余 `EVE`。
- **预处理**：标题标准化（全角转半角、去标点、数字归一化、小写）。
- **采集侧噪音过滤**：拦截误操作条目（如“点击查看更多实时热点”或列表页链接），避免入库与归并。
- **向量化**：标题+摘要 → Embedding（Chroma `source_item_<id>`）。
- **聚类**：
  - 向量相似度阈值 `0.80`。
  - 标题 2-gram Jaccard 阈值 `0.40` 作为辅助筛选。
- **LLM 判定**：对候选组判定是否同一事件；仅作为归并精判。
- **出现次数筛选**：`occurrence_count >= 2` 保留，其他标记 `discarded`。
- **输出**：保留条目标记 `pending_global_merge`，带 `period_merge_group_id` 与 `occurrence_count`。

## 阶段二：整体归并（global_merge）

**目标**：把阶段一保留的事件组与历史 Topic 关联，构建时间线，更新前端可见数据。

### 关键参数（当前实现）
- 候选数量：Top-K **3**。
- 相似度过滤：Chroma 相似度 ≥ **0.50**。
- LLM 置信度：`decision=merge` 且 `confidence ≥ 0.75` 才并入旧 Topic。
- 向量库：纯 **Chroma**（`echoman_embeddings`），对象类型 `source_item` / `topic_summary`。
- 新建 Topic 热度截断：`global_merge_new_topic_keep_ratio`（默认 1.0，当前不截断）。

### 流程
1. **代表项**：每组取一条代表 item（标题+摘要）。
2. **向量召回**：
   - 用代表项向量检索 `topic_summary` 向量；Top-K=3；低于 0.5 丢弃。
   - 若召回为空，回退到最近活跃 Topic（最多 3 条）交给 LLM 判定。
3. **LLM 关联判定**：
   - 输入：代表项 + 候选 Topic（标题+摘要截断）。
   - 输出：`merge/new`、`target_topic_id`、`confidence`。
4. **合并路径**：
   - 追加 `TopicNode`；更新 `last_active`、`intensity_total`。
   - 更新 `TopicPeriodHeat` 与 `current_heat_normalized/heat_percentage`（若本期更高）。
   - 若摘要缺失，生成占位摘要 + 向量；再尝试增量摘要更新。
5. **新建路径**：
   - 创建 `Topic` + `TopicNode` + `TopicPeriodHeat`。
   - 生成占位摘要 + 向量；批量阶段生成完整摘要并覆盖向量。
   - 调用分类服务更新 `category` 与 `category_confidence`。
6. **前端与指标刷新**：
   - 刷新 `topic_item_mv` 物化视图。
   - 重算当日 `category_day_metrics`。

### 输出
- 更新的 `topics`、`topic_nodes`、`topic_period_heat`、`summaries`。
- Chroma 向量：`source_item_*`、`topic_summary_*`。
- 运行日志：`runs_pipeline`（`stage=event_merge/global_merge`；另写入 `merge_completed` 记录）。

## 近期改动要点
- 增加 **MORN** 归并时段（08:05/08:20）。
- 统一 Chroma 作为向量存储与召回。
- Top-K 固定 3，低相似度剔除阈值 0.5。
- 新建 Topic 热度截断默认关闭（1.0）。

## 前端关注点
- 归并完成时间：08:20 / 12:20 / 18:20 / 22:20。
- 热度、分类、摘要在阶段二完成后保证一致性。
