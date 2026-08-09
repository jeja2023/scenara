import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  apiBlob,
  apiImageDataUrl,
  streamJsonEvents,
} from "../src/api";
import ParseView from "../src/views/ParseView.vue";

const routerMocks = vi.hoisted(() => ({
  replace: vi.fn(async () => undefined),
  push: vi.fn(async () => undefined),
}));

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => routerMocks,
}));

vi.mock("../src/api", () => {
  class MockApiError extends Error {
    constructor(
      readonly status: number,
      readonly code: string,
      message: string,
      readonly requestId?: string,
    ) {
      super(message);
    }
  }

  return {
    ApiError: MockApiError,
    api: vi.fn(),
    apiBlob: vi.fn(async () => new Blob(["preview"], { type: "image/jpeg" })),
    apiImageDataUrl: vi.fn(
      async (path: string) => `data:image/jpeg;base64,${btoa(path)}`,
    ),
    apiStream: vi.fn(async () => new Response("")),
    blobToDataUrl: vi.fn(async () => "data:image/jpeg;base64,cHJldmlldw=="),
    idempotencyKey: vi.fn(() => "test-idempotency"),
    streamJsonEvents: vi.fn(async function* () {}),
    userFacingError: vi.fn((_error: unknown, fallback: string) => fallback),
  };
});

const apiMock = vi.mocked(api);
const apiBlobMock = vi.mocked(apiBlob);
const apiImageDataUrlMock = vi.mocked(apiImageDataUrl);
const streamJsonEventsMock = vi.mocked(streamJsonEvents);

function resultPage(offset: number) {
  const count = offset === 0 ? 1000 : 1;
  return {
    result: {
      schema_version: "1.0",
      run_id: "run-video",
      domain: "ocr",
      pipeline: { pipeline_id: "ocr.document", version: "0.1.0" },
      asset_id: "asset-video",
      source_id: null,
      units: Array.from({ length: count }, (_, index) => ({
        unit_id: `frame_${offset + index}`,
        unit_type: "frame",
        index: offset + index,
        pts_ms: (offset + index) * 1000,
        page_number: null,
        width: 640,
        height: 360,
        objects: [],
      })),
      domain_payload: { domain: "ocr", text: "", blocks: [] },
      relations: [],
      artifacts: [],
      models: [],
      timings: {},
      media_metadata: { width: 640, height: 360, sampled_units: 1001 },
      warnings: [],
      provenance: {},
      created_at: 1,
    },
    unit_offset: offset,
    unit_limit: 1000,
    unit_total: 1001,
  };
}

function portraitResult() {
  return {
    schema_version: "1.0",
    run_id: "run-portrait",
    domain: "portrait",
    pipeline: { pipeline_id: "portrait.analysis", version: "0.4.0" },
    asset_id: "asset-portrait",
    source_id: null,
    units: [
      {
        unit_id: "frame_0",
        unit_type: "frame",
        index: 0,
        pts_ms: 0,
        page_number: null,
        width: 200,
        height: 100,
        frame_artifact_id: "frame_a1",
        objects: [
          {
            object_id: "person_1",
            object_type: "person",
            score: 0.95,
            bbox: { x: 20, y: 10, width: 40, height: 50 },
            attributes: {},
            crop_artifact_id: "crop_p1",
          },
          {
            object_id: "face_1",
            object_type: "face",
            score: 0.9,
            bbox: { x: 30, y: 15, width: 10, height: 12 },
            attributes: {},
            crop_artifact_id: "crop_f1",
          },
        ],
      },
    ],
    domain_payload: {
      domain: "portrait",
      persons: [],
      faces: [],
      tracks: [],
      capabilities: [],
    },
    relations: [],
    artifacts: [
      {
        artifact_id: "crop_p1",
        artifact_type: "object_crop",
        object_key: "k1",
        content_type: "image/jpeg",
        sha256: "a",
      },
      {
        artifact_id: "crop_f1",
        artifact_type: "object_crop",
        object_key: "k2",
        content_type: "image/jpeg",
        sha256: "b",
      },
      {
        artifact_id: "frame_a1",
        artifact_type: "unit_frame",
        object_key: "k3",
        content_type: "image/jpeg",
        sha256: "c",
      },
    ],
    models: [],
    timings: {},
    media_metadata: { width: 200, height: 100, sampled_units: 1 },
    warnings: [],
    provenance: {},
    created_at: 1,
  };
}

function runRecord(runId: string, status: string) {
  return {
    run_id: runId,
    status,
    progress: status === "completed" ? 1 : 0.25,
    pipeline: { pipeline_id: "ocr.document", version: "2.1.0" },
    parameters: {},
    priority: 0,
    revision: 1,
    created_at: 1,
    updated_at: 1,
  };
}

const activePipelines = [
  {
    pipeline_id: "portrait.person-detection",
    version: "0.1.0",
    domain: "portrait",
    status: "active",
    pausable: true,
    nodes: [],
  },
  {
    pipeline_id: "portrait.analysis",
    version: "0.4.0",
    domain: "portrait",
    status: "active",
    pausable: true,
    nodes: [],
  },
  {
    pipeline_id: "ocr.document",
    version: "2.1.0",
    domain: "ocr",
    status: "active",
    pausable: true,
    nodes: [],
  },
  {
    pipeline_id: "thermal.inspection",
    version: "1.0.0",
    domain: "thermal",
    status: "active",
    pausable: true,
    nodes: [],
    parameter_schema: {
      sensitivity: {
        label: "灵敏度",
        control: "number",
        default: 0.8,
        minimum: 0,
        maximum: 1,
        step: 0.1,
      },
    },
  },
];
const activeDomains = [
  {
    domain_id: "portrait",
    display_name: "人像",
    schema_version: "1.0",
    console_route: "/parse?domain=portrait",
    capabilities: ["person_detection"],
    supported_media_kinds: ["image", "video", "stream"],
    default_pipeline_id: "portrait.person-detection",
    navigation_order: 10,
  },
  {
    domain_id: "ocr",
    display_name: "OCR 文档",
    schema_version: "1.0",
    console_route: "/parse?domain=ocr",
    capabilities: ["text_recognition"],
    supported_media_kinds: ["document", "image", "video", "stream"],
    default_pipeline_id: "ocr.document",
    navigation_order: 20,
  },
  {
    domain_id: "thermal",
    display_name: "热成像检测",
    schema_version: "1.0",
    console_route: "/parse?domain=thermal",
    capabilities: ["temperature_detection"],
    supported_media_kinds: ["image", "video"],
    default_pipeline_id: "thermal.inspection",
    navigation_order: 30,
  },
];

function workspaceApi(path: string, init?: RequestInit): unknown | undefined {
  if (path === "/api/v1/media/assets?limit=200")
    return { items: [], offset: 0, limit: 200, total: 0 };
  if (path === "/api/v1/media/sources?limit=200")
    return { items: [], offset: 0, limit: 200, total: 0 };
  if (path === "/api/v1/pipelines") return activePipelines;
  if (path === "/api/v1/domains") return activeDomains;
  if (path === "/api/v1/media/assets" && init?.method === "POST") {
    const form = init.body as FormData;
    const kind = String(form.get("kind"));
    return {
      asset_id: `asset-${kind}`,
      kind,
      filename: `sample.${kind}`,
      content_type: "application/octet-stream",
      size_bytes: 1,
      sha256: "a".repeat(64),
      metadata: {},
      temporary: false,
      created_at: 1,
    };
  }
  return undefined;
}

describe("media parse workbench", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    apiMock.mockClear();
    apiBlobMock.mockClear();
    apiImageDataUrlMock.mockClear();
    streamJsonEventsMock.mockClear();
    routerMocks.replace.mockClear();
    routerMocks.push.mockClear();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:sample-video"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(),
      strokeRect: vi.fn(),
      fillRect: vi.fn(),
      fillText: vi.fn(),
      measureText: vi.fn(() => ({ width: 20 })),
    } as unknown as CanvasRenderingContext2D);
    // restoreAllMocks 会清掉 vi.mock 工厂里的实现，因此每个用例都重新装配图片接口。
    apiImageDataUrlMock.mockImplementation(
      async (path: string) => `data:image/jpeg;base64,${btoa(path)}`,
    );
    streamJsonEventsMock.mockImplementation(async function* () {});
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/runs") return runRecord("run-video", "completed");
      if (path.includes("unit_offset=1000")) return resultPage(1000);
      if (path.includes("/result?")) return resultPage(0);
      throw new Error(`unexpected API path: ${path}`);
    });
  });

  it("parses video and merges every result page", async () => {
    const wrapper = mount(ParseView, {
      props: { initialDomain: "ocr" },
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(2)').trigger("click");
    await wrapper
      .findAll(".input-controls select")[0]!
      .setValue("scene_change");
    await wrapper.get("button.advanced-toggle").trigger("click");
    const fields = wrapper.findAll(".parameter-grid input");
    await fields[2]!.setValue("500");
    await fields[3]!.setValue("2500");
    await fields[4]!.setValue("0.2");
    await fields[5]!.setValue("1280");

    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "sample.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    await wrapper.get("button.button.primary").trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("1001"));

    expect(apiMock).toHaveBeenCalledWith(
      expect.stringContaining("unit_offset=1000"),
    );
    const runCall = apiMock.mock.calls.find(
      ([path]) => path === "/api/v1/runs",
    );
    const body = JSON.parse(String((runCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({
      domain: "ocr",
      pipeline: { pipeline_id: "ocr.document", version: "2.1.0" },
      asset_id: "asset-video",
      source_id: null,
      parameters: {
        sample_strategy: "scene_change",
        sample_start_ms: 500,
        sample_end_ms: 2500,
        scene_change_threshold: 0.2,
        frame_max_edge: 1280,
      },
    });
    expect(wrapper.findAll(".unit-list button")).toHaveLength(1001);
    wrapper.unmount();
  });

  it("uploads image and document assets before creating versioned runs", async () => {
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/runs") {
        const body = JSON.parse(String(init?.body));
        return body.asset_id === "asset-document"
          ? runRecord("run-document", "failed")
          : runRecord("run-image", "completed");
      }
      if (path.includes("/api/v1/runs/run-image/result?")) return resultPage(0);
      throw new Error(`unexpected API path: ${path}`);
    });

    const imageWrapper = mount(ParseView, {
      props: { initialDomain: "ocr" },
      attachTo: document.body,
    });
    await flushPromises();
    const imageInput = imageWrapper.get('input[type="file"]');
    Object.defineProperty(imageInput.element, "files", {
      configurable: true,
      value: [new File(["image"], "sample.png", { type: "image/png" })],
    });
    await imageInput.trigger("change");
    await imageWrapper.get("button.button.primary").trigger("click");
    const imageRunCall = apiMock.mock.calls.find(
      ([path]) => path === "/api/v1/runs",
    );
    expect(
      JSON.parse(String((imageRunCall?.[1] as RequestInit).body)),
    ).toMatchObject({
      domain: "ocr",
      pipeline: { pipeline_id: "ocr.document", version: "2.1.0" },
      asset_id: "asset-image",
      parameters: {},
    });
    imageWrapper.unmount();

    const documentWrapper = mount(ParseView, {
      props: { initialDomain: "ocr" },
      attachTo: document.body,
    });
    await flushPromises();
    await documentWrapper.get('[role="tab"]:nth-child(3)').trigger("click");
    const documentFields = documentWrapper.findAll(".parameter-grid input");
    await documentFields[0]!.setValue("20");
    await documentFields[1]!.setValue("2.5");
    const documentInput = documentWrapper.get('input[type="file"]');
    Object.defineProperty(documentInput.element, "files", {
      configurable: true,
      value: [
        new File(["document"], "sample.pdf", { type: "application/pdf" }),
      ],
    });
    await documentInput.trigger("change");
    await documentWrapper.get("button.button.primary").trigger("click");
    const runCalls = apiMock.mock.calls.filter(
      ([path]) => path === "/api/v1/runs",
    );
    const documentBody = JSON.parse(
      String((runCalls.at(-1)?.[1] as RequestInit).body),
    );
    expect(documentBody).toMatchObject({
      domain: "ocr",
      pipeline: { pipeline_id: "ocr.document", version: "2.1.0" },
      asset_id: "asset-document",
      parameters: { max_units: 20, page_scale: 2.5 },
    });
    documentWrapper.unmount();
  });

  it("retries a transient network interruption while polling a run", async () => {
    let runReads = 0;
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) {
        if (path === "/api/v1/media/assets" && init?.method === "POST")
          return { ...(workspace as object), asset_id: "asset-retry" };
        return workspace;
      }
      if (path === "/api/v1/runs") return runRecord("run-retry", "queued");
      if (path === "/api/v1/runs/run-retry") {
        runReads += 1;
        if (runReads === 1)
          throw new ApiError(0, "NETWORK_ERROR", "connection interrupted");
        return runRecord("run-retry", "completed");
      }
      if (path.includes("unit_offset=1000")) return resultPage(1000);
      if (path.includes("/result?")) return resultPage(0);
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, {
      props: { initialDomain: "ocr" },
      attachTo: document.body,
    });
    await flushPromises();
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["image"], "sample.png", { type: "image/png" })],
    });
    await input.trigger("change");
    await wrapper.get("button.button.primary").trigger("click");

    await vi.waitFor(() => expect(runReads).toBe(2), { timeout: 3_000 });
    await vi.waitFor(() => expect(wrapper.text()).toContain("1001"));
    expect(wrapper.text()).not.toContain("connection interrupted");
    wrapper.unmount();
  });

  it("renders progress and partial detection results before the run completes", async () => {
    let finishStream: (() => void) | undefined;
    let completed = false;
    streamJsonEventsMock.mockImplementation(async function* () {
      yield {
        event_type: "result.partial",
        status: "running",
        payload: { unit_count: 1, progress: 0 },
      };
      yield {
        event_type: "run.progress",
        status: "running",
        payload: { progress: 0.5, processed_units: 1, expected_units: 2 },
      };
      await new Promise<void>((resolve) => {
        finishStream = resolve;
      });
      completed = true;
      yield { event_type: "run.completed", status: "completed", payload: {} };
      yield { event_type: "run.running", status: "running", payload: {} };
    });
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/runs")
        return {
          ...runRecord("run-live", "running"),
          domain: "portrait",
          pipeline: {
            pipeline_id: "portrait.person-detection",
            version: "0.1.0",
          },
        };
      if (path === "/api/v1/runs/run-live")
        return runRecord("run-live", completed ? "completed" : "running");
      if (path.includes("/api/v1/runs/run-live/result?")) {
        const liveResult = { ...portraitResult(), run_id: "run-live" };
        return {
          result: liveResult,
          unit_offset: 0,
          unit_limit: 1000,
          unit_total: 1,
        };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, {
      props: { initialDomain: "portrait" },
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(2)').trigger("click");
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "live.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    const execution = wrapper.get("button.button.primary").trigger("click");

    await vi.waitFor(() => expect(wrapper.text()).toContain("50%"));
    expect(wrapper.text()).toContain("1 / 2 个单元");
    expect(wrapper.text()).toContain("运行中");
    await vi.waitFor(() =>
      expect(wrapper.findAll(".unit-list button")).toHaveLength(1),
    );
    await vi.waitFor(() =>
      expect(wrapper.findAll(".crop-card")).toHaveLength(2),
    );

    finishStream?.();
    await execution;
    await vi.waitFor(() =>
      expect(wrapper.get(".run-strip .badge").text()).toBe("已完成"),
    );
    wrapper.unmount();
  });

  it("serializes the complete stream contract with the selected active version", async () => {
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/media/sources" && init?.method === "POST") {
        return {
          source_id: "source-1",
          name: "东门",
          masked_url: "rtsp://camera.example/live",
          metadata: {},
          created_at: 1,
        };
      }
      if (path === "/api/v1/runs") return runRecord("run-stream", "failed");
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, {
      props: { initialDomain: "ocr" },
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(4)').trigger("click");
    await flushPromises();
    await wrapper.get('input[placeholder="例如：东门摄像头"]').setValue("东门");
    await wrapper
      .get('input[placeholder="rtsp://host/path"]')
      .setValue("rtsp://camera.example/live");
    await wrapper.findAll(".input-controls select")[1]!.setValue("keyframe");
    await wrapper.get("button.advanced-toggle").trigger("click");
    const fields = wrapper.findAll(".parameter-grid input");
    await fields[1]!.setValue("8");
    await fields[2]!.setValue("250");
    await fields[3]!.setValue("5000");
    await fields[4]!.setValue("720");
    await fields[5]!.setValue("5");
    await fields[6]!.setValue("3000");
    await fields[7]!.setValue("2000");
    await wrapper.get("button.button.primary").trigger("click");

    const runCall = apiMock.mock.calls.find(
      ([path]) => path === "/api/v1/runs",
    );
    const body = JSON.parse(String((runCall?.[1] as RequestInit).body));
    expect(body.pipeline).toEqual({
      pipeline_id: "ocr.document",
      version: "2.1.0",
    });
    expect(body.source_id).toBe("source-1");
    expect(body.parameters).toMatchObject({
      sample_strategy: "keyframe",
      max_units: 8,
      sample_start_ms: 250,
      sample_end_ms: 5000,
      frame_max_edge: 720,
      max_reconnect_attempts: 5,
      connect_timeout_ms: 3000,
      read_timeout_ms: 2000,
    });
    expect(apiBlobMock).not.toHaveBeenCalledWith(
      "/api/v1/media/sources/source-1/preview",
    );
    wrapper.unmount();
  });

  it("tracks pause, resume, and cancelling until the run reaches a terminal state", async () => {
    let status = "running";
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/runs") return runRecord("run-control", "running");
      if (path.endsWith("/pause") && init?.method === "POST") {
        status = "paused";
        return runRecord("run-control", "pausing");
      }
      if (path.endsWith("/resume") && init?.method === "POST") {
        status = "running";
        return runRecord("run-control", "running");
      }
      if (path.endsWith("/cancel") && init?.method === "POST") {
        status = "cancelled";
        return runRecord("run-control", "cancelling");
      }
      if (path === "/api/v1/runs/run-control")
        return runRecord("run-control", status);
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, {
      props: { initialDomain: "ocr" },
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(2)').trigger("click");
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "sample.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    const execution = wrapper.get("button.button.primary").trigger("click");
    await vi.waitFor(() =>
      expect(
        wrapper
          .findAll("button")
          .some((button) => button.text().includes("暂停")),
      ).toBe(true),
    );
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("暂停"))!
      .trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("已暂停"), {
      timeout: 2_000,
    });
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("恢复"))!
      .trigger("click");
    await vi.waitFor(() =>
      expect(
        wrapper
          .findAll("button")
          .some((button) => button.text().includes("暂停")),
      ).toBe(true),
    );
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("取消运行"))!
      .trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("已取消"), {
      timeout: 2_000,
    });
    await execution;
    expect(apiMock).toHaveBeenCalledWith("/api/v1/runs/run-control/cancel", {
      method: "POST",
    });
    wrapper.unmount();
  });

  it("loads a new domain from the registry and renders its generic payload", async () => {
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/runs") {
        return {
          ...runRecord("run-thermal", "completed"),
          domain: "thermal",
          pipeline: {
            pipeline_id: "thermal.inspection",
            version: "1.0.0",
          },
        };
      }
      if (path.includes("/api/v1/runs/run-thermal/result?")) {
        return {
          ...resultPage(0),
          result: {
            ...resultPage(0).result,
            run_id: "run-thermal",
            domain: "thermal",
            pipeline: {
              pipeline_id: "thermal.inspection",
              version: "1.0.0",
            },
            domain_payload: {
              domain: "thermal",
              average_temperature: 42.5,
              hotspots: [{ name: "motor", temperature: 87.4 }],
            },
          },
          unit_total: 1,
        };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, {
      props: { initialDomain: "thermal" },
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.get('input[type="number"]').setValue("0.9");
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["image"], "thermal.png", { type: "image/png" })],
    });
    await input.trigger("change");
    await wrapper.get("button.button.primary").trigger("click");

    await vi.waitFor(() => expect(wrapper.text()).toContain("领域结果"));
    expect(wrapper.text()).toContain("average temperature");
    expect(wrapper.text()).toContain("motor");
    const runCall = apiMock.mock.calls.find(
      ([path]) => path === "/api/v1/runs",
    );
    expect(
      JSON.parse(String((runCall?.[1] as RequestInit).body)),
    ).toMatchObject({
      domain: "thermal",
      pipeline: { pipeline_id: "thermal.inspection", version: "1.0.0" },
      parameters: { sensitivity: 0.9 },
    });
    wrapper.unmount();
  });

  it("shows a feature crop per detected object and opens the original image on click", async () => {
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      const workspace = workspaceApi(path, init);
      if (workspace !== undefined) return workspace;
      if (path === "/api/v1/runs")
        return {
          ...runRecord("run-portrait", "completed"),
          domain: "portrait",
          pipeline: {
            pipeline_id: "portrait.person-detection",
            version: "0.1.0",
          },
        };
      if (path.includes("/api/v1/runs/run-portrait/result?")) {
        return {
          result: portraitResult(),
          unit_offset: 0,
          unit_limit: 1000,
          unit_total: 1,
        };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, {
      props: { initialDomain: "portrait" },
      attachTo: document.body,
    });
    await flushPromises();
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["image"], "portrait.png", { type: "image/png" })],
    });
    await input.trigger("change");
    await wrapper.get("button.button.primary").trigger("click");

    // Crops render by default, one card per detected object.
    await vi.waitFor(() =>
      expect(wrapper.findAll(".crop-card")).toHaveLength(2),
    );
    expect(apiImageDataUrlMock).toHaveBeenCalledWith(
      "/api/v1/runs/run-portrait/artifacts/crop_p1",
    );
    expect(apiImageDataUrlMock).toHaveBeenCalledWith(
      "/api/v1/runs/run-portrait/artifacts/crop_f1",
    );
    expect(wrapper.find(".lightbox").exists()).toBe(false);

    // Clicking a crop opens the large original image with the object highlighted.
    await wrapper.findAll(".crop-card")[0]!.trigger("click");
    await vi.waitFor(() =>
      expect(wrapper.find(".lightbox").exists()).toBe(true),
    );
    expect(apiImageDataUrlMock).toHaveBeenCalledWith(
      "/api/v1/runs/run-portrait/artifacts/frame_a1",
    );
    const highlight = wrapper.get(".lightbox-highlight");
    expect(highlight.attributes("style")).toContain("left: 10%");
    expect(highlight.attributes("style")).toContain("width: 20%");
    expect(wrapper.get(".lightbox-panel header").text()).toContain("1 / 2");

    // Arrow keys move between objects, Escape closes the lightbox.
    await wrapper.get(".lightbox").trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.get(".lightbox-panel header").text()).toContain("2 / 2");
    await wrapper.get(".lightbox").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".lightbox").exists()).toBe(false);
    wrapper.unmount();
  });
});
