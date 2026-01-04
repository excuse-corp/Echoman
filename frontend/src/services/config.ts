const defaultApiBaseUrl = "/api/v1";

function normalizeBaseUrl(value: string) {
  return value.replace(/\/+$/, "");
}

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL;

export const API_BASE_URL = normalizeBaseUrl(
  rawBaseUrl && rawBaseUrl.trim().length > 0 ? rawBaseUrl.trim() : defaultApiBaseUrl,
);

