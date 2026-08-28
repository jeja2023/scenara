import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { api, apiImageDataUrl } from "../src/api";
import ResultsView from "../src/views/ResultsView.vue";

vi.mock("../src/api", () => ({
  api: vi.fn(),
  apiImageDataUrl: vi.fn(
    async (path: string) => `data:image/jpeg;base64,${btoa(path)}`,
  ),
  userFacingError: vi.fn((_error: unknown, fallback: string) => fallback),
}));

const apiMock = vi.mocked(api);
const apiImageDataUrlMock = vi.mocked(apiImageDataUrl);

describe("results view feature images", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    apiImageDataUrlMock.mockImplementation(
      async (path: string) => `data:image/jpeg;base64,${btoa(path)}`,
    );
    apiMock.mockImplementation(async (path: string) => {
      if (path.startsWith("/api/v1/results?")) {
        return {
          items: [
            {
              result_id: "run-result",
              run_id: "run-result",
              domain: "portrait",
              pipeline: {
                pipeline_id: "portrait.person-detection",
                version: "0.1.0",
              },
              status: "completed",
              asset_id: "asset-result",
              media_kind: "image",
              resource_name: "sample.png",
              unit_count: 1,
              object_count: 1,
              person_count: 1,
              face_count: 0,
              ocr_block_count: 0,
              text_length: 0,
              warning_count: 0,
              index_status: "ready",
              created_at: 1,
            },
          ],
          offset: 0,
          limit: 50,
          total: 1,
        };
      }
      if (path === "/api/v1/domains") {
        return [
          {
            domain_id: "portrait",
            display_name: "人像",
            schema_version: "1.0",
            capabilities: [],
            console_route: "/parse/portrait",
          },
        ];
      }
      if (path.startsWith("/api/v1/runs/run-result/result?")) {
        return {
          result: {
            schema_version: "1.0",
            run_id: "run-result",
            domain: "portrait",
            pipeline: {
              pipeline_id: "portrait.person-detection",
              version: "0.1.0",
            },
            units: [
              {
                unit_id: "frame_0",
                unit_type: "frame",
                index: 0,
                pts_ms: 0,
                width: 200,
                height: 100,
                frame_artifact_id: "frame_0_image",
                objects: [
                  {
                    object_id: "person_0",
                    object_type: "person",
                    score: 0.96,
                    bbox: { x: 20, y: 10, width: 40, height: 50 },
                    attributes: {},
                    crop_artifact_id: "crop_0",
                  },
                ],
              },
            ],
            domain_payload: {
              domain: "portrait",
              persons: [],
              faces: [],
              tracks: [],
              capabilities: ["person_detection"],
            },
            relations: [],
            artifacts: [],
            models: [],
            timings: {},
            media_metadata: { sampled_units: 1 },
            warnings: [],
            provenance: {},
            created_at: 1,
          },
          unit_offset: 0,
          unit_limit: 20,
          unit_total: 1,
        };
      }
      throw new Error(`unexpected API path: ${path}`);
    });
  });

  it("shows each crop and opens its full frame with a highlight", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div />" } }],
    });
    await router.push("/?run=run-result");
    await router.isReady();
    const wrapper = mount(ResultsView, {

      attachTo: document.body,
      global: { plugins: [router] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("特征图片");
    await vi.waitFor(() =>
      expect(wrapper.findAll(".crop-card")).toHaveLength(1),
    );
    expect(apiImageDataUrlMock).toHaveBeenCalledWith(
      "/api/v1/runs/run-result/artifacts/crop_0",
    );

    await wrapper.get(".crop-card").trigger("click");
    await vi.waitFor(() =>
      expect(wrapper.find(".lightbox").exists()).toBe(true),
    );
    expect(apiImageDataUrlMock).toHaveBeenCalledWith(
      "/api/v1/runs/run-result/artifacts/frame_0_image",
    );
    expect(wrapper.get(".lightbox-highlight").attributes("style")).toContain(
      "left: 10%",
    );
    wrapper.unmount();
  });

  it("does not automatically open detail drawer on plain page load", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div />" } }],
    });
    await router.push("/");
    await router.isReady();
    const wrapper = mount(ResultsView, {
      attachTo: document.body,
      global: { plugins: [router] },
    });
    await flushPromises();

    expect(wrapper.text()).not.toContain("特征图片");
    expect(wrapper.find(".drawer-backdrop").exists()).toBe(false);
    wrapper.unmount();
  });
});

