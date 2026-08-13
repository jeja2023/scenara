import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  apiStream,
  login,
  saveConnection,
  streamJsonEvents,
  userFacingError,
} from "../src/api";
import { completeSignIn, isSignedIn, signOut } from "../src/auth";
import {
  labelAccessCapability,
  labelCapability,
  labelDomain,
  labelDomainDescription,
  labelDomainDisplayName,
  labelEntitlementSource,
  labelPipeline,
  labelPipelineDisplayName,
  labelPortraitAsset,
  labelPortraitCapability,
  labelPortraitMaturity,
  labelPortraitModule,
  labelPortraitReadiness,
  labelProductGate,
  labelProductSummary,
  labelRunStatus,
  labelVersion,
  labelWarning,
} from "../src/labels";
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
        JSON.stringify({
          schema_version: "1.0",
          request_id: "req-1",
          data: { status: "ok" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api<{ status: string }>("/healthz")).resolves.toEqual({
      status: "ok",
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://scenara.example/healthz");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer token");
    expect(headers.get("X-Tenant-Id")).toBe("tenant-a");
    expect(headers.get("X-Project-Id")).toBe("project-a");
  });

  it("submits username and password to the login boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          schema_version: "1.0",
          request_id: "req-login",
          data: {
            token: "session-token",
            session: {
              session_id: "ses-1",
              tenant_id: "tenant-a",
              project_id: "project-a",
              user_id: "console-user",
              expires_at: 2,
            },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      login("console-user", "correct-password"),
    ).resolves.toMatchObject({
      token: "session-token",
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://scenara.example/api/v1/auth/login");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("X-Tenant-Id")).toBeNull();
    expect(headers.get("X-Project-Id")).toBeNull();
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({
      username: "console-user",
      password: "correct-password",
    });
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
    expect(error).toMatchObject({
      status: 403,
      code: "POLICY_DENIED",
      requestId: "req-denied",
    });
    expect((error as ApiError).message).toBe("当前身份无权执行此操作");
  });

  it("dispatches auth-expired event and clears session on 401 response", async () => {
    const expiredListener = vi.fn();
    window.addEventListener("scenara:auth-expired", expiredListener);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            request_id: "req-expired",
            error: { code: "POLICY_DENIED", message: "Token expired" },
          }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(api("/api/v1/runs")).rejects.toBeInstanceOf(ApiError);
    expect(expiredListener).toHaveBeenCalledOnce();
    window.removeEventListener("scenara:auth-expired", expiredListener);
  });

  it("evaluates session timestamp expiration in isSignedIn", () => {
    completeSignIn(
      { apiBase: "", token: "abc", tenantId: "default", projectId: "default" },
      false,
      Math.floor(Date.now() / 1000) - 60,
    );
    expect(isSignedIn()).toBe(false);

    completeSignIn(
      { apiBase: "", token: "abc", tenantId: "default", projectId: "default" },
      false,
      Math.floor(Date.now() / 1000) + 3600,
    );
    expect(isSignedIn()).toBe(true);
    signOut();
  });

  it("turns network failures into a Chinese message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(api("/healthz")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      message: "无法连接到服务，请检查接口地址和网络",
    });
  });

  it("uses the configured connection for event streams", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("data: {}\n\n", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await apiStream("/api/v1/runs/run-1/events", controller.signal);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://scenara.example/api/v1/runs/run-1/events");
    expect(init.signal).toBe(controller.signal);
    const headers = new Headers(init.headers);
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(headers.get("Authorization")).toBe("Bearer token");
    expect(headers.get("X-Tenant-Id")).toBe("tenant-a");
    expect(headers.get("X-Project-Id")).toBe("project-a");
  });

  it("parses CRLF and multi-line event data", async () => {
    const response = new Response(
      'id: 1\r\nevent: run.running\r\ndata: {"status":\r\ndata: "running"}\r\n\r\n: heartbeat\r\n\r\ndata: {"status":"completed"}\r\n\r\n',
    );
    const events: Array<{ status: string }> = [];
    for await (const event of streamJsonEvents<{ status: string }>(response))
      events.push(event);
    expect(events).toEqual([{ status: "running" }, { status: "completed" }]);
  });

  it("rejects event-stream HTTP errors as stable API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            request_id: "req-stream",
            error: { code: "POLICY_DENIED" },
          }),
          { status: 403 },
        ),
      ),
    );
    await expect(apiStream("/api/v1/runs/run-1/events")).rejects.toMatchObject({
      status: 403,
      code: "POLICY_DENIED",
      requestId: "req-stream",
    });
  });
});

describe("console information architecture", () => {
  it("localizes API identifiers and unknown values", () => {
    expect(labelDomain("portrait")).toBe("人像");
    expect(labelDomain("vehicle.inspection")).toBe("Vehicle Inspection");
    expect(labelDomainDisplayName("portrait", "Portrait")).toBe("人像");
    expect(labelDomainDisplayName("thermal", "热成像")).toBe("热成像");
    expect(labelDomainDisplayName("thermal", "Thermal")).toBe("自定义领域");
    expect(
      labelDomainDescription("portrait", "English backend description"),
    ).toBe("检测人员并分析人像相关的视觉特征。");
    expect(
      labelDomainDescription("thermal", "English backend description"),
    ).toBe(
      "该领域已接入统一解析工作区，可通过已启用的流水线处理支持的数据类型。",
    );
    expect(labelCapability("face_detection")).toBe("人脸检测");
    expect(labelPipeline("ocr.document")).toBe("OCR 文档识别");
    expect(labelPipelineDisplayName("custom.pipeline")).toBe(
      "自定义解析流水线",
    );
    expect(labelRunStatus("future-status")).toBe("未知状态");
    expect(labelCapability("future-capability")).toBe("未命名能力");
    expect(labelProductSummary("parse")).toContain("视觉解析");
    expect(labelProductGate("edge")).toContain("服务端部署");
    expect(labelAccessCapability("api_authentication").name).toBe("接口认证");
    expect(labelEntitlementSource("manual")).toBe("手动配置");
    expect(labelWarning("gait_requires_at_least_8_frames")).toBe(
      "步态分析至少需要 8 帧画面",
    );
    expect(labelWarning("media_termination:source_ended")).toBe(
      "媒体源已正常读完，本次任务已完成全部可读取内容。",
    );
    expect(labelWarning("media_termination:max_units_reached")).toContain(
      "新运行已取消此限制",
    );
    expect(labelWarning("artifact_quota_reached")).toContain(
      "特征图片数量已达到本次运行的上限",
    );
    expect(labelWarning("artifact_crop_quota_reached")).toContain(
      "特征裁剪图片数量已达到本次运行的上限",
    );
    expect(labelWarning("artifact_frame_quota_reached")).toContain(
      "该历史运行创建时仍启用了结果帧数量上限",
    );
    expect(labelVersion("0.3.0.dev6")).toBe("0.3.0 开发版 6");
    expect(userFacingError(new TypeError("Failed to fetch"))).toBe(
      "操作失败，请稍后重试",
    );
    // Portrait Intelligence Foundation Platform labels
    expect(labelPortraitModule("data_governance")).toBe("数据治理");
    expect(labelPortraitModule("annotation")).toBe("标注平台");
    expect(labelPortraitModule("training")).toBe("模型训练");
    expect(labelPortraitModule("algorithms")).toBe("人像算法");
    expect(labelPortraitModule("vector_retrieval")).toBe("向量检索");
    expect(labelPortraitModule("mlops")).toBe("模型运维");
    expect(labelPortraitModule("unknown-module")).toBe("其他能力模块");
    expect(labelPortraitMaturity("available")).toBe("可用");
    expect(labelPortraitMaturity("partial")).toBe("部分可用");
    expect(labelPortraitMaturity("external")).toBe("外部仓库承担");
    expect(labelPortraitMaturity("planned")).toBe("规划中");
    expect(labelPortraitReadiness("ready")).toBe("已就绪");
    expect(labelPortraitReadiness("fallback")).toBe("开发替代");
    expect(labelPortraitReadiness("placeholder")).toBe("占位实现");
    expect(labelPortraitReadiness("not_configured")).toBe("未配置");
    expect(labelPortraitAsset("data_lake")).toBe("人像数据湖");
    expect(labelPortraitAsset("foundation_model")).toBe("人像基础模型");
    expect(labelPortraitAsset("intelligence_engine")).toBe("人像智能引擎");
    expect(labelPortraitCapability("person_detection")).toBe("人员检测");
    expect(labelPortraitCapability("face_embedding")).toBe("人脸识别特征");
    expect(labelPortraitCapability("pose")).toBe("姿态估计");
  });

  it("maintains distinct parsing workspace navigation routes", () => {
    const names = new Set(
      routes.map((route) => String(route.name ?? "fallback")),
    );
    expect(names).toEqual(
      new Set([
        "login",
        "overview",
        "portrait-parse",
        "ocr-parse",
        "parse-domain",
        "parse-media",
        "assets",
        "datasets",
        "results",
        "search",
        "trajectories",
        "portrait-compare",
        "runs",
        "capabilities",
        "pipelines",
        "models",
        "access",
        "operations",
        "audit",
        "governance",
        "feedback",
        "fallback",
      ]),
    );
  });

  it("keeps general-purpose interface labels in Chinese", () => {
    const collectVueFiles = (directory: string): string[] =>
      readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const child = join(directory, entry.name);
        return entry.isDirectory()
          ? collectVueFiles(child)
          : entry.name.endsWith(".vue")
            ? [child]
            : [];
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
      "项目 ID",
      "用户 ID",
      "角色 ID",
      "主体 ID",
      "账号 ID",
      ">Scope<",
      ">API Keys<",
      "<th>Key</th>",
      "Key 名称",
      "签发 Key",
      "API Key 已签发",
      "暂无 API Key",
      "接口 v1",
    ];
    expect(
      untranslatedLabels.filter((label) => source.includes(label)),
    ).toEqual([]);
  });
});
