import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { TimelineNode } from "../types";
import { askQuestion } from "../services/api";

type ExplorerMode = "free" | "event";
type MessageRole = "assistant" | "user";

type Message =
  | {
      id: string;
      role: MessageRole;
      kind: "text";
      text: string;
      isInstruction?: boolean;
    }
  | {
      id: string;
      role: "assistant";
      kind: "timeline";
      topicTitle: string;
      summary?: string;
      nodes: TimelineNode[];
      keyPoints: string[];
      includesFallback: boolean;
    };

interface ConversationConsoleProps {
  mode: ExplorerMode;
  onModeChange: (mode: ExplorerMode) => void;
  selectedTopicId?: string | null;
  selectedTopicTitle?: string | null;
  detailSummary?: string | null;
  keyPoints: string[];
  timelineNodes: TimelineNode[];
  timelineFallback: boolean;
  detailFallback: boolean;
  isTimelineLoading: boolean;
}

const PLATFORM_LABELS: Record<string, string> = {
  weibo: "微博",
  zhihu: "知乎",
  toutiao: "今日头条",
  sina: "新浪新闻",
  tencent: "腾讯新闻",
  netease: "网易新闻",
  baidu: "百度热搜",
  hupu: "虎扑",
  xiaohongshu: "小红书",
  douyin: "抖音",
};

const STREAM_INTERVAL_MS = 120;

function formatTimelineTimestamp(timestamp: string) {
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimelineRange(start: string, end: string) {
  const startDate = new Date(start);
  const endDate = new Date(end);

  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return formatTimelineTimestamp(end);
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

function splitIntoStreamChunks(text: string) {
  const segments = text
    .split(/(?<=[。！？?!\n])/)
    .map((segment) => segment.trim())
    .filter(Boolean);
  if (!segments.length) {
    return [text];
  }
  return segments;
}

export function ConversationConsole({
  mode,
  onModeChange,
  selectedTopicId,
  selectedTopicTitle,
  detailSummary,
  keyPoints,
  timelineNodes,
  timelineFallback,
  detailFallback,
  isTimelineLoading,
}: ConversationConsoleProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [inviteCode, setInviteCode] = useState("");
  const [isFreeModeUnlocked, setFreeModeUnlocked] = useState(false);

  const normalizedKeyPoints = useMemo(() => keyPoints.filter(Boolean), [keyPoints]);

  const buildInitialMessages = useCallback((): Message[] => {
    if (mode === "free") {
      return [
        {
          id: "intro",
          role: "assistant",
          kind: "text",
          text: "自由模式：问我任何你想了解的热点事件，我会基于全局数据为你解答。",
          isInstruction: true,
        },
      ];
    }

    if (!selectedTopicTitle) {
      return [
        {
          id: "event-empty",
          role: "assistant",
          kind: "text",
          text: "请选择左侧的事件，我会自动整理时间线。",
          isInstruction: true,
        },
      ];
    }

    if (!timelineNodes.length) {
      if (isTimelineLoading) {
        return [
          {
            id: "event-loading",
            role: "assistant",
            kind: "text",
            text: `正在整理「${selectedTopicTitle}」的时间线，请稍候…`,
            isInstruction: true,
          },
        ];
      }

      return [
        {
          id: "event-empty-data",
          role: "assistant",
          kind: "text",
          text: `暂时没有找到「${selectedTopicTitle}」的时间线数据，稍后再试试。`,
          isInstruction: true,
        },
      ];
    }

    const timelineMessage: Message = {
      id: `timeline-${selectedTopicId ?? selectedTopicTitle}`,
      role: "assistant",
      kind: "timeline",
      topicTitle: selectedTopicTitle,
      summary: detailSummary ?? undefined,
      nodes: timelineNodes,
      keyPoints: normalizedKeyPoints,
      includesFallback: timelineFallback || detailFallback,
    };

    return [timelineMessage];
  }, [
    mode,
    selectedTopicId,
    selectedTopicTitle,
    detailSummary,
    timelineNodes,
    normalizedKeyPoints,
    timelineFallback,
    detailFallback,
    isTimelineLoading,
  ]);

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // 当消息更新时，自动滚动到底部
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const stopStreaming = useCallback(() => {
    setStreaming(false);
  }, []);

  const appendAssistantChunk = (messageId: string, chunk: string) => {
    if (!chunk) return;
    setMessages((prev) =>
      prev.map((message) =>
        message.id === messageId && message.kind === "text"
          ? { ...message, text: message.text + (message.text ? chunk : chunk.trimStart()) }
          : message,
      ),
    );
    // 流式输出时也滚动到底部
    setTimeout(() => scrollToBottom(), 0);
  };


  useEffect(() => () => stopStreaming(), [stopStreaming]);

  useEffect(() => {
    stopStreaming();
    setMessages(buildInitialMessages());
  }, [buildInitialMessages, stopStreaming]);

  useEffect(() => {
    setInput("");
  }, [mode, selectedTopicId]);

  const handleRefresh = useCallback(() => {
    stopStreaming();
    setMessages(buildInitialMessages());
    setInput("");
  }, [buildInitialMessages, stopStreaming]);

  const callRealAiStream = async (assistantId: string, question: string) => {
    setStreaming(true);
    
    try {
      await askQuestion({
        query: question,
        mode: mode === "event" ? "topic" : "global",
        topicId: mode === "event" ? selectedTopicId ?? undefined : undefined,
        stream: true,
        onToken: (token) => {
          appendAssistantChunk(assistantId, token);
        },
        onCitations: (citations) => {
          // 可以选择在回答末尾添加引用信息
          console.log("Citations received:", citations);
        },
        onDone: (diagnostics) => {
          console.log("Answer completed:", diagnostics);
          stopStreaming();
        },
        onError: (error) => {
          appendAssistantChunk(assistantId, `\n\n❌ 错误: ${error}`);
          stopStreaming();
        },
      });
    } catch (error) {
      appendAssistantChunk(assistantId, `\n\n❌ 请求失败: ${error instanceof Error ? error.message : "未知错误"}`);
      stopStreaming();
    }
  };

  const handleSubmit = () => {
    if (!input.trim() || isStreaming) {
      return;
    }

    const question = input.trim();
    stopStreaming();

    const userMessageId = `user-${Date.now()}`;
    const assistantMessageId = `assistant-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      {
        id: userMessageId,
        role: "user",
        kind: "text",
        text: question,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        kind: "text",
        text: "",
      },
    ]);

    setInput("");

    // 调用真实的AI问答API
    callRealAiStream(assistantMessageId, question);
  };

  const handleTextareaKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const textareaPlaceholder =
    mode === "event"
      ? "针对当前事件继续追问，或输入其它疑问。"
      : "想了解哪件热点事件？告诉我，我们一起听回声。";

  const handleInviteCodeSubmit = () => {
    // TODO: 在后端实现邀请码验证逻辑
    if (inviteCode.trim()) {
      // 这里可以添加实际的验证逻辑
      // 暂时用简单的判断模拟
      console.log("提交邀请码:", inviteCode);
      alert("邀请码功能正在开发中，敬请期待！");
      // setFreeModeUnlocked(true); // 验证成功后解锁
    }
  };

  return (
    <section className="conversation-card">
      <header className="conversation-header">
        <div>
          <h3>Echoman</h3>
          <p>探索模式分为自由模式和事件模式</p>
        </div>
        <div className="conversation-header-actions">
          <button
            type="button"
            className="conversation-refresh"
            onClick={handleRefresh}
            aria-label="刷新对话"
          >
            ↻
          </button>
          <div className="conversation-mode-switch">
            <button
              type="button"
              className={mode === "event" ? "mode-pill active" : "mode-pill"}
              onClick={() => onModeChange("event")}
            >
              事件模式
            </button>
            <button
              type="button"
              className={mode === "free" ? "mode-pill active" : "mode-pill"}
              onClick={() => onModeChange("free")}
            >
              自由模式
            </button>
          </div>
        </div>
      </header>

      <div className="conversation-content-wrapper">
        <div className="conversation-messages">
        {messages.map((message) => {
          if (message.kind === "timeline") {
            return (
              <div className="chat-line assistant" key={message.id}>
                <span className="avatar">E</span>
                <div className="bubble timeline-bubble">
                  <p className="timeline-intro">
                    你好，我是 Echoman，这是我整理的「{message.topicTitle}」事件时间线
                    {message.includesFallback ? "（演示数据）" : ""}。
                  </p>
                  {message.summary && message.summary.trim() && <p className="timeline-summary">摘要：{message.summary}</p>}
                  {message.keyPoints.length > 0 && (
                    <div className="timeline-keypoints">
                      <h4>关键要点</h4>
                      <ul>
                        {message.keyPoints.map((point, index) => (
                          <li key={`${message.id}-point-${index}`}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <ul className="timeline-preview">
                    {message.nodes.map((node) => {
                      const duplicateCount = Number(node.duplicate_count ?? 0);
                      const hasDuplicates = duplicateCount > 1;
                      const timeRangeText = hasDuplicates && node.time_range_start && node.time_range_end
                        ? formatTimelineRange(node.time_range_start, node.time_range_end)
                        : formatTimelineTimestamp(node.timestamp);

                      const platformLabels = hasDuplicates && node.all_platforms && node.all_platforms.length
                        ? Array.from(new Set(node.all_platforms.map((p) => PLATFORM_LABELS[p] ?? p))).join(" / ")
                        : PLATFORM_LABELS[node.source_platform] ?? node.source_platform;

                      const sourceLinks = hasDuplicates && node.all_source_urls && node.all_source_urls.length
                        ? node.all_source_urls.map((url, idx) => {
                            const platform = node.all_platforms?.[idx] || node.source_platform;
                            const label = PLATFORM_LABELS[platform] ?? platform;
                            const timestamp = node.all_timestamps?.[idx] ?? node.timestamp;
                            return { url, label, key: `${node.node_id}-${idx}`, timestamp };
                          })
                        : [{ url: node.source_url, label: PLATFORM_LABELS[node.source_platform] ?? node.source_platform, key: node.node_id, timestamp: node.timestamp }];

                      return (
                        <li className="timeline-preview-item" key={node.node_id}>
                          <div className="timeline-preview-meta">
                            {timeRangeText} · {platformLabels}
                          </div>
                          <div className="timeline-preview-title">{node.title}</div>
                          <div className="timeline-preview-body">{node.content}</div>
                          {hasDuplicates && (
                            <div className="timeline-preview-count">共 {duplicateCount} 次报道</div>
                          )}
                          <div className="timeline-source-list">
                            {sourceLinks.map(({ url, label, key, timestamp }) => (
                              <div className="timeline-source-item" key={key}>
                                <span className="timeline-source-time">{formatTimelineTimestamp(timestamp ?? node.timestamp)}</span>
                                <a
                                  href={url ?? "#"}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="timeline-source-link"
                                >
                                  {label} 原文 →
                                </a>
                              </div>
                            ))}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </div>
            );
          }

          return (
            <div className={`chat-line ${message.role}`} key={message.id}>
              <span className="avatar">{message.role === "assistant" ? "E" : "我"}</span>
              <div className="bubble" style={message.isInstruction ? { opacity: 0.92 } : undefined}>
                {message.text}
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
        </div>

        {mode === "free" && (
          <div className="conversation-input">
            <textarea
              rows={2}
              placeholder={textareaPlaceholder}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleTextareaKeyDown}
            />
            <button type="button" onClick={handleSubmit} disabled={isStreaming}>
              {isStreaming ? "生成中…" : "发送"}
            </button>
          </div>
        )}

        {/* 自由模式遮罩层 */}
        {mode === "free" && !isFreeModeUnlocked && (
          <div className="free-mode-overlay">
            <div className="free-mode-lock-card">
              <div className="lock-icon">🔒</div>
              <h3>自由模式</h3>
              <p className="lock-description">
                问我任何你想了解的热点事件，我会基于全局数据为你解答。
              </p>
              <div className="invite-code-form">
                <input
                  type="text"
                  placeholder="请输入邀请码"
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleInviteCodeSubmit();
                    }
                  }}
                />
                <button type="button" onClick={handleInviteCodeSubmit}>
                  提交
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
