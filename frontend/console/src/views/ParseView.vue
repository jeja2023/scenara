<script setup lang="ts">
import { AlertTriangle, ChevronDown, ChevronUp, Clock3, Download, FileImage, FileText, Pause, Play, Radio, RefreshCw, Square, Video } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api, apiStream, idempotencyKey, streamJsonEvents, userFacingError } from "../api";
import { labelDomain, labelPipeline, labelRunError, labelRunStatus, labelSampleStrategy, labelTerminationReason, labelWarning } from "../labels";
import type { Domain, MediaAsset, MediaSource, ResultEnvelope, ResultPage, Run } from "../types";

type MediaMode = "image" | "video" | "document" | "stream";
type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";

const STRATEGY_LABELS: Record<SampleStrategy, string> = {
  interval: "固定间隔",
  keyframe: "关键帧",
  scene_change: "场景切换",
  uniform: "均匀分布",
};

const props = defineProps<{ domain: Domain }>();
const mode = ref<MediaMode>("image");
const file = ref<File | null>(null);
const mediaUrl = ref("");
const videoElement = ref<HTMLVideoElement | null>(null);
const overlayCanvas = ref<HTMLCanvasElement | null>(null);
const sources = ref<MediaSource[]>([]);
const sourceId = ref("");
const sourceName = ref("");
const sourceUrl = ref("");

// Sampling params
const sampleIntervalMs = ref(1000);
const maxUnits = ref(32);
const sampleStrategy = ref<SampleStrategy>("interval");
const sampleStartMs = ref(0);
const sampleEndMs = ref<number | null>(null);
const sceneChangeThreshold = ref(0.35);
const frameMaxEdge = ref<number | null>(null);
const pageScale = ref(1.5);
const maxReconnectAttempts = ref(3);
const connectTimeoutMs = ref(10_000);
const readTimeoutMs = ref(10_000);
const showAdvanced = ref(false);

const loading = ref(false);
const transitioning = ref(false);
const loadingSources = ref(false);
const error = ref("");
const run = ref<Run | null>(null);
const result = ref<ResultEnvelope | null>(null);
const selectedUnitIndex = ref(0);
const showWarnings = ref(false);
let pollGeneration = 0;
let sseAbort: AbortController | null = null;

const pipeline = computed(() => {
  if (props.domain === "portrait") return "portrait.person-detection";
  return "ocr.document";
});

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const selectedSource = computed(() => sources.value.find((item) => item.source_id === sourceId.value) ?? null);
const samplingValid = computed(() => {
  const endMs = optionalNumber(sampleEndMs.value);
  const maxEdge = optionalNumber(frameMaxEdge.value);
  if (!Number.isInteger(maxUnits.value) || maxUnits.value < 1 || maxUnits.value > (mode.value === "document" ? 1_000 : 10_000)) return false;
  if (mode.value === "document") return pageScale.value >= 0.5 && pageScale.value <= 4;
  if (!Number.isInteger(sampleIntervalMs.value) || sampleIntervalMs.value < 1 || sampleIntervalMs.value > 3_600_000) return false;
  if (!Number.isInteger(sampleStartMs.value) || sampleStartMs.value < 0) return false;
  if (endMs != null && (!Number.isInteger(endMs) || endMs <= sampleStartMs.value)) return false;
  if (sampleStrategy.value === "scene_change" && (sceneChangeThreshold.value < 0.01 || sceneChangeThreshold.value > 1)) return false;
  if (maxEdge != null && (!Number.isInteger(maxEdge) || maxEdge < 64 || maxEdge > 8_192)) return false;
  if (mode.value !== "stream") return true;
  return Number.isInteger(maxReconnectAttempts.value) && maxReconnectAttempts.value >= 0 && maxReconnectAttempts.value <= 20
    && Number.isInteger(connectTimeoutMs.value) && connectTimeoutMs.value >= 100 && connectTimeoutMs.value <= 120_000
    && Number.isInteger(readTimeoutMs.value) && readTimeoutMs.value >= 100 && readTimeoutMs.value <= 120_000;
});
const inputReady = computed(() => {
  const hasInput = mode.value === "stream"
    ? !!sourceId.value || (!!sourceName.value && !!sourceUrl.value)
    : !!file.value;
  return hasInput && (mode.value === "image" || samplingValid.value);
});
const persons = computed(() => result.value?.domain_payload.domain === "portrait" ? result.value.domain_payload.persons : []);
const ocrBlocks = computed(() => result.value?.domain_payload.domain === "ocr" ? result.value.domain_payload.blocks : []);
const ocrText = computed(() => result.value?.domain_payload.domain === "ocr" ? result.value.domain_payload.text : "");
const selectedUnit = computed(() => result.value?.units[selectedUnitIndex.value] ?? result.value?.units[0]);
const selectedObjects = computed(() => selectedUnit.value?.objects ?? []);
const mediaMetadata = computed(() => result.value?.media_metadata ?? null);
const isTerminal = computed(() => !!run.value && ["completed", "failed", "cancelled"].includes(run.value.status));
const progressPercent = computed(() => Math.round((run.value?.progress ?? 0) * 100));
const warnings = computed(() => result.value?.warnings ?? []);
const totalObjects = computed(() => result.value?.units.reduce((s, u) => s + u.objects.length, 0) ?? 0);
const hasResult = computed(() => !!result.value);

function clearMediaUrl(): void {
  if (mediaUrl.value) URL.revokeObjectURL(mediaUrl.value);
  mediaUrl.value = "";
}

function resetResult(): void {
  pollGeneration += 1;
  if (sseAbort) { sseAbort.abort(); sseAbort = null; }
  run.value = null;
  result.value = null;
  selectedUnitIndex.value = 0;
  error.value = "";
  clearOverlay();
}

function clearOverlay(): void {
  const canvas = overlayCanvas.value;
  if (canvas) {
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

function selectMode(value: MediaMode): void {
  mode.value = value;
  file.value = null;
  showAdvanced.value = false;
  clearMediaUrl();
  resetResult();
  if (value === "stream") void refreshSources();
}

function selectFile(event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
  file.value = selected;
  clearMediaUrl();
  mediaUrl.value = selected ? URL.createObjectURL(selected) : "";
  resetResult();
}

async function refreshSources(): Promise<void> {
  loadingSources.value = true;
  try {
    const page = await api<{ items: MediaSource[] }>("/api/v1/media/sources?limit=200");
    sources.value = page.items;
  } catch (caught) {
    error.value = userFacingError(caught, "视频流源加载失败，请稍后重试");
  } finally {
    loadingSources.value = false;
  }
}

async function ensureSource(): Promise<string> {
  if (sourceId.value) return sourceId.value;
  const source = await api<MediaSource>("/api/v1/media/sources", {
    method: "POST",
    body: JSON.stringify({ name: sourceName.value, url: sourceUrl.value }),
  });
  sources.value = [source, ...sources.value];
  sourceId.value = source.source_id;
  return source.source_id;
}

async function loadResult(runId: string): Promise<void> {
  const pageSize = 1000;
  const first = await api<ResultPage>(`/api/v1/runs/${encodeURIComponent(runId)}/result?unit_limit=${pageSize}`);
  const units = [...first.result.units];
  while (units.length < first.unit_total) {
    const page = await api<ResultPage>(
      `/api/v1/runs/${encodeURIComponent(runId)}/result?unit_offset=${units.length}&unit_limit=${pageSize}`,
    );
    if (!page.result.units.length) break;
    units.push(...page.result.units);
  }
  result.value = { ...first.result, units };
  drawOverlay();
}

function subscribeEvents(runId: string): void {
  if (sseAbort) sseAbort.abort();
  const controller = new AbortController();
  sseAbort = controller;
  void (async () => {
    try {
      const response = await apiStream(`/api/v1/runs/${encodeURIComponent(runId)}/events`, controller.signal);
      for await (const event of streamJsonEvents<{
        status?: Run["status"];
        payload?: { progress?: number };
      }>(response)) {
        if (run.value && event.status && ["completed", "failed", "cancelled"].includes(event.status)) {
          run.value = await api<Run>("/api/v1/runs/" + encodeURIComponent(runId));
        } else if (run.value) {
          run.value = {
            ...run.value,
            status: event.status ?? run.value.status,
            progress: event.payload?.progress ?? run.value.progress,
          };
        }
      }
    } catch {
      // 事件流断开时回退到轮询，不向用户报错
    }
  })();
}

function followRun(initial: Run): void {
  void pollRun(initial).catch((caught) => {
    error.value = userFacingError(caught, "运行状态跟踪失败，请稍后重试");
  });
}

async function pollRun(initial: Run): Promise<void> {
  const generation = ++pollGeneration;
  run.value = initial;
  subscribeEvents(initial.run_id);
  while (generation === pollGeneration && !["completed", "failed", "cancelled"].includes(run.value.status)) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    if (generation !== pollGeneration) return;
    run.value = await api<Run>("/api/v1/runs/" + encodeURIComponent(initial.run_id));
  }
  if (sseAbort) { sseAbort.abort(); sseAbort = null; }
  if (generation !== pollGeneration || run.value.status !== "completed") return;
  await loadResult(initial.run_id);
}

function samplingParameters(): Record<string, unknown> {
  const endMs = optionalNumber(sampleEndMs.value);
  const maxEdge = optionalNumber(frameMaxEdge.value);
  const params: Record<string, unknown> = {
    sample_interval_ms: sampleIntervalMs.value,
    max_units: maxUnits.value,
    sample_strategy: sampleStrategy.value,
    sample_start_ms: sampleStartMs.value,
    scene_change_threshold: sceneChangeThreshold.value,
  };
  if (endMs != null && endMs > sampleStartMs.value) params.sample_end_ms = endMs;
  if (maxEdge != null) params.frame_max_edge = maxEdge;
  if (mode.value === "stream") {
    params.max_reconnect_attempts = maxReconnectAttempts.value;
    params.connect_timeout_ms = connectTimeoutMs.value;
    params.read_timeout_ms = readTimeoutMs.value;
  }
  return params;
}

async function execute(): Promise<void> {
  if (!inputReady.value) return;
  resetResult();
  loading.value = true;
  try {
    if (mode.value === "image") {
      const form = new FormData();
      form.append("file", file.value as File);
      form.append("domain", props.domain);
      form.append("pipeline_id", pipeline.value);
      const parsed = await api<{ asset: MediaAsset; run: Run; result: ResultEnvelope | null }>("/api/v1/parse/image", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey(props.domain + "_image") },
        body: form,
      });
      run.value = parsed.run;
      result.value = parsed.result;
      if (parsed.result) drawOverlay();
      else await pollRun(parsed.run);
    } else if (mode.value === "video" || mode.value === "document") {
      const form = new FormData();
      form.append("file", file.value as File);
      form.append("domain", props.domain);
      form.append("pipeline_id", pipeline.value);
      form.append("max_units", String(maxUnits.value));
      if (mode.value === "video") {
        const endMs = optionalNumber(sampleEndMs.value);
        const maxEdge = optionalNumber(frameMaxEdge.value);
        form.append("sample_interval_ms", String(sampleIntervalMs.value));
        form.append("sample_strategy", sampleStrategy.value);
        form.append("sample_start_ms", String(sampleStartMs.value));
        form.append("scene_change_threshold", String(sceneChangeThreshold.value));
        if (endMs != null && endMs > sampleStartMs.value) {
          form.append("sample_end_ms", String(endMs));
        }
        if (maxEdge != null) form.append("frame_max_edge", String(maxEdge));
      } else {
        form.append("page_scale", String(pageScale.value));
      }
      const endpoint = mode.value === "document" ? "/api/v1/parse/document" : "/api/v1/parse/video";
      const parsed = await api<{ asset: MediaAsset; run: Run; result: ResultEnvelope | null }>(endpoint, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey(props.domain + "_" + mode.value) },
        body: form,
      });
      await pollRun(parsed.run);
    } else {
      const selectedId = await ensureSource();
      const created = await api<Run>("/api/v1/parse/stream", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey(props.domain + "_stream") },
        body: JSON.stringify({
          source_id: selectedId,
          domain: props.domain,
          pipeline: { pipeline_id: pipeline.value },
          parameters: samplingParameters(),
        }),
      });
      await pollRun(created);
    }
    if (run.value && ["failed", "cancelled"].includes(run.value.status)) {
      error.value = run.value.termination_reason
        ? labelTerminationReason(run.value.termination_reason)
        : run.value.error_code
          ? labelRunError(run.value.error_code)
          : labelRunStatus(run.value.status);
    }
  } catch (caught) {
    error.value = userFacingError(caught, "解析失败，请检查输入和模型状态后重试");
  } finally {
    loading.value = false;
  }
}

async function transitionRun(action: "pause" | "resume" | "cancel"): Promise<void> {
  if (!run.value || transitioning.value || (action === "cancel" && isTerminal.value)) return;
  const current = run.value;
  transitioning.value = true;
  try {
    pollGeneration += 1;
    if (sseAbort) { sseAbort.abort(); sseAbort = null; }
    const updated = await api<Run>(
      "/api/v1/runs/" + encodeURIComponent(current.run_id) + "/" + action,
      { method: "POST" },
    );
    run.value = updated;
    if (!["completed", "failed", "cancelled"].includes(updated.status)) followRun(updated);
  } catch (caught) {
    error.value = userFacingError(caught, "运行状态更新失败，请刷新后重试");
  } finally {
    transitioning.value = false;
  }
}

function selectUnit(index: number): void {
  selectedUnitIndex.value = index;
  const unit = result.value?.units[index];
  if (mode.value === "video" && videoElement.value && unit?.pts_ms != null) {
    videoElement.value.currentTime = unit.pts_ms / 1000;
  }
  drawOverlay();
}

const OVERLAY_COLORS: Record<string, string> = {
  person: "#ef6c52",
  face: "#2f9e7e",
  silhouette: "#c98a17",
  text: "#2f9e7e",
  title: "#ef6c52",
  paragraph: "#4b7bd4",
  image_region: "#8a63c9",
  table_region: "#c98a17",
};

function drawOverlay(): void {
  const canvas = overlayCanvas.value;
  const unit = selectedUnit.value;
  if (!canvas || !unit) { clearOverlay(); return; }
  canvas.width = unit.width;
  canvas.height = unit.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const stroke = Math.max(1.5, Math.min(unit.width, unit.height) / 320);
  ctx.lineWidth = stroke;
  ctx.font = `${Math.max(11, Math.min(unit.width, unit.height) / 42)}px system-ui, sans-serif`;
  ctx.textBaseline = "bottom";
  for (const item of unit.objects) {
    const color = OVERLAY_COLORS[item.object_type] ?? "#4b7bd4";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    if (item.polygon?.length && item.polygon.length >= 3) {
      ctx.beginPath();
      item.polygon.forEach((point, index) => {
        if (index === 0) ctx.moveTo(point.x, point.y);
        else ctx.lineTo(point.x, point.y);
      });
      ctx.closePath();
      ctx.stroke();
    }
    if (item.bbox) {
      ctx.strokeRect(item.bbox.x, item.bbox.y, item.bbox.width, item.bbox.height);
      if (item.score != null) {
        const text = item.score.toFixed(2);
        const width = ctx.measureText(text).width + 6;
        const height = Math.max(14, stroke * 9);
        ctx.globalAlpha = 0.85;
        ctx.fillRect(item.bbox.x, Math.max(height, item.bbox.y) - height, width, height);
        ctx.globalAlpha = 1;
        ctx.fillStyle = "#ffffff";
        ctx.fillText(text, item.bbox.x + 3, Math.max(height, item.bbox.y) - 2);
        ctx.fillStyle = color;
      }
    }
  }
}

function exportResult(format: "json" | "csv"): void {
  const current = result.value;
  if (!current) return;
  let blob: Blob;
  let extension: string;
  if (format === "json") {
    blob = new Blob([JSON.stringify(current, null, 2)], { type: "application/json" });
    extension = "json";
  } else {
    const header = "单元标识,单元类型,索引,时间点毫秒,页码,宽,高,对象标识,对象类型,置信度,边框x,边框y,边框宽,边框高";
    const rows: string[] = [header];
    for (const unit of current.units) {
      if (!unit.objects.length) {
        rows.push([unit.unit_id, unit.unit_type, unit.index, unit.pts_ms ?? "", unit.page_number ?? "", unit.width, unit.height, "", "", "", "", "", "", ""].join(","));
        continue;
      }
      for (const item of unit.objects) {
        rows.push([
          unit.unit_id, unit.unit_type, unit.index, unit.pts_ms ?? "", unit.page_number ?? "", unit.width, unit.height,
          item.object_id, item.object_type, item.score?.toFixed(4) ?? "",
          item.bbox?.x.toFixed(2) ?? "", item.bbox?.y.toFixed(2) ?? "", item.bbox?.width.toFixed(2) ?? "", item.bbox?.height.toFixed(2) ?? "",
        ].join(","));
      }
    }
    blob = new Blob(["﻿" + rows.join("\n")], { type: "text/csv;charset=utf-8" });
    extension = "csv";
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `scenara-${current.run_id}.${extension}`;
  link.click();
  URL.revokeObjectURL(url);
}

function formatTime(milliseconds?: number | null): string {
  if (milliseconds == null) return "-";
  const seconds = milliseconds / 1000;
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function formatDuration(milliseconds?: number | null): string {
  return milliseconds == null ? "未知" : formatTime(milliseconds);
}

function labelTimestampSource(value: string): string {
  return {
    decoder_pts: "解码器时间戳",
    position_msec: "媒体位置时间戳",
    monotonic_clock: "单调作业时钟",
  }[value] ?? "未知";
}

function formatBox(item: { x: number; y: number; width: number; height: number } | null | undefined): string {
  if (!item) return "-";
  return [item.x, item.y, item.width, item.height].map((value) => value.toFixed(1)).join(", ");
}

watch(() => props.domain, resetResult);
watch(selectedUnitIndex, drawOverlay);
onMounted(refreshSources);
onBeforeUnmount(() => {
  pollGeneration += 1;
  if (sseAbort) { sseAbort.abort(); sseAbort = null; }
  clearMediaUrl();
});
</script>

<template>
  <section class="page parse-workbench">
    <div class="page-header">
      <div><h1>{{ labelDomain(domain) }}解析</h1><p>{{ labelPipeline(pipeline) }} · {{ run?.pipeline?.version ? `版本 ${run.pipeline.version}` : "当前激活版本" }}</p></div>
      <div class="toolbar">
        <button v-if="hasResult" class="button secondary" title="导出结构化结果" @click="exportResult('json')"><Download :size="15" />导出 JSON</button>
        <button v-if="hasResult" class="button secondary" title="导出对象明细表" @click="exportResult('csv')"><Download :size="15" />导出 CSV</button>
        <button v-if="run?.status === 'running'" class="button secondary" :disabled="transitioning" @click="transitionRun('pause')"><Pause :size="15" />暂停</button>
        <button v-if="run?.status === 'paused'" class="button secondary" :disabled="transitioning" @click="transitionRun('resume')"><Play :size="15" />恢复</button>
        <button v-if="run && !isTerminal" class="button danger" :disabled="transitioning" @click="transitionRun('cancel')"><Square :size="15" />取消运行</button>
        <button class="button primary" :disabled="!inputReady || loading" @click="execute"><Play :size="16" />{{ loading ? "运行中" : "开始解析" }}</button>
      </div>
    </div>

    <div class="segmented media-modes" role="tablist" aria-label="媒体类型">
      <button :class="{ active: mode === 'image' }" role="tab" :aria-selected="mode === 'image'" @click="selectMode('image')"><FileImage :size="16" />图片</button>
      <button :class="{ active: mode === 'video' }" role="tab" :aria-selected="mode === 'video'" @click="selectMode('video')"><Video :size="16" />视频文件</button>
      <button :class="{ active: mode === 'document' }" role="tab" :aria-selected="mode === 'document'" @click="selectMode('document')"><FileText :size="16" />PDF 文档</button>
      <button :class="{ active: mode === 'stream' }" role="tab" :aria-selected="mode === 'stream'" @click="selectMode('stream')"><Radio :size="16" />实时流</button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel input-panel">
      <div class="panel-header">
        <h2>输入与采样</h2>
        <span class="badge">{{ mode === "image" ? "单帧" : mode === "document" ? `${maxUnits} 页上限` : `${maxUnits} 个单元上限` }}</span>
      </div>
      <div class="panel-body input-layout">
        <div class="media-stage">
          <img v-if="mode === 'image' && mediaUrl" :src="mediaUrl" alt="待解析图片" />
          <video v-else-if="mode === 'video' && mediaUrl" ref="videoElement" :src="mediaUrl" controls preload="metadata" />
          <div v-else-if="mode === 'document' && file" class="stream-stage">
            <FileText :size="28" />
            <strong>{{ file.name }}</strong>
            <span>{{ (file.size / 1024 / 1024).toFixed(2) }} MiB · 解析后按页浏览结果</span>
          </div>
          <div v-else-if="mode === 'stream'" class="stream-stage">
            <Radio :size="28" />
            <strong>{{ selectedSource?.name || sourceName || "未选择视频流" }}</strong>
            <span>{{ selectedSource?.masked_url || sourceUrl || "登记或选择一个视频流源" }}</span>
          </div>
          <div v-else class="empty">等待{{ mode === "image" ? "图片" : mode === "document" ? "PDF 文档" : "视频文件" }}</div>
          <canvas v-show="mediaUrl && selectedObjects.length" ref="overlayCanvas" class="overlay" aria-hidden="true" />
        </div>

        <div class="input-controls">
          <label v-if="mode !== 'stream'" class="file-picker">
            <span>{{ mode === "image" ? "图片文件" : mode === "document" ? "PDF 文档" : "视频文件" }}</span>
            <input
              type="file"
              :accept="mode === 'image' ? 'image/*' : mode === 'document' ? 'application/pdf,.pdf' : 'video/*,.mkv,.avi,.mov,.mp4,.webm'"
              @change="selectFile"
            />
            <small>{{ file?.name || "尚未选择文件" }}</small>
          </label>

          <template v-else>
            <label><span>已登记视频流</span><select v-model="sourceId"><option value="">登记新视频流</option><option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.name }} · {{ source.masked_url }}</option></select></label>
            <button class="icon-button source-refresh" :disabled="loadingSources" title="刷新视频流" aria-label="刷新视频流" @click="refreshSources"><RefreshCw :size="16" :class="{ spin: loadingSources }" /></button>
            <template v-if="!sourceId">
              <label><span>视频流名称</span><input v-model.trim="sourceName" maxlength="256" placeholder="例如：东门摄像头" /></label>
              <label><span>视频流地址</span><input v-model.trim="sourceUrl" maxlength="4096" placeholder="rtsp://host/path" /></label>
            </template>
          </template>

          <div v-if="mode === 'document'" class="parameter-grid">
            <label><span>最大页数</span><input v-model.number="maxUnits" type="number" min="1" max="1000" /></label>
            <label><span>渲染倍率</span><input v-model.number="pageScale" type="number" min="0.5" max="4" step="0.5" /></label>
          </div>

          <template v-else-if="mode !== 'image'">
            <label><span>采样策略</span>
              <select v-model="sampleStrategy">
                <option v-for="(text, value) in STRATEGY_LABELS" :key="value" :value="value">{{ text }}</option>
              </select>
            </label>
            <div class="parameter-grid">
              <label><span>采样间隔（毫秒）</span><input v-model.number="sampleIntervalMs" type="number" min="1" max="3600000" step="100" :disabled="sampleStrategy !== 'interval'" /></label>
              <label><span>最大分析单元</span><input v-model.number="maxUnits" type="number" min="1" max="10000" /></label>
            </div>
            <button class="button secondary advanced-toggle" @click="showAdvanced = !showAdvanced">
              <component :is="showAdvanced ? ChevronUp : ChevronDown" :size="15" />{{ showAdvanced ? "收起高级参数" : "展开高级参数" }}
            </button>
            <div v-if="showAdvanced" class="parameter-grid">
              <label><span>{{ mode === "stream" ? "开始后跳过（毫秒）" : "起始时间（毫秒）" }}</span><input v-model.number="sampleStartMs" type="number" min="0" step="1000" /></label>
              <label><span>{{ mode === "stream" ? "最大分析时长（毫秒）" : "结束时间（毫秒）" }}</span><input v-model.number="sampleEndMs" type="number" min="0" step="1000" placeholder="不限" /></label>
              <label v-if="sampleStrategy === 'scene_change'"><span>场景切换阈值</span><input v-model.number="sceneChangeThreshold" type="number" min="0.01" max="1" step="0.05" /></label>
              <label><span>帧最大边长（像素）</span><input v-model.number="frameMaxEdge" type="number" min="64" max="8192" step="64" placeholder="原始尺寸" /></label>
              <template v-if="mode === 'stream'">
                <label><span>最大重连次数</span><input v-model.number="maxReconnectAttempts" type="number" min="0" max="20" /></label>
                <label><span>连接超时（毫秒）</span><input v-model.number="connectTimeoutMs" type="number" min="100" max="120000" step="100" /></label>
                <label><span>读取超时（毫秒）</span><input v-model.number="readTimeoutMs" type="number" min="100" max="120000" step="100" /></label>
              </template>
            </div>
          </template>
        </div>
      </div>
    </section>

    <section v-if="run" class="run-strip" aria-live="polite">
      <div><span class="badge" :class="run.status">{{ labelRunStatus(run.status) }}</span><strong class="mono">{{ run.run_id }}</strong></div>
      <div class="progress-track" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: `${progressPercent}%` }" /></div>
      <span>{{ progressPercent }}%</span>
    </section>

    <section v-if="warnings.length" class="panel warning-panel">
      <div class="panel-header">
        <h2><AlertTriangle :size="16" />解析告警</h2>
        <button class="button secondary" @click="showWarnings = !showWarnings">{{ showWarnings ? "收起" : `查看 ${warnings.length} 条` }}</button>
      </div>
      <ul v-if="showWarnings" class="panel-body warning-list">
        <li v-for="item in warnings" :key="item">{{ labelWarning(item) }}</li>
      </ul>
    </section>

    <div class="results-layout">
      <section class="panel result-summary">
        <div class="panel-header"><h2>解析结果</h2><Clock3 v-if="loading" :size="16" class="spin" /></div>
        <div v-if="result" class="panel-body">
          <dl class="result-counters">
            <div><dt>分析单元</dt><dd>{{ result.units.length }}</dd></div>
            <div><dt>识别对象</dt><dd>{{ totalObjects || persons.length || ocrBlocks.length }}</dd></div>
            <div><dt>模型</dt><dd>{{ result.models.length }}</dd></div>
          </dl>
          <dl v-if="mediaMetadata" class="metadata-grid">
            <div><dt>画面尺寸</dt><dd>{{ mediaMetadata.width || selectedUnit?.width }} × {{ mediaMetadata.height || selectedUnit?.height }}</dd></div>
            <div><dt>时长</dt><dd>{{ formatDuration(mediaMetadata.duration_ms) }}</dd></div>
            <div><dt>帧率</dt><dd>{{ mediaMetadata.fps?.toFixed(2) || "未知" }}</dd></div>
            <div><dt>编码</dt><dd>{{ mediaMetadata.codec || mediaMetadata.format || "未知" }}</dd></div>
            <div v-if="mediaMetadata.sample_strategy"><dt>采样策略</dt><dd>{{ labelSampleStrategy(mediaMetadata.sample_strategy) }}</dd></div>
            <div v-if="mediaMetadata.frames_read != null"><dt>读取帧数</dt><dd>{{ mediaMetadata.frames_read }}</dd></div>
            <div v-if="mediaMetadata.reconnect_count != null"><dt>重连次数</dt><dd>{{ mediaMetadata.reconnect_count }}</dd></div>
            <div v-if="mediaMetadata.elapsed_ms != null"><dt>解码耗时</dt><dd>{{ (mediaMetadata.elapsed_ms / 1000).toFixed(2) }} 秒</dd></div>
            <div v-if="mediaMetadata.timestamp_source"><dt>时间戳来源</dt><dd>{{ labelTimestampSource(mediaMetadata.timestamp_source) }}</dd></div>
          </dl>
          <textarea v-if="domain === 'ocr'" readonly :value="ocrText" aria-label="OCR 文本结果" />
          <div v-if="selectedObjects.length" class="table-scroll"><table class="data-table"><thead><tr><th>对象</th><th>类型</th><th>置信度</th><th>边框 x, y, w, h</th></tr></thead><tbody><tr v-for="item in selectedObjects" :key="item.object_id"><td class="mono">{{ item.object_id }}</td><td>{{ item.object_type }}</td><td>{{ item.score?.toFixed(3) ?? "-" }}</td><td class="mono">{{ formatBox(item.bbox) }}</td></tr></tbody></table></div>
          <details><summary>原始结果（JSON）</summary><pre>{{ JSON.stringify(result, null, 2) }}</pre></details>
        </div>
        <div v-else class="empty result-empty">{{ loading ? "正在解析媒体" : "暂无结果" }}</div>
      </section>

      <section class="panel timeline-panel">
        <div class="panel-header"><h2>{{ mode === "image" ? "媒体单元" : mode === "document" ? "页面" : "时间轴" }}</h2><span class="badge">{{ result?.units.length || 0 }}</span></div>
        <div v-if="result?.units.length" class="unit-list">
          <button v-for="(unit, index) in result.units" :key="unit.unit_id" :class="{ selected: selectedUnitIndex === index }" @click="selectUnit(index)">
            <span class="unit-index">{{ index + 1 }}</span>
            <span><strong>{{ unit.unit_type === "page" ? `第 ${unit.page_number} 页` : formatTime(unit.pts_ms) }}</strong><small>{{ unit.width }} × {{ unit.height }} · {{ unit.objects.length }} 个对象</small></span>
          </button>
        </div>
        <div v-else class="empty">等待媒体单元</div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.parse-workbench { gap: 14px; }
.media-modes { width: fit-content; margin-bottom: 14px; }
.media-modes button { display: inline-flex; align-items: center; gap: 7px; }
.input-layout { display: grid; grid-template-columns: minmax(360px, 1.25fr) minmax(280px, .75fr); gap: 16px; }
.media-stage { position: relative; width: 100%; min-width: 0; aspect-ratio: 16 / 9; display: grid; place-items: center; overflow: hidden; background: #101816; color: #dbe6e2; border-radius: 4px; }
.media-stage img, .media-stage video, .overlay { position: absolute; width: 100%; height: 100%; object-fit: contain; }
.overlay { pointer-events: none; }
.stream-stage { display: grid; justify-items: center; gap: 8px; max-width: 80%; text-align: center; }
.stream-stage span { color: #9fb1aa; overflow-wrap: anywhere; }
.input-controls { position: relative; display: grid; align-content: start; gap: 14px; }
.input-controls label, .file-picker { display: grid; gap: 6px; }
.input-controls label > span { font-size: 12px; font-weight: 700; color: var(--muted); }
.file-picker small { overflow-wrap: anywhere; }
.source-refresh { position: absolute; right: 7px; top: 25px; }
.parameter-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.advanced-toggle { justify-self: start; display: inline-flex; align-items: center; gap: 6px; }
.run-strip { display: grid; grid-template-columns: minmax(260px, auto) minmax(160px, 1fr) auto; align-items: center; gap: 12px; margin-top: 14px; padding: 10px 12px; border: 1px solid var(--line); background: var(--surface); }
.run-strip > div:first-child { display: flex; align-items: center; gap: 9px; min-width: 0; }
.progress-track { height: 7px; overflow: hidden; background: #dfe6e3; border-radius: 3px; }
.progress-track span { display: block; height: 100%; background: var(--teal); transition: width .2s ease; }
.warning-panel { margin-top: 14px; }
.warning-panel h2 { display: inline-flex; align-items: center; gap: 7px; color: #7c4b08; }
.warning-list { display: grid; gap: 7px; margin: 0; padding-left: 20px; }
.warning-list li { color: #7c4b08; font-size: 12px; overflow-wrap: anywhere; }
.results-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 340px); gap: 14px; margin-top: 14px; }
.result-counters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 0 0 14px; border-block: 1px solid var(--line); }
.result-counters div { padding: 10px 12px; border-right: 1px solid var(--line); }
.result-counters div:last-child { border-right: 0; }
.result-counters dt { color: var(--muted); font-size: 11px; }
.result-counters dd { margin: 4px 0 0; font-size: 21px; font-weight: 700; }
.metadata-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; margin: 0 0 14px; background: var(--line); border: 1px solid var(--line); }
.metadata-grid div { padding: 9px 10px; background: var(--surface); }
.metadata-grid dt { color: var(--muted); font-size: 11px; }
.metadata-grid dd { margin: 3px 0 0; font-weight: 700; overflow-wrap: anywhere; }
.result-summary textarea { width: 100%; min-height: 160px; margin-bottom: 12px; }
.result-empty { min-height: 260px; }
.unit-list { display: grid; max-height: 620px; overflow: auto; }
.unit-list button { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 9px; align-items: center; width: 100%; padding: 9px 10px; border: 0; border-bottom: 1px solid var(--line); background: var(--surface); color: var(--text); text-align: left; cursor: pointer; }
.unit-list button:hover, .unit-list button.selected { background: #e7f1ee; }
.unit-list small { display: block; margin-top: 2px; color: var(--muted); }
.unit-index { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid var(--line); border-radius: 3px; font-size: 11px; }
pre { max-height: 320px; overflow: auto; padding: 12px; background: #101816; color: #dbe6e2; border-radius: 4px; font-size: 11px; }
.spin { animation: spin .9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) {
  .input-layout, .results-layout { grid-template-columns: 1fr; }
  .metadata-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .run-strip { grid-template-columns: 1fr auto; }
  .run-strip .progress-track { grid-column: 1 / -1; grid-row: 2; }
}
@media (max-width: 520px) {
  .media-modes { width: 100%; }
  .media-modes button { flex: 1; justify-content: center; min-width: 0; }
  .input-layout { display: block; }
  .input-controls { margin-top: 12px; }
  .parameter-grid { grid-template-columns: 1fr; }
  .result-counters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .result-counters div { padding-inline: 8px; }
}
</style>
