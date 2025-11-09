import type { TimelineNode } from "../types";
import { getPlatformLabel } from "../constants/platforms";

interface TimelineProps {
  nodes: TimelineNode[];
}

function formatTimestamp(timestamp: string) {
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimeRange(start: string, end: string) {
  const startDate = new Date(start);
  const endDate = new Date(end);

  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return formatTimestamp(end);
  }

  const sameDay = startDate.toDateString() === endDate.toDateString();

  const formatterDate = new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });
  const formatterTime = new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const startDateLabel = formatterDate.format(startDate);
  const endDateLabel = formatterDate.format(endDate);
  const startTimeLabel = formatterTime.format(startDate);
  const endTimeLabel = formatterTime.format(endDate);

  if (sameDay) {
    return `${startDateLabel} ${startTimeLabel} - ${endTimeLabel}`;
  }

  return `${startDateLabel} ${startTimeLabel} - ${endDateLabel} ${endTimeLabel}`;
}

export function Timeline({ nodes }: TimelineProps) {
  if (!nodes.length) {
    return <p style={{ color: "var(--text-muted)", fontSize: 14 }}>暂时还没有时间线数据。</p>;
  }

  // 后端已经完成聚合，前端直接展示即可，不需要再分组
  return (
    <div className="timeline">
      {nodes.map((node) => {
        // 检查是否有聚合信息（后端已聚合）
        const duplicateCount = Number(node.duplicate_count ?? 0);
        const hasDuplicates = duplicateCount > 1;
        const timeRangeText = hasDuplicates && node.time_range_start && node.time_range_end
          ? formatTimeRange(node.time_range_start, node.time_range_end)
          : formatTimestamp(node.timestamp);

        // 获取平台标签
        const platformLabel = hasDuplicates && node.all_platforms
          ? Array.from(new Set(node.all_platforms.map(p => getPlatformLabel(p)))).join(" / ")
          : getPlatformLabel(node.source_platform);

        const sourceEntries = hasDuplicates && node.all_source_urls
          ? node.all_source_urls.map((url, idx) => {
              const platform = node.all_platforms?.[idx] || node.source_platform;
              const timestamp = node.all_timestamps?.[idx] || node.timestamp;
              return {
                  key: `${node.node_id}-${idx}`,
                  url,
                  label: getPlatformLabel(platform),
                  timestamp
              };
            })
          : [{
              key: String(node.node_id),
              url: node.source_url,
              label: getPlatformLabel(node.source_platform),
              timestamp: node.timestamp
            }];

        return (
          <div className="timeline-item" key={node.node_id}>
            <div className="timeline-date">{timeRangeText}</div>
            <div className="timeline-platforms">来源：{platformLabel}</div>
            <div className="timeline-title">{node.title}</div>
            <div className="timeline-body">{node.content}</div>
            {hasDuplicates && (
              <div className="timeline-report-count">共 {duplicateCount} 次报道</div>
            )}
            <div className="timeline-source-list">
              {sourceEntries.map((entry) => (
                <div className="timeline-source-item" key={entry.key}>
                  <span className="timeline-source-time">{formatTimestamp(entry.timestamp ?? node.timestamp)}</span>
                  <a
                    href={entry.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="timeline-source-link"
                  >
                    {entry.label} 原文 →
                  </a>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
