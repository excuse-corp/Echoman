/**
 * SSE (Server-Sent Events) 流式对话服务
 * 
 * 用于与后端API进行实时流式对话
 */

import { API_BASE_URL } from "./config";

export interface SSETokenEvent {
  type: "token";
  data: {
    content: string;
  };
}

export interface SSECitationsEvent {
  type: "citations";
  data: {
    citations: Array<{
      topic_id?: number;
      node_id?: number;
      source_url: string;
      snippet: string;
      platform: string;
    }>;
  };
}

export interface SSEDoneEvent {
  type: "done";
  data: {
    diagnostics: {
      latency_ms: number;
      tokens_prompt: number;
      tokens_completion: number;
      context_chunks: number;
      original_chunks?: number;
    };
  };
}

export interface SSEErrorEvent {
  type: "error";
  data: {
    message: string;
  };
}

export type SSEEvent = SSETokenEvent | SSECitationsEvent | SSEDoneEvent | SSEErrorEvent;

export interface SSEStreamOptions {
  query: string;
  mode: "topic" | "global";
  topic_id?: number;
  chat_id?: number;
  onToken?: (content: string) => void;
  onCitations?: (citations: SSECitationsEvent["data"]["citations"]) => void;
  onDone?: (diagnostics: SSEDoneEvent["data"]["diagnostics"]) => void;
  onError?: (message: string) => void;
}

/**
 * 发起SSE流式对话
 * 
 * @param options 对话选项
 * @returns 清理函数，用于取消连接
 */
export async function startSSEStream(options: SSEStreamOptions): Promise<() => void> {
  const {
    query,
    mode = "global",
    topic_id,
    chat_id,
    onToken,
    onCitations,
    onDone,
    onError,
  } = options;

  // 构造请求URL
  const url = `${API_BASE_URL}/chat/ask`;

  // 构造请求体
  const payload = {
    query,
    mode,
    topic_id,
    chat_id,
    stream: true,
  };

  let aborted = false;
  let controller: AbortController | null = null;

  // 使用fetch API进行流式请求
  const fetchStream = async () => {
    try {
      controller = new AbortController();

      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        onError?.(`HTTP ${response.status}: ${errorText}`);
        return;
      }

      if (!response.body) {
        onError?.("Response body is null");
        return;
      }

      // 读取流
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent: string | null = null;

      while (!aborted) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        // 解码数据块
        buffer += decoder.decode(value, { stream: true });

        // 按行分割
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // 保留最后一行（可能不完整）

        for (const line of lines) {
          const trimmedLine = line.trim();

          if (!trimmedLine) {
            // 空行表示事件结束
            currentEvent = null;
            continue;
          }

          // 解析 event: 行
          if (trimmedLine.startsWith("event:")) {
            currentEvent = trimmedLine.substring(6).trim();
            continue;
          }

          // 解析 data: 行
          if (trimmedLine.startsWith("data:")) {
            const dataStr = trimmedLine.substring(5).trim();

            try {
              const data = JSON.parse(dataStr);

              // 根据事件类型处理
              if (currentEvent === "token") {
                onToken?.(data.content || "");
              } else if (currentEvent === "citations") {
                onCitations?.(data.citations || []);
              } else if (currentEvent === "done") {
                onDone?.(data.diagnostics || {});
              } else if (currentEvent === "error") {
                onError?.(data.message || "Unknown error");
              }
            } catch (e) {
              console.error("Failed to parse SSE data:", dataStr, e);
            }
          }
        }
      }
    } catch (error) {
      if (!aborted) {
        onError?.(error instanceof Error ? error.message : String(error));
      }
    }
  };

  // 启动流式请求
  fetchStream();

  // 返回清理函数
  return () => {
    aborted = true;
    controller?.abort();
  };
}

/**
 * 简化的流式对话函数
 * 
 * @param query 用户问题
 * @param mode 对话模式
 * @param callbacks 回调函数
 * @returns 清理函数
 */
export async function askStream(
  query: string,
  mode: "topic" | "global" = "global",
  callbacks: {
    onToken?: (content: string) => void;
    onCitations?: (citations: SSECitationsEvent["data"]["citations"]) => void;
    onDone?: (diagnostics: SSEDoneEvent["data"]["diagnostics"]) => void;
    onError?: (message: string) => void;
  }
): Promise<() => void> {
  return startSSEStream({
    query,
    mode,
    ...callbacks,
  });
}
