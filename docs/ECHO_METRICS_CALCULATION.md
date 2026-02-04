# 回声指标计算逻辑

> 更新时间：2026-02-04

## 概述

Echoman 使用两类核心指标衡量事件影响力：

- **回声长度（Echo Length）**：事件持续时间
- **回声强度（Echo Intensity）**：归并周期内热度占比的历史峰值

说明：
- 列表接口返回 `intensity_raw`（Topic 累计节点数）与 `intensity_norm`（Topic 历史峰值热度，0-1）。

---

## 一、回声长度（Echo Length）

### 1.1 定义与公式

```
回声长度（小时） = (last_active - first_seen).total_seconds() / 3600
```

- `first_seen`：首次发现时间
- `last_active`：最后活跃时间

### 1.2 计算位置

- `backend/app/services/global_merge.py`：创建/归并 Topic 时更新 `first_seen`/`last_active`
- `backend/app/api/v1/topics.py`：列表接口计算 `length_hours`
- `backend/app/api/v1/topics.py`：详情接口计算 `length_display`（`x天x小时`）

### 1.3 更新机制

- **新建 Topic**：
  - `first_seen = min(items.fetched_at)`
  - `last_active = max(items.fetched_at)`
- **归并到已有 Topic**：
  - `last_active = max(items.fetched_at)`
  - `first_seen` 不变

---

## 二、回声强度（Echo Intensity）

### 2.1 定义

回声强度来源于**归并周期内**的归一化热度（0-1）。

- 每个归并周期内所有事件 `heat_normalized` 之和 = 1.0
- Topic 的当前周期热度 = 本次归并进来的 `items` 的 `heat_normalized` 之和
- Topic 的 `current_heat_normalized` 取**历史周期峰值**

### 2.2 热度归一化流程

**实现位置**：`backend/app/services/heat_normalization.py`

1) **平台内 Min-Max 归一化**
```
normalized = (value - min) / (max - min)
```

2) **平台无热度值处理**
- `sina/hupu` 等无热度值平台，默认 `0.5`

3) **平台权重加权**
```
weighted = normalized * platform_weight / sum(all_platform_weights)
```

4) **全局归一化（周期内总和=1）**
```
heat_normalized = weighted / sum(all_weighted)
```

### 2.3 平台权重（当前配置）

配置位置：`backend/app/config/settings.py`

```
weibo:   1.2
zhihu:   1.1
baidu:   1.1
toutiao: 1.0
netease: 0.9
sina:    0.8
hupu:    0.8
```

### 2.4 Topic 热度聚合

实现位置：`backend/app/services/global_merge.py::_update_topic_heat`

```
Topic 当前周期热度 = Σ(items.heat_normalized)
```

- 写入 `topic_period_heat`：
  - `heat_normalized`（0-1）
  - `heat_percentage = heat_normalized * 100`
- 更新 `topics.current_heat_normalized`（跨周期峰值）

### 2.5 接口返回字段

- `/topics` 与 `/topics/today`：
  - `intensity_raw` = `topics.intensity_total`
  - `intensity_norm` = `topics.current_heat_normalized`

- `/topics/{topic_id}`：
  - `current_heat_normalized`
  - `heat_percentage`

---

## 三、归并周期说明

归并周期由 `HeatNormalizationService.calculate_period()` 计算：

- `MORN`：< 10:00
- `AM`：< 14:00
- `PM`：< 20:00
- `EVE`：≥ 20:00

归一化在阶段一（event_merge）前执行，对应时间点：
- 08:05 / 12:05 / 18:05 / 22:05

---

## 四、相关代码文件

| 文件路径 | 功能 |
|---------|------|
| `backend/app/services/heat_normalization.py` | 热度归一化 |
| `backend/app/services/global_merge.py` | Topic 热度聚合与峰值更新 |
| `backend/app/api/v1/topics.py` | 回声长度/强度的接口输出 |
| `backend/app/models/topic.py` | Topic 模型字段 |
| `backend/app/models/source_item.py` | 采集项热度字段 |

---

**文档版本**：v2.0
