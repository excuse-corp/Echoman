export type PlatformName =
  | "weibo"
  | "zhihu"
  | "toutiao"
  | "sina"
  | "tencent"
  | "netease"
  | "xiaohongshu"
  | "douyin";

export interface HotspotSummary {
  topic_id: string;
  title: string;
  summary: string;
  intensity_raw: number;
  intensity_norm: number;
  length_hours: number;
  length_days: number;
  first_seen: string;
  last_active: string;
  platforms: PlatformName[];
  platform_mentions: Record<PlatformName, number>;
  status: "active" | "ended";
}

export interface TopicDetail {
  topic: HotspotSummary;
  key_points: string[];
  entities: Record<string, string[]>;
}

export interface TimelineNode {
  node_id: string;
  topic_id: string;
  timestamp: string;
  title: string;
  content: string;
  source_platform: PlatformName;
  source_url: string;
  captured_at: string;
  engagement?: number;
  // 聚合字段（用于相同内容的多次报道）
  duplicate_count?: number;
  time_range_start?: string;
  time_range_end?: string;
  all_platforms?: PlatformName[];
  all_source_urls?: string[];
  all_timestamps?: string[];
}

export interface TimelineResponse {
  topic_summary?: string | null;
  items: TimelineNode[];
}

export interface CategoryEchoStat {
  category: string;
  avg_length_hours: number;
  max_length_hours: number;
  min_length_hours: number;
  topics_count: number;
}

export interface IngestSummary {
  platform: PlatformName;
  fetched: number;
  merged: number;
  new_topics: number;
  notes?: string;
}

export interface IngestRunResponse {
  started_at: string;
  finished_at: string;
  summaries: IngestSummary[];
}

export interface ChatCitation {
  topic_id?: number;
  node_id?: number;
  source_url: string;
  snippet: string;
  platform: string;
}

export interface ChatDiagnostics {
  latency_ms: number;
  tokens_prompt: number;
  tokens_completion: number;
  context_chunks: number;
  fallback?: boolean;
}

export interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  diagnostics: ChatDiagnostics;
}

export interface ChatStreamEvent {
  type: "token" | "citations" | "done" | "error";
  data: {
    content?: string;
    citations?: ChatCitation[];
    diagnostics?: ChatDiagnostics;
    message?: string;
  };
}
