import assert from "node:assert/strict";
import test from "node:test";

import { ScenaraClient } from "../dist/index.js";

test("media shortcuts serialize the complete public parsing contract", async () => {
  const calls = [];
  const client = new ScenaraClient({
    transport: async (method, path, options = {}) => {
      calls.push({ method, path, options });
      return {};
    },
  });
  const file = new Blob(["media"], { type: "application/octet-stream" });

  await client.parseImage({
    file,
    filename: "frame.png",
    domain: "ocr",
    pipelineId: "ocr.document",
    pipelineVersion: "1.2.3",
    idempotencyKey: "image-key",
  });
  await client.parseVideo({
    file,
    filename: "clip.mp4",
    domain: "ocr",
    sampleIntervalMs: 400,
    maxUnits: 8,
    sampleStrategy: "scene_change",
    sampleStartMs: 250,
    sampleEndMs: 5_000,
    sceneChangeThreshold: 0.2,
    frameMaxEdge: 1_280,
    pageScale: 2,
    cameraId: "camera-a",
    recordingStartedAt: 1_700_000_000.25,
    waitMs: 1_000,
    idempotencyKey: "video-key",
  });
  await client.parseDocument({
    file,
    filename: "report.pdf",
    maxUnits: 10,
    pageScale: 2.5,
    idempotencyKey: "document-key",
  });
  await client.parseStream({
    sourceId: "source-1",
    sampleIntervalMs: 500,
    maxUnits: 12,
    sampleStrategy: "keyframe",
    sampleStartMs: 100,
    sampleEndMs: 6_000,
    sceneChangeThreshold: 0.4,
    frameMaxEdge: 720,
    maxReconnectAttempts: 5,
    connectTimeoutMs: 3_000,
    readTimeoutMs: 2_000,
    idempotencyKey: "stream-key",
  });

  const video = calls.find(({ path }) => path.endsWith("/parse/video"));
  assert.equal(video.options.idempotencyKey, "video-key");
  const videoFields = Object.fromEntries(video.options.body.entries());
  assert.ok(videoFields.file instanceof Blob);
  delete videoFields.file;
  assert.deepEqual(
    videoFields,
    {
      domain: "ocr",
      sample_interval_ms: "400",
      max_units: "8",
      sample_strategy: "scene_change",
      sample_start_ms: "250",
      sample_end_ms: "5000",
      scene_change_threshold: "0.2",
      frame_max_edge: "1280",
      page_scale: "2",
      camera_id: "camera-a",
      recording_started_at: "1700000000.25",
      wait_ms: "1000",
    },
  );

  const image = calls.find(({ path }) => path.endsWith("/parse/image"));
  assert.equal(image.options.idempotencyKey, "image-key");
  assert.deepEqual(
    Object.fromEntries([...image.options.body.entries()].filter(([name]) => name !== "file")),
    { domain: "ocr", pipeline_id: "ocr.document", pipeline_version: "1.2.3" },
  );

  const document = calls.find(({ path }) => path.endsWith("/parse/document"));
  assert.equal(document.options.idempotencyKey, "document-key");
  assert.equal(document.options.body.get("domain"), "ocr");
  assert.equal(document.options.body.get("max_units"), "10");
  assert.equal(document.options.body.get("page_scale"), "2.5");

  const stream = calls.find(({ path }) => path.endsWith("/parse/stream"));
  assert.equal(stream.options.idempotencyKey, "stream-key");
  assert.deepEqual(stream.options.body.pipeline, { pipeline_id: "portrait.person-detection" });
  assert.deepEqual(stream.options.body.parameters, {
    sample_interval_ms: 500,
    max_units: 12,
    sample_strategy: "keyframe",
    sample_start_ms: 100,
    sample_end_ms: 6_000,
    scene_change_threshold: 0.4,
    frame_max_edge: 720,
    max_reconnect_attempts: 5,
    connect_timeout_ms: 3_000,
    read_timeout_ms: 2_000,
  });
});

test("result APIs aggregate all pages and retain delta-page access", async () => {
  const calls = [];
  const total = 1201;
  const client = new ScenaraClient({
    transport: async (_method, path) => {
      const url = new URL(path, "https://scenara.example");
      const offset = Number(url.searchParams.get("unit_offset") ?? 0);
      const limit = Number(url.searchParams.get("unit_limit") ?? 100);
      calls.push(offset);
      return {
        result: {
          schema_version: "1.0",
          run_id: "run-large",
          domain: "ocr",
          pipeline: { pipeline_id: "ocr.document", version: "0.1.0" },
          asset_id: "asset-large",
          source_id: null,
          units: Array.from(
            { length: Math.max(0, Math.min(total, offset + limit) - offset) },
            (_, index) => ({ unit_id: `frame_${offset + index}` }),
          ),
          domain_payload: {},
          relations: [],
          artifacts: [],
          models: [],
          timings: {},
          media_metadata: {},
          warnings: [],
          provenance: {},
          created_at: 1,
        },
        unit_offset: offset,
        unit_limit: limit,
        unit_total: total,
      };
    },
  });

  const page = await client.getResultPage("run-large", 500, 2);
  assert.deepEqual(page.result.units.map((unit) => unit.unit_id), ["frame_500", "frame_501"]);
  const result = await client.getResult("run-large");
  assert.equal(result.units.length, total);
  assert.equal(result.units.at(-1).unit_id, "frame_1200");
  assert.deepEqual(calls, [500, 0, 1000]);
});
