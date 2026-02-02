import type { CategoryEchoStat, HotspotSummary, TimelineNode, TopicDetail, ChatResponse, ChatStreamEvent } from "../types";
import { ENABLED_PLATFORMS } from "../constants/platforms";
import { API_BASE_URL } from "./config";

const now = new Date();
const hours = (n: number) => 1000 * 60 * 60 * n;

const fallbackHotspots: HotspotSummary[] = [
  {
    topic_id: "topic-001",
    title: "明星公益直播引发关注",
    summary: "多位艺人联合抖音公益直播，筹款帮助受灾地区，引发跨平台讨论。",
    intensity_raw: 138,
    intensity_norm: 0.825,
    length_hours: 84,
    length_days: 3.5,
    first_seen: new Date(now.getTime() - hours(84)).toISOString(),
    last_active: new Date(now.getTime() - hours(6)).toISOString(),
    platforms: ["douyin", "weibo", "xiaohongshu", "tencent"],
    platform_mentions: {
      douyin: 40,
      weibo: 52,
      xiaohongshu: 18,
      tencent: 28,
      zhihu: 0,
      toutiao: 0,
      sina: 0,
      netease: 0,
    },
    status: "active",
  },
  {
    topic_id: "topic-002",
    title: "华南强降雨造成交通中断",
    summary: "华南多地遭遇持续强降雨，官方多轮应急响应帮助恢复交通与民生。",
    intensity_raw: 214,
    intensity_norm: 0.91,
    length_hours: 120,
    length_days: 5.0,
    first_seen: new Date(now.getTime() - hours(120)).toISOString(),
    last_active: new Date(now.getTime() - hours(2)).toISOString(),
    platforms: ["sina", "tencent", "netease", "toutiao", "weibo", "zhihu"],
    platform_mentions: {
      douyin: 12,
      weibo: 60,
      xiaohongshu: 14,
      tencent: 34,
      zhihu: 28,
      toutiao: 38,
      sina: 20,
      netease: 18,
    },
    status: "active",
  },
  {
    topic_id: "topic-003",
    title: "电竞冠军公益行走进校园",
    summary: "知名电竞战队走进校园分享职业经验，并发起反沉迷宣讲，引发年轻群体关注。",
    intensity_raw: 96,
    intensity_norm: 0.68,
    length_hours: 54,
    length_days: 2.5,
    first_seen: new Date(now.getTime() - hours(54)).toISOString(),
    last_active: new Date(now.getTime() - hours(10)).toISOString(),
    platforms: ["douyin", "weibo", "toutiao"],
    platform_mentions: {
      douyin: 22,
      weibo: 44,
      xiaohongshu: 0,
      tencent: 0,
      zhihu: 0,
      toutiao: 30,
      sina: 0,
      netease: 0,
    },
    status: "active",
  },
];

const fallbackCategoryStats: CategoryEchoStat[] = [
  {
    category: "entertainment",
    avg_length_hours: 76,
    max_length_hours: 152,
    min_length_hours: 36,
    topics_count: 0,
  },
  {
    category: "current_affairs",
    avg_length_hours: 102,
    max_length_hours: 176,
    min_length_hours: 52,
    topics_count: 0,
  },
  {
    category: "sports_esports",
    avg_length_hours: 66,
    max_length_hours: 120,
    min_length_hours: 24,
    topics_count: 0,
  },
];

const fallbackDetails: Record<string, TopicDetail> = {
  "topic-001": {
    topic: fallbackHotspots[0],
    key_points: [
      "公益直播在 4 小时内突破 2000 万观看量，延续跨平台讨论热度。",
      "多家媒体报道直播善款流向，公益组织邀请第三方审计监督。",
      "志愿者团队通过小程序实时同步抢险物资需求与发放进展。",
    ],
    entities: {
      persons: ["李晨", "赵露思"],
      organizations: ["抖音公益", "蓝天救援队"],
      locations: ["四川省绵阳市"],
    },
  },
  "topic-002": {
    topic: fallbackHotspots[1],
    key_points: [
      "气象部门连续发布暴雨黄色预警，多地道路临时封闭。",
      "应急管理部门提升响应等级，投入排涝设备并安排复工复产。",
      "专家提醒警惕次生灾害风险，关注电力和通信保障。",
    ],
    entities: {
      organizations: ["应急管理部", "中国气象局"],
      locations: ["广东省韶关市", "广西南宁市"],
    },
  },
  "topic-003": {
    topic: fallbackHotspots[2],
    key_points: [
      "冠军战队携手教育机构，分享电竞行业发展与自律经验。",
      "活动同步上线公益直播，筹集青少年心理辅导基金。",
      "官方提醒理性看待电竞职业，强调健康生活与学习平衡。",
    ],
    entities: {
      organizations: ["AG 战队", "青少年成长基金会"],
      locations: ["杭州市滨江区"],
    },
  },
};

const fallbackTimelines: Record<string, TimelineNode[]> = {
  "topic-001": [
    {
      node_id: "node-001",
      topic_id: "topic-001",
      timestamp: new Date(now.getTime() - hours(72)).toISOString(),
      title: "明星宣布公益直播计划",
      content: "多位艺人在微博宣布将开启公益直播，目标筹集善款支援灾区。",
      source_platform: "weibo",
      source_url: "https://weibo.com/example/announce",
      captured_at: new Date(now.getTime() - hours(71)).toISOString(),
      engagement: 68000,
    },
    {
      node_id: "node-002",
      topic_id: "topic-001",
      timestamp: new Date(now.getTime() - hours(56)).toISOString(),
      title: "抖音直播开播吸引百万网友",
      content: "直播首小时突破百万观看，粉丝在评论区接力捐款。",
      source_platform: "douyin",
      source_url: "https://www.douyin.com/example/live",
      captured_at: new Date(now.getTime() - hours(55)).toISOString(),
      engagement: 128000,
    },
    {
      node_id: "node-003",
      topic_id: "topic-001",
      timestamp: new Date(now.getTime() - hours(30)).toISOString(),
      title: "善款流向公布并接受第三方审计",
      content: "公益组织发布捐款明细，并宣布邀请第三方审计机构参与监督。",
      source_platform: "xiaohongshu",
      source_url: "https://www.xiaohongshu.com/example/report",
      captured_at: new Date(now.getTime() - hours(29)).toISOString(),
      engagement: 54000,
    },
  ],
  "topic-002": [
    {
      node_id: "node-101",
      topic_id: "topic-002",
      timestamp: new Date(now.getTime() - hours(120)).toISOString(),
      title: "暴雨黄色预警发布",
      content: "气象部门对华南多地发布暴雨黄色预警，提醒市民减少出行。",
      source_platform: "sina",
      source_url: "https://news.sina.com.cn/example/weather",
      captured_at: new Date(now.getTime() - hours(119)).toISOString(),
      engagement: 22000,
    },
    {
      node_id: "node-102",
      topic_id: "topic-002",
      timestamp: new Date(now.getTime() - hours(80)).toISOString(),
      title: "部分高铁停运与航班延误",
      content: "交通运输部门宣布对多趟列车和航班采取临时调整措施。",
      source_platform: "tencent",
      source_url: "https://news.qq.com/example/transport",
      captured_at: new Date(now.getTime() - hours(79)).toISOString(),
      engagement: 47000,
    },
    {
      node_id: "node-103",
      topic_id: "topic-002",
      timestamp: new Date(now.getTime() - hours(30)).toISOString(),
      title: "雨势趋缓官方安排复工复产",
      content: "地方政府发布通告，称主要道路完成排水，逐步恢复交通和生产。",
      source_platform: "netease",
      source_url: "https://news.163.com/example/recover",
      captured_at: new Date(now.getTime() - hours(29)).toISOString(),
      engagement: 33000,
    },
  ],
  "topic-003": [
    {
      node_id: "node-201",
      topic_id: "topic-003",
      timestamp: new Date(now.getTime() - hours(48)).toISOString(),
      title: "冠军战队公布校园公益行计划",
      content: "AG 战队宣布将展开系列校园宣讲，并同步上线公益直播。",
      source_platform: "weibo",
      source_url: "https://weibo.com/example/esports",
      captured_at: new Date(now.getTime() - hours(47)).toISOString(),
      engagement: 22000,
    },
    {
      node_id: "node-202",
      topic_id: "topic-003",
      timestamp: new Date(now.getTime() - hours(32)).toISOString(),
      title: "反沉迷宣讲直播登上热搜",
      content: "活动邀请心理专家分享案例，呼吁家长与学校共同关注青少年身心健康。",
      source_platform: "douyin",
      source_url: "https://www.douyin.com/example/esports",
      captured_at: new Date(now.getTime() - hours(31)).toISOString(),
      engagement: 54000,
    },
    {
      node_id: "node-203",
      topic_id: "topic-003",
      timestamp: new Date(now.getTime() - hours(12)).toISOString(),
      title: "公益基金公布首批资助名单",
      content: "青少年成长基金会公布心理辅导项目首批资助名单，并开放后续申请。",
      source_platform: "toutiao",
      source_url: "https://www.toutiao.com/example/esports",
      captured_at: new Date(now.getTime() - hours(11)).toISOString(),
      engagement: 18000,
    },
  ],
};

export async function getHotspots(): Promise<{ items: HotspotSummary[]; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics
    console.log('[api] Fetching hotspots from:', `${API_BASE_URL}/topics`);
    const response = await fetch(`${API_BASE_URL}/topics`);
    console.log('[api] Response status:', response.status);
    if (!response.ok) {
      throw new Error(`Bad status: ${response.status}`);
    }
    const payload = await response.json();
    console.log('[api] Received payload:', payload);
    console.log('[api] Items count:', payload.items?.length);
    return { items: payload.items as HotspotSummary[], fallback: false };
  } catch (error) {
    console.error("[api] getHotspots fallback, reason:", error);
    return { items: fallbackHotspots, fallback: true };
  }
}

export async function getTodayTopics(): Promise<{ items: HotspotSummary[]; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics/today
    console.log('[api] Fetching today topics from:', `${API_BASE_URL}/topics/today`);
    const response = await fetch(`${API_BASE_URL}/topics/today`);
    console.log('[api] Response status:', response.status);
    if (!response.ok) {
      throw new Error(`Bad status: ${response.status}`);
    }
    const payload = await response.json();
    console.log('[api] Received today topics payload:', payload);
    console.log('[api] Today topics count:', payload.items?.length);
    return { items: payload.items as HotspotSummary[], fallback: false };
  } catch (error) {
    console.error("[api] getTodayTopics fallback, reason:", error);
    return { items: [], fallback: true };
  }
}

export async function getCategoryEchoStats(): Promise<{ items: CategoryEchoStat[]; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/categories/metrics/summary
    const response = await fetch(`${API_BASE_URL}/categories/metrics/summary`);
    if (!response.ok) {
      throw new Error(`Bad status: ${response.status}`);
    }
    const payload = await response.json();
    return { items: payload.items as CategoryEchoStat[], fallback: false };
  } catch (error) {
    console.warn("[api] getCategoryEchoStats fallback, reason:", error);
    return { items: fallbackCategoryStats, fallback: true };
  }
}

export async function getTopicDetail(
  topicId: string,
): Promise<{ detail: TopicDetail | null; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics/{topic_id}
    const response = await fetch(`${API_BASE_URL}/topics/${topicId}`);
    if (!response.ok) {
      throw new Error(`Bad status: ${response.status}`);
    }
    const raw = await response.json();

    const firstSeen = raw.first_seen ?? raw.firstSeen ?? null;
    const lastActive = raw.last_active ?? raw.lastActive ?? null;

    let lengthHours = 0;
    let lengthDays = 0;
    
    if (typeof raw.length_hours === "number") {
      lengthHours = raw.length_hours;
      lengthDays = raw.length_days ?? lengthHours / 24;
    } else if (typeof raw.length_days === "number") {
      lengthDays = raw.length_days;
      lengthHours = lengthDays * 24;
    } else if (firstSeen && lastActive) {
      const start = new Date(firstSeen).getTime();
      const end = new Date(lastActive).getTime();
      if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
        lengthHours = (end - start) / (1000 * 60 * 60);
        lengthDays = lengthHours / 24;
      }
    }

    const platforms = Array.isArray(raw.platforms)
      ? raw.platforms
      : raw.platform_mentions
        ? Object.keys(raw.platform_mentions)
        : [];

    const topicSummary = {
      topic_id: String(raw.topic_id ?? raw.id ?? topicId),
      title: raw.title ?? raw.title_key ?? "未命名话题",
      summary: raw.summary || "",
      intensity_raw: raw.intensity_raw ?? raw.intensity_total ?? 0,
      intensity_norm: raw.intensity_norm ?? raw.intensity_total ?? 0,
      length_hours: lengthHours,
      length_days: lengthDays,
      first_seen: firstSeen ?? new Date().toISOString(),
      last_active: lastActive ?? new Date().toISOString(),
      platforms,
      platform_mentions: raw.platform_mentions ?? {},
      status: raw.status ?? "active",
    } as HotspotSummary;

    const detail: TopicDetail = {
      topic: topicSummary,
      key_points: Array.isArray(raw.key_points) ? raw.key_points : [],
      entities: typeof raw.entities === "object" && raw.entities !== null ? raw.entities : {},
    };

    return { detail, fallback: false };
  } catch (error) {
    console.warn("[api] getTopicDetail fallback, reason:", error);
    return { detail: fallbackDetails[topicId] ?? null, fallback: true };
  }
}

export async function getTimeline(
  topicId: string,
): Promise<{ nodes: TimelineNode[]; topic_summary?: string | null; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics/{topic_id}/timeline
    // 返回包含 topic_summary 和 items 的对象
    const response = await fetch(`${API_BASE_URL}/topics/${topicId}/timeline`);
    if (!response.ok) {
      throw new Error(`Bad status: ${response.status}`);
    }
    const payload = await response.json();
    const rawItems: unknown[] = payload.items || payload.nodes || [];
    const topicSummary = payload.topic_summary ?? null;

    const nodes: TimelineNode[] = rawItems.map((item: any) => {
      const published = item.published_at ?? item.timestamp ?? item.created_at ?? null;
      const captured = item.captured_at ?? published ?? new Date().toISOString();
      const engagement = (() => {
        if (typeof item.engagement === "number") return item.engagement;
        if (item.interactions) {
          const values = Object.values(item.interactions).map((v) => Number(v));
          return values.find((v) => Number.isFinite(v)) ?? undefined;
        }
        return undefined;
      })();

      const generatedId = (() => {
        if (typeof item.node_id !== "undefined") return String(item.node_id);
        if (typeof item.id !== "undefined") return String(item.id);
        if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
          return crypto.randomUUID();
        }
        return `${topicId}-${Math.random().toString(36).slice(2)}`;
      })();

      return {
        node_id: generatedId,
        topic_id: String(item.topic_id ?? topicId),
        timestamp: published ?? new Date().toISOString(),
        title: item.title ?? "",
        content: item.summary ?? item.content ?? "",
        source_platform: item.source_platform ?? item.platform ?? "",
        source_url: item.source_url ?? item.url ?? item.link ?? "",
        captured_at: captured,
        engagement,
        // 聚合字段
        duplicate_count: item.duplicate_count ?? undefined,
        time_range_start: item.time_range_start ?? undefined,
        time_range_end: item.time_range_end ?? undefined,
        all_platforms: item.all_platforms ?? undefined,
        all_source_urls: item.all_source_urls ?? undefined,
        all_timestamps: item.all_timestamps ?? undefined,
      } satisfies TimelineNode;
    });

    return { nodes, topic_summary: topicSummary, fallback: false };
  } catch (error) {
    console.warn("[api] getTimeline fallback, reason:", error);
    return { nodes: fallbackTimelines[topicId] ?? [], topic_summary: null, fallback: true };
  }
}

// 实际支持的数据源平台（从统一配置导出）
export const dataSources = ENABLED_PLATFORMS;

export const FALLBACK_DATASET_NOTE = "????????????????????????????????";

export const FALLBACK_HOTSPOTS = fallbackHotspots;
export const FALLBACK_CATEGORY_STATS = fallbackCategoryStats;

export async function verifyInviteCode(code: string): Promise<{ valid: boolean; token?: string; expires_at?: string }> {
  const response = await fetch(`${API_BASE_URL}/free/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });

  if (!response.ok) {
    let detail = "";
    try {
      const data = await response.json();
      detail = data?.detail || "";
    } catch {
      detail = "";
    }
    throw new Error(detail || `API错误: ${response.status}`);
  }

  return response.json();
}

/**
 * 问答API - 支持流式和非流式
 */
export async function askQuestion(params: {
  query: string;
  mode: "global" | "topic";
  topicId?: string;
  freeToken?: string;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
  signal?: AbortSignal;
  stream?: boolean;
  onToken?: (token: string) => void;
  onCitations?: (citations: ChatResponse["citations"]) => void;
  onDone?: (diagnostics: ChatResponse["diagnostics"]) => void;
  onError?: (error: string) => void;
}): Promise<ChatResponse | null> {
  const { query, mode, topicId, freeToken, history, signal, stream = false, onToken, onCitations, onDone, onError } = params;

  try {
    const requestBody = {
      query,
      mode,
      topic_id: topicId ? parseInt(topicId) : undefined,
      free_token: freeToken,
      history,
      stream,
    };

    if (!stream) {
      // 非流式请求
      const response = await fetch(`${API_BASE_URL}/chat/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
        signal,
      });

      if (!response.ok) {
        throw new Error(`API错误: ${response.status}`);
      }

      const data: ChatResponse = await response.json();
      return data;
    } else {
      // 流式请求 - SSE
      const response = await fetch(`${API_BASE_URL}/chat/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
        signal,
      });

      if (!response.ok) {
        throw new Error(`API错误: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("响应体为空");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) {
            // 空行表示事件结束
            currentEvent = "";
            continue;
          }
          
          if (line.startsWith("event:")) {
            currentEvent = line.substring(6).trim();
            continue;
          }

          if (line.startsWith("data:")) {
            try {
              const data = JSON.parse(line.substring(5).trim());
              
              // 根据事件类型处理数据
              if (currentEvent === "token" && data.content && onToken) {
                onToken(data.content);
              } else if (currentEvent === "citations" && data.citations && onCitations) {
                onCitations(data.citations);
              } else if (currentEvent === "done" && data.diagnostics && onDone) {
                onDone(data.diagnostics);
              } else if (currentEvent === "error" && data.message && onError) {
                onError(data.message);
              }
            } catch (e) {
              console.warn("解析SSE数据失败:", e, "原始数据:", line);
            }
          }
        }
      }

      return null; // 流式模式通过回调返回数据
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return null;
    }
    const errorMessage = error instanceof Error ? error.message : "未知错误";
    if (onError) {
      onError(errorMessage);
    }
    console.error("[api] askQuestion error:", error);
    return null;
  }
}
