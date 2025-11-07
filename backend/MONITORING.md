# Echoman 监控与告警系统

## 概述

Echoman后端集成了完整的监控系统，基于Prometheus + Grafana，提供实时性能监控、告警和可视化。

## 监控指标

### 1. 采集指标

- **echoman_ingest_total**: 采集总次数（按平台、状态）
- **echoman_ingest_items_total**: 采集条目总数（按平台）
- **echoman_ingest_duration_seconds**: 采集耗时（按平台）

### 2. 归并指标

- **echoman_merge_halfday_total**: 半日归并总次数
- **echoman_merge_global_total**: 整体归并总次数（按merge/new）
- **echoman_merge_duration_seconds**: 归并耗时

### 3. 主题指标

- **echoman_topics_total**: 主题总数（按active/ended）
- **echoman_topics_created_total**: 创建的主题总数

### 4. LLM调用指标

- **echoman_llm_calls_total**: LLM调用总次数（按类型、提供商、状态）
- **echoman_llm_tokens_total**: Token消耗总数（按类型、prompt/completion）
- **echoman_llm_duration_seconds**: LLM调用耗时

### 5. RAG对话指标

- **echoman_chat_queries_total**: 对话查询总次数（按模式、状态）
- **echoman_chat_duration_seconds**: 对话耗时

### 6. 系统资源指标

- **echoman_system_cpu_percent**: CPU使用率
- **echoman_system_memory_percent**: 内存使用率
- **echoman_system_disk_percent**: 磁盘使用率

## API端点

### 健康检查

```bash
GET /api/v1/monitoring/health
```

返回系统各组件的健康状态：
- 数据库连接
- 采集服务状态
- 系统资源状况

### Prometheus指标

```bash
GET /api/v1/monitoring/metrics
```

返回Prometheus格式的所有指标。

### 指标摘要

```bash
GET /api/v1/monitoring/metrics/summary
```

返回最近24小时的指标统计摘要。

## 部署方式

### 方式1: Docker Compose（推荐）

在`docker-compose.yml`中已包含Prometheus和Grafana服务：

```bash
cd backend
docker-compose up -d prometheus grafana
```

访问：
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000（默认用户名/密码: admin/admin）

### 方式2: 独立部署

#### 安装Prometheus

```bash
# Ubuntu/Debian
sudo apt install prometheus

# 或使用Docker
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

#### 安装Grafana

```bash
# Ubuntu/Debian
sudo apt install grafana

# 或使用Docker
docker run -d \
  --name grafana \
  -p 3000:3000 \
  grafana/grafana
```

## Grafana仪表板配置

### 导入仪表板

1. 访问Grafana (http://localhost:3000)
2. 登录（默认: admin/admin）
3. 添加数据源:
   - 类型: Prometheus
   - URL: http://prometheus:9090（Docker）或 http://localhost:9090（本地）
4. 导入仪表板:
   - 从文件导入: `monitoring/grafana-dashboard.json`

### 主要面板

- **采集成功率**: 实时监控各平台采集成功率
- **主题数量**: 活跃/结束主题统计
- **LLM调用量**: LLM使用情况和Token消耗
- **系统资源**: CPU/内存/磁盘使用率
- **对话延迟**: RAG对话响应时间分布
- **归并耗时**: 半日归并和整体归并性能

## 告警配置

### 示例告警规则

创建`monitoring/alerts.yml`:

```yaml
groups:
  - name: echoman_alerts
    interval: 30s
    rules:
      # 采集失败率过高
      - alert: HighIngestFailureRate
        expr: rate(echoman_ingest_total{status="failed"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "采集失败率过高"
          description: "过去5分钟采集失败率超过10%"
      
      # 磁盘空间不足
      - alert: DiskSpaceLow
        expr: echoman_system_disk_percent > 90
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "磁盘空间不足"
          description: "磁盘使用率超过90%"
      
      # LLM调用失败率过高
      - alert: HighLLMFailureRate
        expr: rate(echoman_llm_calls_total{status="failed"}[5m]) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM调用失败率过高"
          description: "过去5分钟LLM调用失败率超过20%"
      
      # 主题创建停滞
      - alert: TopicCreationStalled
        expr: rate(echoman_topics_created_total[1h]) == 0
        for: 2h
        labels:
          severity: warning
        annotations:
          summary: "主题创建停滞"
          description: "过去2小时未创建新主题"
```

### Alertmanager配置

1. 安装Alertmanager:
```bash
docker run -d \
  --name alertmanager \
  -p 9093:9093 \
  prom/alertmanager
```

2. 配置通知渠道（邮件、Slack、钉钉等）

## 监控最佳实践

### 1. 定期检查

- 每天检查Grafana仪表板
- 关注异常指标和告警

### 2. 性能优化

- 监控LLM Token消耗，优化Prompt
- 监控归并耗时，调整批处理大小
- 监控系统资源，及时扩容

### 3. 容量规划

- 根据主题增长趋势预测存储需求
- 根据LLM调用量预估成本
- 根据系统负载规划硬件升级

### 4. 故障排查

- 采集失败：检查网络、平台API变化
- LLM超时：检查LLM服务可用性
- 数据库慢查询：检查索引、优化查询

## 指标收集最佳实践

### 在代码中记录指标

```python
from app.services.monitoring_service import record_ingest, record_llm_call

# 记录采集指标
start_time = time.time()
try:
    items = await scraper.fetch()
    duration = time.time() - start_time
    record_ingest('weibo', 'success', duration, len(items))
except Exception as e:
    duration = time.time() - start_time
    record_ingest('weibo', 'failed', duration)

# 记录LLM调用指标
start_time = time.time()
response = await llm.chat_completion(messages)
duration = time.time() - start_time
record_llm_call(
    call_type='classify',
    provider='qwen',
    status='success',
    duration=duration,
    prompt_tokens=response['usage']['prompt_tokens'],
    completion_tokens=response['usage']['completion_tokens']
)
```

## 常见问题

### Q: Prometheus无法抓取指标？

A: 检查：
1. 后端服务是否正常运行
2. 网络连接是否正常
3. Prometheus配置文件中的target地址是否正确

### Q: Grafana仪表板无数据？

A: 检查：
1. Prometheus数据源配置是否正确
2. 时间范围选择是否正确
3. PromQL查询语句是否正确

### Q: 如何自定义监控指标？

A: 在`app/services/monitoring_service.py`中添加新的Prometheus指标：

```python
from prometheus_client import Counter

my_custom_metric = Counter(
    'echoman_custom_metric',
    '自定义指标描述',
    ['label1', 'label2']
)

# 记录指标
my_custom_metric.labels(label1='value1', label2='value2').inc()
```

## 生产环境建议

1. **持久化存储**: 为Prometheus和Grafana配置数据持久化
2. **高可用**: 使用Prometheus集群和Grafana HA模式
3. **访问控制**: 配置Grafana用户权限和Prometheus安全认证
4. **备份**: 定期备份Grafana仪表板配置
5. **日志集成**: 结合ELK/Loki进行日志分析

## 参考资料

- [Prometheus文档](https://prometheus.io/docs/)
- [Grafana文档](https://grafana.com/docs/)
- [prometheus_client Python库](https://github.com/prometheus/client_python)

