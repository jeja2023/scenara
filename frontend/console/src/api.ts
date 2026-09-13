import type { ApiErrorBody, Envelope } from "./types";

export function revokeBlobUrl(value: string): void {
  if (value.startsWith("blob:")) URL.revokeObjectURL(value);
}

export interface ConnectionSettings {
  apiBase: string;
  token: string;
  tenantId: string;
  projectId: string;
}

export interface LoginSession {
  token: string;
  session: {
    session_id: string;
    tenant_id: string;
    project_id: string;
    user_id: string;
    expires_at: number;
  };
}

const STORAGE_KEY = "scenara.console.connection.v1";
const SESSION_TOKEN_KEY = "scenara.console.token.session.v1";
const PERSISTENT_TOKEN_KEY = "scenara.console.token.local.v1";
const defaults: ConnectionSettings = {
  apiBase: "",
  token: "",
  tenantId: "default",
  projectId: "default",
};

export function loadConnection(): ConnectionSettings {
  try {
    const stored = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? "{}",
    ) as Partial<ConnectionSettings>;
    return {
      ...defaults,
      ...stored,
      token:
        sessionStorage.getItem(SESSION_TOKEN_KEY) ??
        localStorage.getItem(PERSISTENT_TOKEN_KEY) ??
        stored.token ??
        "",
    } as ConnectionSettings;
  } catch {
    return { ...defaults };
  }
}

export function saveConnection(
  value: ConnectionSettings,
  options: { persistAuth?: boolean } = { persistAuth: false },
): void {
  const context: Omit<ConnectionSettings, "token"> = {
    apiBase: value.apiBase,
    tenantId: value.tenantId,
    projectId: value.projectId,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(context));
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
  localStorage.removeItem(PERSISTENT_TOKEN_KEY);
  const tokenStorage =
    options.persistAuth === false ? sessionStorage : localStorage;
  if (value.token) {
    tokenStorage.setItem(
      options.persistAuth === false ? SESSION_TOKEN_KEY : PERSISTENT_TOKEN_KEY,
      value.token,
    );
  }
}

function notifyAuthExpired(): void {
  clearConnectionToken();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("scenara:auth-expired"));
  }
}

export function connectionTokenIsPersistent(): boolean {
  return localStorage.getItem(PERSISTENT_TOKEN_KEY) !== null;
}

export function clearConnectionToken(): void {
  sessionStorage.removeItem(SESSION_TOKEN_KEY);
  localStorage.removeItem(PERSISTENT_TOKEN_KEY);
  try {
    const stored = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? "{}",
    ) as Partial<ConnectionSettings>;
    if ("token" in stored) {
      delete stored.token;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
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
    REQUEST_BODY_TOO_LARGE: "文件超过直传限制，请使用对象存储直传",
    STATE_CONFLICT: "数据状态已变化，请刷新后重试",
    TRAJECTORY_CONFLICT: "轨迹身份状态冲突，请刷新后重试",
    TRAJECTORY_NOT_FOUND: "未找到指定的轨迹身份或摄像头",
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
  return requestHeadersForConnection(init, loadConnection());
}

function requestHeadersForConnection(
  init: RequestInit,
  connection: ConnectionSettings,
): Headers {
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

export async function login(
  username: string,
  password: string,
): Promise<LoginSession> {
  const connection = loadConnection();
  let response: Response;
  try {
    response = await fetch(`${connection.apiBase}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      localizedHttpError(0, "NETWORK_ERROR"),
    );
  }
  const body = (await response.json().catch(() => ({}))) as
    Envelope<LoginSession> | ApiErrorBody;
  if (!response.ok) {
    const error = (body as ApiErrorBody).error;
    if (response.status === 401) notifyAuthExpired();
    throw new ApiError(
      response.status,
      error?.code ?? "HTTP_ERROR",
      localizedHttpError(response.status, error?.code ?? "HTTP_ERROR"),
      (body as ApiErrorBody).request_id,
    );
  }
  return (body as Envelope<LoginSession>).data;
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
  if (response.status === 401) notifyAuthExpired();
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
    if (response.status === 401) notifyAuthExpired();
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

const DIRECT_UPLOAD_THRESHOLD_BYTES = 512 * 1024 * 1024;
const HASH_CHUNK_BYTES = 8 * 1024 * 1024;
const SHA256_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b,
  0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
  0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7,
  0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152,
  0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
  0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
  0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
  0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
  0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

function rotateRight(value: number, amount: number): number {
  return (value >>> amount) | (value << (32 - amount));
}

class Sha256 {
  private readonly state = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  private readonly buffer = new Uint8Array(64);
  private bufferLength = 0;
  private bytesHashed = 0;

  update(data: Uint8Array): void {
    this.bytesHashed += data.length;
    let offset = 0;
    if (this.bufferLength) {
      const copied = Math.min(64 - this.bufferLength, data.length);
      this.buffer.set(data.subarray(0, copied), this.bufferLength);
      this.bufferLength += copied;
      offset += copied;
      if (this.bufferLength === 64) {
        this.compress(this.buffer);
        this.bufferLength = 0;
      }
    }
    while (offset + 64 <= data.length) {
      this.compress(data.subarray(offset, offset + 64));
      offset += 64;
    }
    if (offset < data.length) {
      this.buffer.set(data.subarray(offset), 0);
      this.bufferLength = data.length - offset;
    }
  }

  digest(): Uint8Array {
    const bitLength = this.bytesHashed * 8;
    const paddingLength = (this.bufferLength < 56 ? 56 - this.bufferLength : 120 - this.bufferLength) + 8;
    const padding = new Uint8Array(paddingLength);
    padding[0] = 0x80;
    let length = bitLength;
    for (let index = 0; index < 8; index += 1) {
      padding[padding.length - 1 - index] = length & 0xff;
      length = Math.floor(length / 256);
    }
    this.update(padding);
    const result = new Uint8Array(32);
    const view = new DataView(result.buffer);
    this.state.forEach((value, index) => view.setUint32(index * 4, value));
    return result;
  }

  private compress(block: Uint8Array): void {
    const words = new Uint32Array(64);
    const view = new DataView(block.buffer, block.byteOffset, block.byteLength);
    for (let index = 0; index < 16; index += 1) words[index] = view.getUint32(index * 4);
    for (let index = 16; index < 64; index += 1) {
      const value = words[index - 15]!;
      const gamma0 = rotateRight(value, 7) ^ rotateRight(value, 18) ^ (value >>> 3);
      const previous = words[index - 2]!;
      const gamma1 = rotateRight(previous, 17) ^ rotateRight(previous, 19) ^ (previous >>> 10);
      words[index] = (words[index - 16]! + gamma0 + words[index - 7]! + gamma1) >>> 0;
    }
    let a = this.state[0]!;
    let b = this.state[1]!;
    let c = this.state[2]!;
    let d = this.state[3]!;
    let e = this.state[4]!;
    let f = this.state[5]!;
    let g = this.state[6]!;
    let h = this.state[7]!;
    for (let index = 0; index < 64; index += 1) {
      const sigma1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + sigma1 + choice + SHA256_K[index]! + words[index]!) >>> 0;
      const sigma0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sigma0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }
    this.state[0] = (this.state[0]! + a) >>> 0;
    this.state[1] = (this.state[1]! + b) >>> 0;
    this.state[2] = (this.state[2]! + c) >>> 0;
    this.state[3] = (this.state[3]! + d) >>> 0;
    this.state[4] = (this.state[4]! + e) >>> 0;
    this.state[5] = (this.state[5]! + f) >>> 0;
    this.state[6] = (this.state[6]! + g) >>> 0;
    this.state[7] = (this.state[7]! + h) >>> 0;
  }
}

export async function sha256File(file: File): Promise<string> {
  const hash = new Sha256();
  for (let offset = 0; offset < file.size; offset += HASH_CHUNK_BYTES) {
    const chunk = await file.slice(offset, offset + HASH_CHUNK_BYTES).arrayBuffer();
    hash.update(new Uint8Array(chunk));
    // Yield between chunks so hashing a large file does not freeze the page.
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  return Array.from(hash.digest(), (value) => value.toString(16).padStart(2, "0")).join("");
}

function putPresignedFile(
  url: string,
  method: string,
  headers: Record<string, string>,
  file: File,
  onProgress?: (value: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(method, url, true);
    Object.entries(headers).forEach(([key, value]) => {
      // Browsers control Content-Length; setting it from JavaScript raises a
      // forbidden-header error even though the presigned request includes it.
      if (key.toLowerCase() !== "content-length") request.setRequestHeader(key, value);
    });
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    request.onerror = () => reject(new ApiError(0, "OBJECT_UPLOAD_FAILED", "无法连接对象存储"));
    request.onabort = () => reject(new ApiError(0, "OBJECT_UPLOAD_CANCELLED", "对象存储上传已取消"));
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else reject(new ApiError(request.status, "OBJECT_UPLOAD_FAILED", `对象存储上传失败（${request.status}）`));
    };
    request.send(file);
  });
}

export async function uploadAssetDirect(
  file: File,
  kind: "image" | "video" | "document",
  domain?: string,
  onProgress?: (value: number) => void,
): Promise<import("./types").MediaAsset> {
  onProgress?.(0);
  const request = {
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    kind,
    domain: domain || null,
    size_bytes: file.size,
    sha256: await sha256File(file),
  };
  const upload = await api<{
    upload_id: string;
    upload_token: string;
    method: "PUT";
    url: string;
    headers: Record<string, string>;
    expires_at: number;
  }>("/api/v1/media/uploads/presign", {
    method: "POST",
    body: JSON.stringify(request),
  });
  await putPresignedFile(upload.url, upload.method, upload.headers, file, onProgress);
  onProgress?.(1);
  return api<import("./types").MediaAsset>("/api/v1/media/uploads/complete", {
    method: "POST",
    body: JSON.stringify({
      ...request,
      upload_id: upload.upload_id,
      upload_token: upload.upload_token,
      expires_at: upload.expires_at,
    }),
  });
}

export function shouldUseDirectUpload(file: File): boolean {
  return file.size > DIRECT_UPLOAD_THRESHOLD_BYTES;
}

export async function apiBlob(path: string): Promise<Blob> {
  const response = await request(path, { headers: { Accept: "image/*" } });
  if (!response.ok) {
    if (response.status === 401) notifyAuthExpired();
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
      else reject(new Error("二进制响应未生成 Data URL"));
    };
    reader.onerror = () =>
      reject(reader.error ?? new Error("无法读取二进制响应"));
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
  if (!response.ok) {
    if (response.status === 401) notifyAuthExpired();
    throw await responseError(response);
  }
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
