import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { HotspotSummary, TimelineNode, TopicDetail } from "../types";
import { dataSources, getHotspots, getTodayTopics, getTimeline, getTopicDetail } from "../services/api";
import { ConversationConsole } from "../components/ConversationConsole";
import { ThemeToggle } from "../components/ThemeToggle";
import { getPlatformLabel } from "../constants/platforms";

function formatDateTime(timestamp: string) {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return `${year}/${month}/${day} ${hour}:${minute}`;
}

function formatDateOnly(timestamp: string): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hours = date.getHours();
  const period = hours < 12 ? "am" : "pm";
  return `${year}/${month}/${day} ${period}`;
}

function formatRelativeDate(timestamp: string): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffHours < 24) {
    return "今天";
  } else if (diffDays === 1) {
    return "昨天";
  } else if (diffDays === 2) {
    return "前天";
  } else if (diffDays < 7) {
    return `${diffDays}天前`;
  } else {
    return formatDateOnly(timestamp);
  }
}

function formatEchoLength(hours: number): string {
  if (!Number.isFinite(hours) || hours < 0) return "—";

  const totalHours = Math.round(hours);

  // 0 或极短时长，统一提示
  if (totalHours <= 0) {
    return "低于2小时";
  }

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

export function ExplorerPage() {
  const [hotspots, setHotspots] = useState<HotspotSummary[]>([]);
  const [todayTopics, setTodayTopics] = useState<HotspotSummary[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TopicDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineNode[]>([]);
  const [usingFallback, setUsingFallback] = useState(false);
  const [timelineFallback, setTimelineFallback] = useState(false);
  const [detailFallback, setDetailFallback] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [mode, setMode] = useState<"free" | "event">("event");
  const [activeTab, setActiveTab] = useState<"echo" | "today">("echo");

  useEffect(() => {
    let cancel = false;
    getHotspots().then(({ items, fallback }) => {
      if (cancel) return;
      // 排序规则：首先按照回声长度（以小时计，忽略分钟），越长越靠前
      // 如果回声长度一样，按照回声强度排序
      const sortedItems = [...items].sort((a, b) => {
        const aHours = Math.floor(a.length_hours);
        const bHours = Math.floor(b.length_hours);
        
        // 先按回声长度（小时数）降序
        if (aHours !== bHours) {
          return bHours - aHours;
        }
        
        // 回声长度相同时，按回声强度降序
        return b.intensity_norm - a.intensity_norm;
      });
      
      setHotspots(sortedItems);
      setUsingFallback(fallback);
    });
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    let cancel = false;
    getTodayTopics().then(({ items, fallback }) => {
      if (cancel) return;
      // 排序规则：与回声热榜一致
      const sortedItems = [...items].sort((a, b) => {
        const aHours = Math.floor(a.length_hours);
        const bHours = Math.floor(b.length_hours);
        
        if (aHours !== bHours) {
          return bHours - aHours;
        }
        
        return b.intensity_norm - a.intensity_norm;
      });
      
      setTodayTopics(sortedItems);
    });
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedTopicId) {
      setDetail(null);
      setTimeline([]);
      setTimelineFallback(false);
      setDetailFallback(false);
      setTimelineLoading(false);
      return;
    }
    let cancel = false;
    setTimelineLoading(true);
    setDetail(null);
    setTimeline([]);
    setTimelineFallback(false);
    setDetailFallback(false);
    (async () => {
      try {
        const [{ detail, fallback }, { nodes, topic_summary, fallback: fallbackTimeline }] = await Promise.all([
          getTopicDetail(selectedTopicId),
          getTimeline(selectedTopicId),
        ]);
        if (cancel) return;
        // 如果 API 返回了 topic_summary，优先使用它
        if (detail && topic_summary) {
          detail.topic.summary = topic_summary;
        }
        setDetail(detail);
        setTimeline(nodes);
        setTimelineFallback(fallbackTimeline);
        setDetailFallback(fallback);
      } catch (error) {
        if (!cancel) {
          setDetail(null);
          setTimeline([]);
          setTimelineFallback(false);
          setDetailFallback(false);
        }
      } finally {
        if (!cancel) {
          setTimelineLoading(false);
        }
      }
    })();
    return () => {
      cancel = true;
    };
  }, [selectedTopicId]);

  const selectedHotspot = useMemo(
    () => {
      const allItems = activeTab === "echo" ? hotspots : todayTopics;
      return allItems.find((item) => item.topic_id === selectedTopicId) ?? null;
    },
    [hotspots, todayTopics, selectedTopicId, activeTab],
  );

  const handleHotspotClick = (topicId: string) => {
    setSelectedTopicId(topicId);
    setMode("event");
  };

  const currentItems = activeTab === "echo" ? hotspots : todayTopics;

  return (
    <div className="page explorer">
      <div className="theme-toggle-floating">
        <ThemeToggle />
      </div>
      <header className="explorer-header">
        <div className="brand">
          <span className="brand-mark">E</span>
          <div>
            <h1>Echoman</h1>
            <p className="tagline">每个回声会持续多久</p>
          </div>
        </div>
        <div className="header-actions">
          <span className="data-sources">
            数据源：
            <span>{dataSources.join(" / ")}</span>
          </span>
          <Link to="/" className="ghost-button">
            返回首页
          </Link>
        </div>
      </header>

      <main className="explorer-layout">
        <aside className="hotspot-sidebar">
          <div className="sidebar-header">
            <div className="tab-header">
              <button
                type="button"
                className={activeTab === "echo" ? "tab-button active" : "tab-button"}
                onClick={() => setActiveTab("echo")}
              >
                回声热榜
              </button>
              <button
                type="button"
                className={activeTab === "today" ? "tab-button active" : "tab-button"}
                onClick={() => setActiveTab("today")}
              >
                当日热点
              </button>
            </div>
            <span>
              {activeTab === "echo"
                ? "取全部事件中回声长度前50展示，每天凌晨更新"
                : "展示当日新增话题，按回声长度排序"}
            </span>
          </div>
          <div className="hotspot-list-container">
            <ol className="hotspot-list">
              {currentItems.map((item, index) => {
                const active = mode === "event" && item.topic_id === selectedTopicId;
                return (
                  <li key={item.topic_id} className={active ? "hotspot-item active" : "hotspot-item"}>
                    <button type="button" onClick={() => handleHotspotClick(item.topic_id)}>
                      <div className="hotspot-rank-col">
                        <span className="rank-number">{index + 1}</span>
                      </div>
                      <div className="hotspot-content">
                        <h3>{item.title}</h3>
                        <div className="item-meta">
                          <span className="meta-chip">长度 {formatEchoLength(item.length_hours)}</span>
                          <span className="meta-chip">强度 {(item.intensity_norm * 10000).toFixed(1)}bp</span>
                          {item.last_active && (
                            <span className="meta-chip meta-chip-date">
                              最近活跃 {formatDateOnly(item.last_active)}
                            </span>
                          )}
                        </div>
                        {item.platforms.length > 0 && (
                          <div className="hotspot-platforms">
                            {item.platforms.map((platform) => (
                              <span className="platform-chip" key={`${item.topic_id}-${platform}`}>
                                {getPlatformLabel(platform)}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        </aside>

        <section className="explorer-chat-panel">
          <ConversationConsole
            mode={mode}
            onModeChange={setMode}
            selectedTopicId={selectedTopicId}
            selectedTopicTitle={detail?.topic.title ?? selectedHotspot?.title}
            detailSummary={detail?.topic.summary ?? selectedHotspot?.summary}
            keyPoints={detail?.key_points ?? []}
            timelineNodes={timeline}
            timelineFallback={timelineFallback}
            detailFallback={detailFallback}
            isTimelineLoading={timelineLoading}
          />
        </section>
      </main>
    </div>
  );
}
