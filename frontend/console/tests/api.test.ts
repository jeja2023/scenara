import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, saveConnection } from "../src/api";
import { labelCapability, labelDomain, labelPipeline, labelRunStatus } from "../src/labels";
import { routes } from "../src/router";

describe("console API contract", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    saveConnection({
      apiBase: "https://scenara.example",
      token: "token",
      tenantId: "tenant-a",
      projectId: "project-a",
    });
  });

  it("adds project context and unwraps the API envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ schema_version: "1.0", request_id: "req-1", data: { status: "ok" } }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api<{ status: string }>("/healthz")).resolves.toEqual({ status: "ok" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://scenara.example/healthz");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token");
    expect(headers.get("X-Tenant-Id")).toBe("tenant-a");
    expect(headers.get("X-Project-Id")).toBe("project-a");
  });

  it("preserves stable API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            request_id: "req-denied",
            error: { code: "POLICY_DENIED", message: "denied" },
          }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const error = await api("/api/v1/runs").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, code: "POLICY_DENIED", requestId: "req-denied" });
    expect((error as ApiError).message).toBe("当前身份无权执行此操作");
  });

  it("turns network failures into a Chinese message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("/healthz")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      message: "无法连接到服务，请检查接口地址和网络",
    });
  });
});

describe("console information architecture", () => {
  it("localizes API identifiers and unknown values", () => {
    expect(labelDomain("portrait")).toBe("人像");
    expect(labelCapability("face_detection")).toBe("人脸检测");
    expect(labelPipeline("ocr.document")).toBe("OCR 文档识别");
    expect(labelRunStatus("future-status")).toBe("未知状态");
    expect(labelCapability("future-capability")).toBe("未命名能力");
  });

  it("includes every 0.7 workspace", () => {
    const names = new Set(routes.map((route) => String(route.name ?? "fallback")));
    expect(names).toEqual(
      new Set([
        "overview",
        "media",
        "runs",
        "results",
        "portrait",
        "ocr",
        "pipelines",
        "models",
        "access",
        "operations",
        "enterprise",
        "feedback",
        "fallback",
      ]),
    );
  });

  it("keeps general-purpose interface labels in Chinese", () => {
    const collectVueFiles = (directory: string): string[] => readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const child = join(directory, entry.name);
      return entry.isDirectory() ? collectVueFiles(child) : entry.name.endsWith(".vue") ? [child] : [];
    });
    const source = collectVueFiles(join(process.cwd(), "src"))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    const untranslatedLabels = [
      "API 地址",
      "Bearer Token",
      "Webhook 订阅",
      "SLA",
      "运行 ID",
      "流水线 ID",
      "模型 ID",
      "数据集 ID",
      "<th>ID</th>",
      "<span>URL</span>",
      ">API v1<",
    ];
    expect(untranslatedLabels.filter((label) => source.includes(label))).toEqual([]);
  });
});

