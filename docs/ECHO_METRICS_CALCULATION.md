# 回声指标计算逻辑

## 概述

Echoman 系统使用两个核心指标来衡量热点事件的影响力：

- **回声长度**：事件的持续时间（从首次出现到最后活跃）
- **回声强度**：事件的热度强度（归一化后的相对热度值）

---

## 一、回声长度（Echo Length）

### 1.1 定义

回声长度表示一个事件从首次被发现到最后一次活跃的时间跨度。

### 1.2 计算公式

```python
回声长度（小时） = (last_active - first_seen).total_seconds() / 3600
```

**字段说明**：
- `first_seen`: 事件首次被采集的时间戳
- `last_active`: 事件最后一次更新/活跃的时间戳

### 1.3 计算位置

**代码位置**: `backend/app/api/v1/topics.py` (第95行)

```python
# 计算回声时长（小时数）
length_hours = (topic.last_active - topic.first_seen).total_seconds() / 3600 
    if topic.last_active and topic.first_seen else 0
```

### 1.4 更新机制

回声长度会随着事件的持续更新而增长：

1. **创建新Topic时**：
   ```python
   first_seen = min(item.fetched_at for item in items)
   last_active = max(item.fetched_at for item in items)
   ```

2. **归并到已有Topic时**：
   ```python
   topic.last_active = max(item.fetched_at for item in items)
   # first_seen 保持不变
   ```

### 1.5 前端显示

**代码位置**: `frontend/src/pages/ExplorerPage.tsx`

```typescript
function formatEchoLength(hours: number): string {
  const totalHours = Math.round(hours);
  
  // 不超过1天（24小时），只显示小时
  if (totalHours < 24) {
    return `${totalHours}小时`;
  }
  
  // 超过1天，显示"x天x小时"
  const days = Math.floor(totalHours / 24);
  const remainingHours = totalHours % 24;
  
  if (remainingHours === 0) {
    return `${days}天`;
  }
  
  return `${days}天${remainingHours}小时`;
}
```

**显示示例**：
- `8小时`
- `1天2小时`
- `3天`

---

## 二、回声强度（Echo Intensity）

### 2.1 定义

回声强度表示事件在归并周期内的归一化热度值，反映事件相对于其他事件的热度水平。

> 📖 **应用场景**：热度归一化在每次归并流程中执行（每日3次：12:15、18:15、22:15），详见 [merge-logic.md](merge-logic.md#步骤1热度归一化)

### 2.2 计算流程

回声强度的计算分为**四个阶段**：

#### 阶段1: 原始热度采集

每个平台的热点数据都带有原始热度值（`heat_value`）：

| 平台 | 热度字段示例 |
|------|------------|
| 微博 | 热度值（数值） |
| 知乎 | 热度值 |
| 今日头条 | 热度值 |
| 新浪 | 可能无热度值 |

**代码位置**: 各爬虫模块 `backend/scrapers/`

#### 阶段2: 平台内Min-Max归一化

对每个平台内的数据进行归一化到 **0-1** 范围。

**代码位置**: `backend/app/services/heat_normalization.py` (第63-96行)

```python
# 获取该平台的热度值列表
heat_values = [item.heat_value for item in platform_items if item.heat_value is not None]

# 如果该平台无热度值，使用默认值 0.5
if not heat_values:
    for item in platform_items:
        item.heat_normalized = 0.5
    continue

# Min-Max 归一化
min_heat = min(heat_values)
max_heat = max(heat_values)

for item in platform_items:
    if item.heat_value is None:
        item.heat_normalized = 0.5
    elif max_heat == min_heat:
        item.heat_normalized = 0.5  # 所有值相同
    else:
        # Min-Max 归一化: (value - min) / (max - min)
        normalized = (item.heat_value - min_heat) / (max_heat - min_heat)
        item.heat_normalized = normalized
```

**公式**：
```
normalized = (value - min) / (max - min)
```

#### 阶段3: 平台权重加权

不同平台有不同的权重，反映其影响力。

**代码位置**: `backend/app/services/heat_normalization.py` (第98-109行)

```python
# 应用平台权重
total_weight = sum(platform_weights.values())

for item in normalized_items:
    platform_weight = platform_weights.get(item.platform, 1.0)
    
    # 加权: normalized * platform_weight / sum(all_platform_weights)
    weighted = item.heat_normalized * platform_weight / total_weight
    item.heat_normalized = weighted
```

**公式**：
```
weighted = normalized × platform_weight / Σ(all_platform_weights)
```

**平台权重配置** (`backend/app/config.py`):
```python
platform_weights_dict = {
    "weibo": 1.2,      # 微博影响力大
    "zhihu": 1.1,      # 知乎质量高
    "baidu": 1.1,      # 搜索权威
    "toutiao": 1.0,    # 基准
    "douyin": 1.0,     # 短视频平台
    "netease": 0.9,    # 门户网站
    "sina": 0.8,       # 无热度值，降权
    "hupu": 0.8        # 垂直领域
}
```

**权重设计原则**：
- 微博、知乎、百度等主流平台权重较高（1.1-1.2）
- 今日头条、抖音等作为基准（1.0）
- 无热度值或垂直领域平台权重较低（0.8-0.9）

#### 阶段4: 全局归一化

将归并周期内所有事件的热度总和归一化为 1.0，确保同一周期内事件热度具有可比性。

**代码位置**: `backend/app/services/heat_normalization.py` (第111-116行)

```python
# 全局归一化（使归并周期内所有事件热度和为 1.0）
total_heat = sum(item.heat_normalized for item in weighted_items)

if total_heat > 0:
    for item in weighted_items:
        item.heat_normalized = item.heat_normalized / total_heat
```

**归并周期说明**：
- **上午（AM）**：8:00-12:00 的3次采集数据一起归一化
- **下午（PM）**：14:00-18:00 的3次采集数据一起归一化
- **傍晚（EVE）**：20:00-22:00 的2次采集数据一起归一化

**归一化结果**：
- 每个归并周期内所有事件的 `heat_normalized` 之和 = 1.0 (100%)
- 示例：如果有100个事件，平均每个事件的热度 ≈ 0.01 (1%)
- 示例：如果有82个事件，平均每个事件的热度 ≈ 0.0122 (1.22%)

**完整示例**：
```
原始热度：
- 微博A: 1,500,000 → Min-Max: 0.8 → 加权: 0.96 → 全局归一化: 0.015 (1.5%)
- 知乎B: 950 → Min-Max: 0.7 → 加权: 0.77 → 全局归一化: 0.012 (1.2%)
- 新浪C: null → 默认: 0.5 → 加权: 0.40 → 全局归一化: 0.006 (0.6%)

归并周期总和: 1.0（100%）
```

### 2.3 Topic热度聚合

当多个 `source_item` 归并到一个 Topic 时：

**代码位置**: `backend/app/services/global_merge.py` (第546-548行)

```python
current_heat_normalized = sum(
    item.heat_normalized or 0 for item in items
) / len(items) if items else 0
```

**公式**：
```
Topic热度 = Σ(items的heat_normalized) / items数量
```

### 2.4 前端显示

**代码位置**: `backend/app/api/v1/topics.py` (第113行)

```python
"intensity_norm": round(heat_normalized, 4) if heat_normalized > 0 else 0
# 返回 0-1 范围的值
```

**前端转换** (`frontend/src/pages/ExplorerPage.tsx`):

```typescript
{(item.intensity_norm * 100).toFixed(2)}%
// 0.0049 × 100 = 0.49%
```

---

## 三、数据流示例

### 3.1 完整流程图

```
原始数据采集 → 平台内归一化 → 平台权重加权 → 全局归一化 → Topic聚合 → 前端显示
   (热度值)      (0-1范围)      (加权调整)    (总和=1.0)   (平均值)   (×100%)
```

### 3.2 实际数据示例

假设某半日时段采集到以下数据：

**Step 1: 原始采集**
```
微博事件A: heat_value = 850000
微博事件B: heat_value = 620000
知乎事件C: heat_value = 45000
知乎事件D: heat_value = 32000
... (共82个事件)
```

**Step 2: 平台内归一化（微博）**
```
min = 620000, max = 850000
事件A: (850000 - 620000) / (850000 - 620000) = 1.0
事件B: (620000 - 620000) / (850000 - 620000) = 0.0
```

**Step 3: 平台权重加权**
```
假设 total_weight = 8.5
微博权重 = 1.2

事件A: 1.0 × 1.2 / 8.5 = 0.141
事件B: 0.0 × 1.2 / 8.5 = 0.0
```

**Step 4: 全局归一化**
```
假设所有82个事件的加权总和 = 15.5

事件A: 0.141 / 15.5 = 0.0091
事件B: 0.0 / 15.5 = 0.0
```

**Step 5: Topic聚合**
```
假设事件A单独成为一个Topic:
Topic热度 = 0.0091

假设事件B和其他2个item归并:
Topic热度 = (0.0 + 0.005 + 0.008) / 3 = 0.0043
```

**Step 6: 前端显示**
```
Topic A: 0.0091 × 100 = 0.91%
Topic B: 0.0043 × 100 = 0.43%
```

---

## 四、当前问题分析

### 4.1 问题描述

当前系统有82个事件，热度显示普遍偏低（0.21%、0.49%等）。

### 4.2 问题原因

**全局归一化策略不合理**：使所有事件热度总和 = 1.0

```python
# 当前实现
total_heat = sum(item.heat_normalized for item in weighted_items)
for item in weighted_items:
    item.heat_normalized = item.heat_normalized / total_heat
```

**问题**：
- 事件数量越多，单个事件的平均热度越低
- 82个事件 → 平均热度 = 1/82 = 1.22%
- 不直观，难以理解

### 4.3 解决方案

#### 方案1: 相对最大值归一化（推荐）

```python
# 使用最大值归一化
max_heat = max(item.heat_normalized for item in weighted_items)
if max_heat > 0:
    for item in weighted_items:
        item.heat_normalized = item.heat_normalized / max_heat
```

**优点**：
- 最热事件 = 1.0 (100%)
- 其他事件 = 相对于最热事件的百分比
- 直观易懂

**修改位置**: `backend/app/services/heat_normalization.py` 第111-116行

#### 方案2: 分级区间归一化

使用分位数或固定阈值：

```python
# 使用95分位数作为参考
p95 = np.percentile([item.heat_normalized for item in weighted_items], 95)
for item in weighted_items:
    item.heat_normalized = min(item.heat_normalized / p95, 1.0)
```

**优点**：
- 避免极端值影响
- 大部分事件有合理的热度值

#### 方案3: 保持现状，调整展示

- 前端不乘以100
- 改名为"热度占比"
- 添加说明文字

---

## 五、排序逻辑

### 5.1 回声热榜排序规则

**代码位置**: `frontend/src/pages/ExplorerPage.tsx` (第51-76行)

```typescript
const sortedItems = [...items].sort((a, b) => {
  const aHours = Math.floor(a.length_hours);
  const bHours = Math.floor(b.length_hours);
  
  // 1. 先按回声长度（小时数）降序，忽略分钟
  if (aHours !== bHours) {
    return bHours - aHours;
  }
  
  // 2. 回声长度相同时，按回声强度降序
  return b.intensity_norm - a.intensity_norm;
});
```

**排序优先级**：
1. **回声长度优先**（以小时计，忽略分钟）
2. **回声强度次之**（长度相同时比较）

**示例**：
```
1. 事件A: 8小时30分, 强度0.49% → 排序值: (8, 0.0049)
2. 事件B: 8小时10分, 强度0.68% → 排序值: (8, 0.0068)
3. 事件C: 4小时50分, 强度0.95% → 排序值: (4, 0.0095)

排序结果: B > A > C
(长度都是8小时，B强度更高；C虽然强度最高但长度短)
```

---

## 六、API数据格式

### 6.1 Topics列表API

**接口**: `GET /api/v1/topics`

**响应示例**:
```json
{
  "page": 1,
  "size": 50,
  "total": 82,
  "items": [
    {
      "topic_id": "123",
      "title": "人民日报：台湾光复昭示祖国必统一",
      "intensity_raw": 15,
      "intensity_norm": 0.0049,
      "length_hours": 8.0,
      "length_days": 0.33,
      "first_seen": "2025-11-04T10:00:00",
      "last_active": "2025-11-04T18:00:00",
      "platforms": ["百度热搜", "今日头条"],
      "status": "active"
    }
  ]
}
```

**字段说明**：
- `intensity_raw`: 原始强度（Topic包含的source_item数量）
- `intensity_norm`: 归一化强度（0-1范围，前端需×100显示为百分比）
- `length_hours`: 回声长度（小时，精确到小数）
- `length_days`: 回声长度（天，兼容性字段）

---

## 七、总结

### 7.1 回声长度
- ✅ **计算逻辑清晰**：last_active - first_seen
- ✅ **更新机制合理**：随事件持续更新而增长
- ✅ **显示友好**：自动转换为"x天x小时"格式

### 7.2 回声强度
- ⚠️ **全局归一化策略存在问题**：总和=1.0导致值偏小
- ✅ **平台内归一化合理**：Min-Max归一化
- ✅ **平台权重机制良好**：反映不同平台影响力
- 🔧 **建议优化**：采用相对最大值归一化

### 7.3 显示效果
- **回声长度**: 8小时、1天2小时 ✅ 直观
- **回声强度**: 0.49%、0.21% ⚠️ 偏小，不直观

---

## 八、相关文档

- [merge-logic.md](merge-logic.md): 归并逻辑详解（热度归一化的应用场景）
- [backend-solution.md](backend-solution.md): 后端方案设计
- [api-spec.md](api-spec.md): API接口文档

---

## 九、相关代码文件

| 文件路径 | 功能 |
|---------|------|
| `backend/app/services/heat_normalization.py` | 热度归一化服务 |
| `backend/app/services/global_merge.py` | 整体归并服务（Topic热度聚合） |
| `backend/app/api/v1/topics.py` | Topics API（数据返回） |
| `frontend/src/pages/ExplorerPage.tsx` | 前端展示和排序 |
| `backend/app/models/topic.py` | Topic数据模型 |
| `backend/app/models/source_item.py` | SourceItem数据模型 |

---

**文档版本**: v1.0  
**最后更新**: 2025-11-06  
**作者**: Echoman Team

