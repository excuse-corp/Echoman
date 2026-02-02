import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import type { TimelineNode } from "../types";
import { askQuestion, verifyInviteCode } from "../services/api";

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
const TOOL_USAGE_PREFIX = "（本次使用工具：";
const TOOL_USAGE_SUFFIX = "）";
const URL_REGEX = /(https?:\/\/[^\s)）<>]+|www\.[^\s)）<>]+)/g;
const MARKDOWN_LINK_REGEX = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

function splitToolUsage(text: string) {
  const trimmed = text.trim();
  if (!trimmed.includes(TOOL_USAGE_PREFIX)) {
    return { body: text, toolUsage: "" };
  }
  const parts = trimmed.split("\n");
  const lastLine = parts[parts.length - 1];
  if (lastLine.startsWith(TOOL_USAGE_PREFIX) && lastLine.endsWith(TOOL_USAGE_SUFFIX)) {
    return { body: parts.slice(0, -1).join("\n"), toolUsage: lastLine };
  }
  return { body: text, toolUsage: "" };
}

function splitTrailingPunctuation(value: string) {
  const match = value.match(/^(.*?)([\]\)\}，。；、,.!?]+)$/);
  if (match) {
    return { core: match[1], trailing: match[2] };
  }
  return { core: value, trailing: "" };
}

function formatLinkLabel(href: string, index: number) {
  const platform = getPlatformLabelFromUrl(href);
  if (platform) {
    return `${platform}链接${index}`;
  }
  try {
    const url = new URL(href);
    const host = url.hostname.replace(/^www\./, "");
    return host ? `${host}链接${index}` : `原文链接${index}`;
  } catch {
    return `原文链接${index}`;
  }
}

function getPlatformLabelFromUrl(href: string) {
  try {
    const url = new URL(href.startsWith("http") ? href : `https://${href}`);
    const host = url.hostname.replace(/^www\./, "");
    const rules: Array<[string, string]> = [
      ["weibo.com", "微博"],
      ["zhihu.com", "知乎"],
      ["toutiao.com", "今日头条"],
      ["sina.com.cn", "新浪新闻"],
      ["news.sina.com.cn", "新浪新闻"],
      ["qq.com", "腾讯新闻"],
      ["news.qq.com", "腾讯新闻"],
      ["163.com", "网易新闻"],
      ["baidu.com", "百度"],
      ["hupu.com", "虎扑"],
      ["xiaohongshu.com", "小红书"],
      ["douyin.com", "抖音"],
    ];
    for (const [suffix, label] of rules) {
      if (host === suffix || host.endsWith(`.${suffix}`)) {
        return label;
      }
    }
    return "";
  } catch {
    return "";
  }
}

function renderPlainTextWithLinks(text: string, keyPrefix: string, linkState: { index: number }) {
  const elements: ReactNode[] = [];
  const parts = text.split(URL_REGEX);
  parts.forEach((part, index) => {
    if (!part) return;
    if (part.match(URL_REGEX)) {
      const { core, trailing } = splitTrailingPunctuation(part);
      const href = core.startsWith("http") ? core : `https://${core}`;
      const label = formatLinkLabel(href, linkState.index);
      linkState.index += 1;
      elements.push(
        <a key={`${keyPrefix}-link-${index}`} href={href} target="_blank" rel="noopener noreferrer">
          {label}
        </a>,
      );
      if (trailing) {
        elements.push(<span key={`${keyPrefix}-trail-${index}`}>{trailing}</span>);
      }
    } else {
      const lines = part.split("\n");
      lines.forEach((line, lineIndex) => {
        elements.push(<span key={`${keyPrefix}-text-${index}-${lineIndex}`}>{line}</span>);
        if (lineIndex < lines.length - 1) {
          elements.push(<br key={`${keyPrefix}-br-${index}-${lineIndex}`} />);
        }
      });
    }
  });
  return elements;
}

function renderTextWithLinks(text: string) {
  const elements: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let counter = 0;
  const linkState = { index: 1 };

  while ((match = MARKDOWN_LINK_REGEX.exec(text)) !== null) {
    const [full, label, url] = match;
    const start = match.index;
    const end = start + full.length;
    if (start > lastIndex) {
      elements.push(...renderPlainTextWithLinks(text.slice(lastIndex, start), `seg-${counter}`, linkState));
      counter += 1;
    }
    elements.push(
      <a key={`mdlink-${counter}`} href={url} target="_blank" rel="noopener noreferrer">
        {label}
      </a>,
    );
    counter += 1;
    lastIndex = end;
  }

  if (lastIndex < text.length) {
    elements.push(...renderPlainTextWithLinks(text.slice(lastIndex), `seg-${counter}`, linkState));
  }

  return elements;
}

function splitPendingUrl(text: string) {
  const match = text.match(/(https?:\/\/|www\.)\S*$/);
  if (match && typeof match.index === "number") {
    return { safeText: text.slice(0, match.index), tail: text.slice(match.index) };
  }
  return { safeText: text, tail: "" };
}

function replaceUrlsWithMarkdown(text: string) {
  const placeholders: string[] = [];
  let placeholderIndex = 0;
  const preserved = text.replace(MARKDOWN_LINK_REGEX, (match) => {
    const token = `__MDLINK_${placeholderIndex}__`;
    placeholders.push(match);
    placeholderIndex += 1;
    return token;
  });

  let urlIndex = 1;
  const replaced = preserved.replace(URL_REGEX, (match) => {
    const { core, trailing } = splitTrailingPunctuation(match);
    const href = core.startsWith("http") ? core : `https://${core}`;
    const label = formatLinkLabel(href, urlIndex);
    urlIndex += 1;
    return `[${label}](${href})${trailing ?? ""}`;
  });

  return replaced.replace(/__MDLINK_(\d+)__/g, (_full, idx) => placeholders[Number(idx)] ?? "");
}

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
  const abortRef = useRef<AbortController | null>(null);
  const stopRequestedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [inviteCode, setInviteCode] = useState("");
  const [isFreeModeUnlocked, setFreeModeUnlocked] = useState(false);
  const [freeModeToken, setFreeModeToken] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [streamUrlTail, setStreamUrlTail] = useState<Record<string, string>>({});

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
    stopRequestedRef.current = true;
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setStreaming(false);
  }, []);

  const appendAssistantChunk = (messageId: string, chunk: string) => {
    if (!chunk) return;
    const sanitizedChunk = chunk.replace(/<\/?think>/g, "");
    const pendingTail = streamUrlTail[messageId] ?? "";
    const combined = pendingTail + sanitizedChunk;
    const { safeText, tail } = splitPendingUrl(combined);
    if (tail !== pendingTail) {
      setStreamUrlTail((prev) => ({ ...prev, [messageId]: tail }));
    }
    setMessages((prev) =>
      prev.map((message) =>
        message.id === messageId && message.kind === "text"
          ? { ...message, text: message.text + (message.text ? safeText : safeText.trimStart()) }
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
    setStreamUrlTail({});
  }, [buildInitialMessages, stopStreaming]);

  useEffect(() => {
    setInput("");
  }, [mode, selectedTopicId]);

  useEffect(() => {
    const cachedToken = localStorage.getItem("free_mode_token");
    if (cachedToken) {
      setFreeModeToken(cachedToken);
      setFreeModeUnlocked(true);
    }
  }, []);

  const handleRefresh = useCallback(() => {
    stopStreaming();
    setMessages(buildInitialMessages());
    setInput("");
  }, [buildInitialMessages, stopStreaming]);

  const flushPendingUrlTail = (assistantId: string) => {
    const tail = streamUrlTail[assistantId];
    if (!tail) return;
    setMessages((prev) =>
      prev.map((message) =>
        message.id === assistantId && message.kind === "text"
          ? { ...message, text: message.text + tail }
          : message,
      ),
    );
    setStreamUrlTail((prev) => {
      const next = { ...prev };
      delete next[assistantId];
      return next;
    });
  };

  const sanitizeAssistantMessage = (assistantId: string) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === assistantId && message.kind === "text"
          ? {
              ...message,
              text: replaceUrlsWithMarkdown(
                message.text
                  .replace(/<think>[\s\S]*?<\/think>/g, "")
                  .replace(/<\/?think>/g, "")
                  .trim(),
              ),
            }
          : message,
      ),
    );
  };

  const callRealAiStream = async (
    assistantId: string,
    question: string,
    history: Array<{ role: "user" | "assistant"; content: string }>
  ) => {
    setStreaming(true);
    stopRequestedRef.current = false;
    const controller = new AbortController();
    abortRef.current = controller;
    
    try {
      await askQuestion({
        query: question,
        mode: mode === "event" ? "topic" : "global",
        topicId: mode === "event" ? selectedTopicId ?? undefined : undefined,
        freeToken: mode === "free" ? freeModeToken ?? undefined : undefined,
        history,
        signal: controller.signal,
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
          flushPendingUrlTail(assistantId);
          sanitizeAssistantMessage(assistantId);
          abortRef.current = null;
          stopStreaming();
        },
        onError: (error) => {
          if (!stopRequestedRef.current) {
            appendAssistantChunk(assistantId, `\n\n❌ 错误: ${error}`);
          }
          if (mode === "free" && error.includes("403")) {
            localStorage.removeItem("free_mode_token");
            setFreeModeToken(null);
            setFreeModeUnlocked(false);
            setInviteError("访问令牌已失效，请重新输入邀请码");
          }
          abortRef.current = null;
          stopStreaming();
        },
      });
    } catch (error) {
      if (!stopRequestedRef.current) {
        appendAssistantChunk(assistantId, `\n\n❌ 请求失败: ${error instanceof Error ? error.message : "未知错误"}`);
      }
      abortRef.current = null;
      stopStreaming();
    }
  };

  const handleSubmit = () => {
    if (!input.trim() || isStreaming) {
      return;
    }

    const question = input.trim();
    stopStreaming();

    const history = messages
      .filter((message) => message.kind === "text")
      .slice(-8)
      .map((message) => ({
        role: message.role === "assistant" ? "assistant" : "user",
        content: message.text,
      }));

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
    callRealAiStream(assistantMessageId, question, history);
  };

  const handleSendOrStop = () => {
    if (isStreaming) {
      stopStreaming();
      return;
    }
    handleSubmit();
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
    if (!inviteCode.trim()) {
      setInviteError("请输入邀请码");
      return;
    }
    setInviteError(null);
    verifyInviteCode(inviteCode.trim())
      .then((result) => {
        if (result.valid && result.token) {
          localStorage.setItem("free_mode_token", result.token);
          setFreeModeToken(result.token);
          setFreeModeUnlocked(true);
          setInviteCode("");
        } else {
          setInviteError("邀请码无效或已过期");
        }
      })
      .catch((error) => {
        setInviteError(error instanceof Error ? error.message : "邀请码校验失败");
      });
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
                {(() => {
                  const { body, toolUsage } = splitToolUsage(message.text);
                  if (message.role === "assistant" && !body.trim() && isStreaming) {
                    return (
                      <div className="thinking-dots" aria-label="正在生成">
                        <span />
                        <span />
                        <span />
                      </div>
                    );
                  }
                  return (
                    <>
                      {renderTextWithLinks(body)}
                      {toolUsage && <div className="tool-usage">{toolUsage}</div>}
                    </>
                  );
                })()}
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
            <button
              type="button"
              onClick={handleSendOrStop}
              disabled={!isStreaming && !input.trim()}
              className={isStreaming ? "stop-button" : undefined}
            >
              {isStreaming ? "停止" : "发送"}
            </button>
            {isStreaming && (
              <div className="send-streaming-indicator" aria-label="正在生成">
                <span />
                <span />
                <span />
              </div>
            )}
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
                  onChange={(e) => {
                    setInviteCode(e.target.value);
                    if (inviteError) {
                      setInviteError(null);
                    }
                  }}
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
              {inviteError && <p className="invite-code-error">{inviteError}</p>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
