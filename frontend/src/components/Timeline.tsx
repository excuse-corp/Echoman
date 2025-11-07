import type { TimelineNode } from "../types";
import { getPlatformLabel } from "../constants/platforms";

interface TimelineProps {
  nodes: TimelineNode[];
}

type TimelineGroup = {
  key: string;
  nodes: TimelineNode[];
};

function groupNodesByTimestampAndTitle(nodes: TimelineNode[]): TimelineGroup[] {
  const groups: TimelineGroup[] = [];
  const map = new Map<string, TimelineGroup>();

  for (const node of nodes) {
    // 将时间戳格式化到小时级别，忽略分钟、秒和毫秒
    // 这样同一小时内、同一标题的事件会被合并
    const date = new Date(node.timestamp);
    const timeKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}`;
    const key = `${timeKey}__${node.title}`;
    let group = map.get(key);

    if (!group) {
      group = { key, nodes: [] };
      map.set(key, group);
      groups.push(group);
    }

    group.nodes.push(node);
  }

  return groups;
}

function formatTimestamp(timestamp: string) {
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Timeline({ nodes }: TimelineProps) {
  if (!nodes.length) {
    return <p style={{ color: "var(--text-muted)", fontSize: 14 }}>暂时还没有时间线数据。</p>;
  }

  const groups = groupNodesByTimestampAndTitle(nodes);

  return (
    <div className="timeline">
      {groups.map((group) => {
        const primary = group.nodes[0];
        const platformNames = Array.from(
          new Set(
            group.nodes.map((node) => getPlatformLabel(node.source_platform))
          )
        );

        return (
          <div className="timeline-item" key={group.key}>
            <div className="timeline-date">{formatTimestamp(primary.timestamp)}</div>
            <div className="timeline-platforms">来源：{platformNames.join(" / ")}</div>
            <div className="timeline-title">{primary.title}</div>
            <div className="timeline-body">{primary.content}</div>
            {group.nodes.map((node) => {
              const label = getPlatformLabel(node.source_platform);

              return (
                <a
                  key={node.node_id}
                  href={node.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="timeline-source"
                >
                  {label} 原文 →
                </a>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
