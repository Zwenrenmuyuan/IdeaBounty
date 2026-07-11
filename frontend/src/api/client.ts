import { ApiError } from "@/types";

const BASE_URL = "/api";

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

interface FastApiValidationError {
  type: string;
  loc: (string | number)[];
  msg: string;
}

function formatValidationErrors(errors: FastApiValidationError[]): string {
  return errors
    .map((err) => {
      const field = err.loc.filter((p) => p !== "body").join(".") || "body";
      return `${field}: ${err.msg}`;
    })
    .join("；");
}

function extractErrorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;

    if (Array.isArray(detail)) {
      const formatted = formatValidationErrors(
        detail as FastApiValidationError[],
      );
      if (formatted) return formatted;
    }

    if (typeof detail === "string" && detail) return detail;

    if (detail !== null && typeof detail === "object") {
      return JSON.stringify(detail);
    }
  }

  if (status === 401) return "登录已过期，请重新登录";
  if (status === 403) return "无权限执行此操作";
  if (status === 404) return "请求的资源不存在或不可访问";

  return `请求失败 (${status})`;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, signal } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "include",
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new ApiError("网络连接失败，请稍后重试", 0);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = extractErrorMessage(data, response.status);
    const detailStr =
      data && typeof data === "object" && "detail" in data
        ? typeof (data as { detail: unknown }).detail === "string"
          ? ((data as { detail: string }).detail)
          : undefined
        : undefined;
    throw new ApiError(message, response.status, detailStr);
  }

  return data as T;
}

export const apiClient = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { signal }),

  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: "POST", body, signal }),

  delete: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { method: "DELETE", signal }),
};
