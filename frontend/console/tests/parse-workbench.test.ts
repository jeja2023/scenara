import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api";
import ParseView from "../src/views/ParseView.vue";

vi.mock("../src/api", () => ({
  api: vi.fn(),
  apiStream: vi.fn(async () => new Response("")),
  idempotencyKey: vi.fn(() => "test-idempotency"),
  streamJsonEvents: vi.fn(async function* () {}),
  userFacingError: vi.fn((_error: unknown, fallback: string) => fallback),
}));

const apiMock = vi.mocked(api);

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

describe("media parse workbench", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:sample-video"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    apiMock.mockImplementation(async (path: string) => {
      if (path.startsWith("/api/v1/media/sources")) {
        return { items: [], offset: 0, limit: 200, total: 0 };
      }
      if (path === "/api/v1/parse/video") {
        return {
          asset: { asset_id: "asset-video", metadata: {} },
          run: { run_id: "run-video", status: "completed", progress: 1 },
          result: null,
        };
      }
      if (path.includes("unit_offset=1000")) return resultPage(1000);
      if (path.includes("/result?")) return resultPage(0);
      throw new Error(`unexpected API path: ${path}`);
    });
  });

  it("parses video and merges every result page", async () => {
    const wrapper = mount(ParseView, { props: { domain: "ocr" }, attachTo: document.body });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(2)').trigger("click");
    await wrapper.get("select").setValue("scene_change");
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
    const parseCall = apiMock.mock.calls.find(([path]) => path === "/api/v1/parse/video");
    const form = (parseCall?.[1] as RequestInit).body as FormData;
    expect(Object.fromEntries(form.entries())).toMatchObject({
      sample_strategy: "scene_change",
      sample_start_ms: "500",
      sample_end_ms: "2500",
      scene_change_threshold: "0.2",
      frame_max_edge: "1280",
    });
    expect(wrapper.findAll(".unit-list button")).toHaveLength(1001);
    wrapper.unmount();
  });

  it("serializes image and document shortcuts without a hard-coded pipeline version", async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.startsWith("/api/v1/media/sources")) return { items: [], offset: 0, limit: 200, total: 0 };
      if (path === "/api/v1/parse/image") {
        return { asset: { asset_id: "asset-image", metadata: {} }, run: runRecord("run-image", "completed"), result: resultPage(0).result };
      }
      if (path === "/api/v1/parse/document") {
        return { asset: { asset_id: "asset-document", metadata: {} }, run: runRecord("run-document", "failed"), result: null };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    const imageWrapper = mount(ParseView, { props: { domain: "ocr" }, attachTo: document.body });
    await flushPromises();
    const imageInput = imageWrapper.get('input[type="file"]');
    Object.defineProperty(imageInput.element, "files", {
      configurable: true,
      value: [new File(["image"], "sample.png", { type: "image/png" })],
    });
    await imageInput.trigger("change");
    await imageWrapper.get("button.button.primary").trigger("click");
    const imageCall = apiMock.mock.calls.find(([path]) => path === "/api/v1/parse/image");
    const imageForm = (imageCall?.[1] as RequestInit).body as FormData;
    expect(Object.fromEntries(imageForm.entries())).toMatchObject({ domain: "ocr", pipeline_id: "ocr.document" });
    expect(imageForm.has("pipeline_version")).toBe(false);
    imageWrapper.unmount();

    const documentWrapper = mount(ParseView, { props: { domain: "ocr" }, attachTo: document.body });
    await flushPromises();
    await documentWrapper.get('[role="tab"]:nth-child(3)').trigger("click");
    const documentFields = documentWrapper.findAll(".parameter-grid input");
    await documentFields[0]!.setValue("20");
    await documentFields[1]!.setValue("2.5");
    const documentInput = documentWrapper.get('input[type="file"]');
    Object.defineProperty(documentInput.element, "files", {
      configurable: true,
      value: [new File(["document"], "sample.pdf", { type: "application/pdf" })],
    });
    await documentInput.trigger("change");
    await documentWrapper.get("button.button.primary").trigger("click");
    const documentCall = apiMock.mock.calls.find(([path]) => path === "/api/v1/parse/document");
    const documentForm = (documentCall?.[1] as RequestInit).body as FormData;
    expect(Object.fromEntries(documentForm.entries())).toMatchObject({
      domain: "ocr",
      pipeline_id: "ocr.document",
      max_units: "20",
      page_scale: "2.5",
    });
    expect(documentForm.has("pipeline_version")).toBe(false);
    documentWrapper.unmount();
  });

  it("serializes the complete stream contract and lets the server resolve the active version", async () => {
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path.startsWith("/api/v1/media/sources") && init?.method !== "POST") {
        return { items: [], offset: 0, limit: 200, total: 0 };
      }
      if (path === "/api/v1/media/sources" && init?.method === "POST") {
        return { source_id: "source-1", name: "东门", masked_url: "rtsp://camera.example/live", metadata: {}, created_at: 1 };
      }
      if (path === "/api/v1/parse/stream") return runRecord("run-stream", "failed");
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, { props: { domain: "ocr" }, attachTo: document.body });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(4)').trigger("click");
    await flushPromises();
    await wrapper.get('input[placeholder="例如：东门摄像头"]').setValue("东门");
    await wrapper.get('input[placeholder="rtsp://host/path"]').setValue("rtsp://camera.example/live");
    await wrapper.findAll("select")[1]!.setValue("keyframe");
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

    const parseCall = apiMock.mock.calls.find(([path]) => path === "/api/v1/parse/stream");
    const body = JSON.parse(String((parseCall?.[1] as RequestInit).body));
    expect(body.pipeline).toEqual({ pipeline_id: "ocr.document" });
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
    wrapper.unmount();
  });

  it("tracks pause, resume, and cancelling until the run reaches a terminal state", async () => {
    let status = "running";
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path.startsWith("/api/v1/media/sources")) return { items: [], offset: 0, limit: 200, total: 0 };
      if (path === "/api/v1/parse/video") return { asset: { asset_id: "asset-control", metadata: {} }, run: runRecord("run-control", "running"), result: null };
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
      if (path === "/api/v1/runs/run-control") return runRecord("run-control", status);
      throw new Error(`unexpected API path: ${path}`);
    });

    const wrapper = mount(ParseView, { props: { domain: "ocr" }, attachTo: document.body });
    await flushPromises();
    await wrapper.get('[role="tab"]:nth-child(2)').trigger("click");
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      configurable: true,
      value: [new File(["video"], "sample.mp4", { type: "video/mp4" })],
    });
    await input.trigger("change");
    const execution = wrapper.get("button.button.primary").trigger("click");
    await vi.waitFor(() => expect(wrapper.findAll("button").some((button) => button.text().includes("暂停"))).toBe(true));
    await wrapper.findAll("button").find((button) => button.text().includes("暂停"))!.trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("已暂停"), { timeout: 2_000 });
    await wrapper.findAll("button").find((button) => button.text().includes("恢复"))!.trigger("click");
    await vi.waitFor(() => expect(wrapper.findAll("button").some((button) => button.text().includes("暂停"))).toBe(true));
    await wrapper.findAll("button").find((button) => button.text().includes("取消运行"))!.trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("已取消"), { timeout: 2_000 });
    await execution;
    expect(apiMock).toHaveBeenCalledWith("/api/v1/runs/run-control/cancel", { method: "POST" });
    wrapper.unmount();
  });
});
