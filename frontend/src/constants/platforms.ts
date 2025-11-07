/**
 * 平台配置和映射
 * 
 * 统一管理所有平台的中英文映射，避免在多个组件中重复定义
 */

export type PlatformKey = 
  | "weibo"
  | "zhihu"
  | "toutiao"
  | "sina"
  | "tencent"
  | "netease"
  | "baidu"
  | "hupu"
  | "xiaohongshu"
  | "douyin";

/**
 * 平台中文名称映射表
 */
export const PLATFORM_LABELS: Record<string, string> = {
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

/**
 * 获取平台的中文名称
 * @param platformKey 平台英文key
 * @returns 平台中文名称，如果找不到则返回原key
 */
export function getPlatformLabel(platformKey: string): string {
  return PLATFORM_LABELS[platformKey] ?? platformKey;
}

/**
 * 当前启用的数据源平台（用于首页展示）
 */
export const ENABLED_PLATFORMS = [
  "微博",
  "知乎",
  "今日头条",
  "新浪新闻",
  "网易新闻",
  "百度热搜",
  "虎扑",
];

