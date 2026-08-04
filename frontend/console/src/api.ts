import type { ApiErrorBody, Envelope } from "./types";

export interface ConnectionSettings {
  apiBase: string;
  token: string;
  tenantId: string;
  projectId: string;
}

const STORAGE_KEY = "scenara.console.connection.v1";
const defaults: ConnectionSettings = {
  apiBase: "",
  token: "",
  tenantId: "default",
  projectId: "default",
};

export function loadConnection(): ConnectionSettings {
  try {
    return {
      ...defaults,
      ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}"),
    } as ConnectionSettings;
  } catch {
    return { ...defaults };
  }
}

export function saveConnection(value: ConnectionSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId?: string,
  ) {
    super(message);
  }
}

function localizedHttpError(status: number, code: string): string {
  const byCode: Record<string, string> = {
    AUDIT_UNAVAILABLE: "审计服务不可用，请稍后重试",
    FEEDBACK_CONFLICT: "反馈或发布状态冲突，请刷新后重试",
    FEEDBACK_NOT_FOUND: "未找到指定的反馈或发布记录",
    INVALID_ARGUMENT: "提交的参数无效，请检查后重试",
    INDEX_CONTRACT_ERROR: "索引契约不匹配，请刷新索引或调整输入",
    INVALID_RUN_TRANSITION: "当前运行状态不允许执行此操作",
    NETWORK_ERROR: "无法连接到服务，请检查接口地址和网络",
    NOT_FOUND: "未找到请求的资源",
    PIPELINE_ERROR: "流水线配置或执行参数无效",
    POLICY_DENIED: "当前身份无权执行此操作",
    POLICY_UNAVAILABLE: "权限策略服务不可用，请稍后重试",
    PORTRAIT_CONFLICT: "人像数据状态冲突，请刷新后重试",
    PORTRAIT_ENCODING_ERROR: "图片无法提取有效人像特征，请更换清晰图片",
    PORTRAIT_NOT_FOUND: "未找到指定的人像数据",
    STATE_CONFLICT: "数据状态已变化，请刷新后重试",
    VALIDATION_ERROR: "提交内容未通过校验，请检查必填项和格式",
    WEBHOOK_NOT_FOUND: "未找到指定的事件回调订阅",
  };
  if (byCode[code]) return byCode[code];
  if (status === 401) return "访问令牌无效或已失效";
  if (status === 403) return "当前身份无权执行此操作";
  if (status === 404) return "未找到请求的资源";
  if (status >= 500) return "服务暂时不可用，请稍后重试";
  return "请求失败，请检查输入后重试";
}

export function userFacingError(
  caught: unknown,
  fallback = "操作失败，请稍后重试",
): string {
  return caught instanceof ApiError ? caught.message : fallback;
}

function requestHeaders(init: RequestInit): Headers {
  const connection = loadConnection();
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  headers.set("X-Tenant-Id", connection.tenantId);
  headers.set("X-Project-Id", connection.projectId);
  if (connection.token)
    headers.set("Authorization", `Bearer ${connection.token}`);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  )
    headers.set("Content-Type", "application/json");
  return headers;
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const connection = loadConnection();
  let response: Response;
  try {
    response = await fetch(`${connection.apiBase}${path}`, {
      ...init,
      headers: requestHeaders(init),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      localizedHttpError(0, "NETWORK_ERROR"),
    );
  }
  return response;
}

async function responseError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
  const code = body.error?.code ?? "HTTP_ERROR";
  return new ApiError(
    response.status,
    code,
    localizedHttpError(response.status, code),
    body.request_id,
  );
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await request(path, init);
  const body = (await response.json().catch(() => ({}))) as
    Envelope<T> | ApiErrorBody;
  if (!response.ok) {
    const error = (body as ApiErrorBody).error;
    const code = error?.code ?? "HTTP_ERROR";
    throw new ApiError(
      response.status,
      code,
      localizedHttpError(response.status, code),
      (body as ApiErrorBody).request_id,
    );
  }
  return (body as Envelope<T>).data;
}

export async function apiForm<T>(path: string, form: FormData): Promise<T> {
  return api<T>(path, { method: "POST", body: form });
}

export async function apiBlob(path: string): Promise<Blob> {
  const response = await request(path, { headers: { Accept: "image/*" } });
  if (!response.ok) {
    throw await responseError(response);
  }
  return await response.blob();
}

/**
 * 把二进制响应转成可直接渲染的 Data URL。
 * 控制台的内容安全策略允许同源、data: 和 blob: 图片地址；二进制响应仍转成
 * Data URL，以便历史产物和跨页面预览保持一致。
 */
export function blobToDataUrl(value: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("binary response did not produce a data URL"));
    };
    reader.onerror = () =>
      reject(reader.error ?? new Error("binary response could not be read"));
    reader.readAsDataURL(value);
  });
}

/** 拉取一张图片接口响应并转为 Data URL。 */
export async function apiImageDataUrl(path: string): Promise<string> {
  return blobToDataUrl(await apiBlob(path));
}

export async function apiStream(
  path: string,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await request(path, {
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response;
}

function parseEventData<T>(block: string): T | undefined {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
  if (!data) return undefined;
  try {
    return JSON.parse(data) as T;
  } catch {
    return undefined;
  }
}

export async function* streamJsonEvents<T>(
  response: Response,
): AsyncGenerator<T> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const data = parseEventData<T>(block);
        if (data !== undefined) yield data;
      }
      if (done) break;
    }
    const trailing = parseEventData<T>(buffer);
    if (trailing !== undefined) yield trailing;
  } finally {
    reader.releaseLock();
  }
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${crypto.randomUUID()}`;
}
