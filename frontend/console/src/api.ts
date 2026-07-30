import type { ApiErrorBody, Envelope } from "./types";

export interface ConnectionSettings { apiBase: string; token: string; tenantId: string; projectId: string }

const STORAGE_KEY = "scenara.console.connection.v1";
const defaults: ConnectionSettings = { apiBase: "", token: "", tenantId: "default", projectId: "default" };

export function loadConnection(): ConnectionSettings {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") } as ConnectionSettings; }
  catch { return { ...defaults }; }
}

export function saveConnection(value: ConnectionSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string, readonly requestId?: string) {
    super(message);
  }
}

function localizedHttpError(status: number, code: string): string {
  const byCode: Record<string, string> = {
    AUDIT_UNAVAILABLE: "审计服务不可用，请稍后重试",
    FEEDBACK_CONFLICT: "反馈或发布状态冲突，请刷新后重试",
    FEEDBACK_NOT_FOUND: "未找到指定的反馈或发布记录",
    INVALID_ARGUMENT: "提交的参数无效，请检查后重试",
    INVALID_RUN_TRANSITION: "当前运行状态不允许执行此操作",
    NETWORK_ERROR: "无法连接到服务，请检查接口地址和网络",
    NOT_FOUND: "未找到请求的资源",
    PIPELINE_ERROR: "流水线配置或执行参数无效",
    POLICY_DENIED: "当前身份无权执行此操作",
    POLICY_UNAVAILABLE: "权限策略服务不可用，请稍后重试",
    PORTRAIT_CONFLICT: "人像数据状态冲突，请刷新后重试",
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
  return `请求失败（错误代码：${code}）`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const connection = loadConnection();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Tenant-Id", connection.tenantId);
  headers.set("X-Project-Id", connection.projectId);
  if (connection.token) headers.set("Authorization", `Bearer ${connection.token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${connection.apiBase}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", localizedHttpError(0, "NETWORK_ERROR"));
  }
  const body = await response.json().catch(() => ({})) as Envelope<T> | ApiErrorBody;
  if (!response.ok) {
    const error = (body as ApiErrorBody).error;
    const code = error?.code ?? "HTTP_ERROR";
    throw new ApiError(response.status, code, localizedHttpError(response.status, code), (body as ApiErrorBody).request_id);
  }
  return (body as Envelope<T>).data;
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${crypto.randomUUID()}`;
}
