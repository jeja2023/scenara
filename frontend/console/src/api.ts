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

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const connection = loadConnection();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Tenant-Id", connection.tenantId);
  headers.set("X-Project-Id", connection.projectId);
  if (connection.token) headers.set("Authorization", `Bearer ${connection.token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${connection.apiBase}${path}`, { ...init, headers, cache: "no-store" });
  const body = await response.json().catch(() => ({})) as Envelope<T> | ApiErrorBody;
  if (!response.ok) {
    const error = (body as ApiErrorBody).error;
    throw new ApiError(response.status, error?.code ?? "HTTP_ERROR", error?.message ?? `HTTP ${response.status}`, (body as ApiErrorBody).request_id);
  }
  return (body as Envelope<T>).data;
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${crypto.randomUUID()}`;
}
