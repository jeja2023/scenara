<script setup lang="ts">
import {
  Check,
  Clock,
  Columns2,
  Copy,
  Download,
  Eye,
  FileText,
  Film,
  Layers,
  Layout,
  Loader2,
  ScanFace,
  ShieldAlert,
  ShieldCheck,
  X,
} from "@lucide/vue";

import { computed, nextTick, ref, watch } from "vue";
import { api, apiImageDataUrl, userFacingError } from "../api";
import DataTable from "./DataTable.vue";
import FeatureCropGallery from "./FeatureCropGallery.vue";
import GenericDomainResult from "./GenericDomainResult.vue";
import {
  labelDomain,
  labelMediaKind,
  labelObjectType,
  labelRunStatus,
  labelSampleStrategy,
} from "../labels";
import type {
  MediaUnitResult,
  OcrComplianceReport,
  OcrDomainPayload,
  OcrSlideCard,
  ResultEnvelope,
  ResultPage,
  ResultSummary,
  Run,
  TableColumn,
} from "../types";

const props = withDefaults(
  defineProps<{
    open: boolean;
    runId?: string | null;
    summary?: ResultSummary | null;
  }>(),
  {
    runId: null,
    summary: null,
  },
);

const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "close"): void;
}>();

const detailDialog = ref<HTMLDialogElement | null>(null);
const detailLoading = ref(false);
const error = ref("");
const result = ref<ResultEnvelope | null>(null);
const selectedUnit = ref<MediaUnitResult | null>(null);
const unitTotal = ref(0);
const resolvedSummary = ref<ResultSummary | null>(null);

const currentSummary = computed(() => props.summary || resolvedSummary.value);

const selectedPayload = computed(() => result.value?.domain_payload ?? null);
const ocrText = computed(() =>
  selectedPayload.value?.domain === "ocr"
    ? String(selectedPayload.value.text ?? "")
    : "",
);

const activeOcrTab = ref<"layout" | "compliance" | "slides" | "raw">("layout");
const underlayMode = ref(false);
const underlayImageUrl = ref<string>("");
const underlayLoading = ref(false);
const underlayCache = new Map<string, string>();
const copiedText = ref(false);
const activeSlideIndex = ref(0);

function currentUnderlayArtifactId(): string | null {
  if (
    ocrSlides.value.length > 0 &&
    activeSlideIndex.value >= 0 &&
    activeSlideIndex.value < ocrSlides.value.length
  ) {
    const slide = ocrSlides.value[activeSlideIndex.value];
    if (slide?.frame_artifact_id) return slide.frame_artifact_id;
  }
  if (selectedUnit.value?.frame_artifact_id) {
    return selectedUnit.value.frame_artifact_id;
  }
  if (result.value?.units?.[0]?.frame_artifact_id) {
    return result.value.units[0].frame_artifact_id;
  }
  return null;
}

async function loadUnderlayImage(): Promise<void> {
  if (!result.value) return;
  const runId = result.value.run_id;
  const artifactId = currentUnderlayArtifactId();

  let targetPath = "";
  let cacheKey = "";
  if (artifactId) {
    targetPath = `/api/v1/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
    cacheKey = `artifact:${runId}:${artifactId}`;
  } else {
    const assetId = result.value.asset_id || currentSummary.value?.asset_id;
    if (assetId) {
      targetPath = `/api/v1/media/assets/${encodeURIComponent(assetId)}/preview`;
      cacheKey = `asset:${assetId}`;
    }
  }

  if (!targetPath) {
    underlayImageUrl.value = "";
    return;
  }

  const cached = underlayCache.get(cacheKey);
  if (cached) {
    underlayImageUrl.value = cached;
    return;
  }

  underlayLoading.value = true;
  try {
    const dataUrl = await apiImageDataUrl(targetPath);
    underlayCache.set(cacheKey, dataUrl);
    underlayImageUrl.value = dataUrl;
  } catch (err) {
    console.error("加载底图失败:", err);
    underlayImageUrl.value = "";
  } finally {
    underlayLoading.value = false;
  }
}

async function toggleUnderlayMode(): Promise<void> {
  underlayMode.value = !underlayMode.value;
  if (underlayMode.value) {
    await loadUnderlayImage();
  }
}

watch([selectedUnit, activeSlideIndex, result], () => {
  if (underlayMode.value) {
    void loadUnderlayImage();
  }
});

const ocrPayload = computed(() => {
  if (selectedPayload.value?.domain !== "ocr") return null;
  return selectedPayload.value as unknown as OcrDomainPayload;
});

const complianceReport = computed<OcrComplianceReport | null>(() => {
  return ocrPayload.value?.compliance_report ?? null;
});

const ocrSlides = computed<OcrSlideCard[]>(() => {
  return ocrPayload.value?.slides ?? [];
});

const currentHtmlLayout = computed<string>(() => {
  if (
    ocrSlides.value.length > 0 &&
    activeSlideIndex.value >= 0 &&
    activeSlideIndex.value < ocrSlides.value.length
  ) {
    const slide = ocrSlides.value[activeSlideIndex.value];
    if (slide?.html_layout) return slide.html_layout;
  }
  return ocrPayload.value?.html_layout ?? "";
});

async function copyRawOcrText(): Promise<void> {
  if (!ocrText.value) return;
  try {
    await navigator.clipboard.writeText(ocrText.value);
    copiedText.value = true;
    setTimeout(() => {
      copiedText.value = false;
    }, 2000);
  } catch {}
}

function exportHtmlLayout(): void {
  const content = currentHtmlLayout.value;
  if (!content) return;
  const fullHtml = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OCR 版面排版还原 - ${result.value?.run_id ?? "scenara"}</title>
  <style>
    body { margin: 0; padding: 24px; background: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .page-wrapper { width: 100%; max-width: 900px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; background: #fff; }
  </style>
</head>
<body>
  <div class="page-wrapper">
    ${content}
  </div>
</body>
</html>`;
  const blob = new Blob([fullHtml], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ocr_layout_${result.value?.run_id ?? "export"}.html`;
  a.click();
  URL.revokeObjectURL(url);
}
const objectCount = computed(
  () =>
    result.value?.units.reduce((sum, unit) => sum + unit.objects.length, 0) ??
    currentSummary.value?.object_count ??
    0,
);
const resultDescription = computed(() => {
  if (!currentSummary.value) return "选择一条结果查看原始内容和解析单元。";
  if (currentSummary.value.domain === "ocr") {
    return `${currentSummary.value.ocr_block_count ?? 0} 个文本块 · ${currentSummary.value.text_length ?? 0} 个字符`;
  }
  if (currentSummary.value.domain === "fashion") {
    return `服饰风格解析 · ${objectCount.value} 个识别目标`;
  }
  if (currentSummary.value.domain === "behavior") {
    return `行为动作识别 · ${objectCount.value} 个动作时序`;
  }
  return `${currentSummary.value.person_count ?? 0} 个人员 · ${currentSummary.value.face_count ?? 0} 张人脸`;
});

const mediaMetadata = computed(() => result.value?.media_metadata ?? null);
const hasMediaMetadataItems = computed(() => {
  const m = mediaMetadata.value;
  if (!m) return false;
  return Boolean(
    (m.width && m.height) ||
      m.duration_ms != null ||
      m.fps != null ||
      m.codec ||
      m.format ||
      m.sample_strategy ||
      m.frames_read != null ||
      m.reconnect_count != null ||
      m.elapsed_ms != null ||
      m.timestamp_source,
  );
});
const genericPayload = computed<Record<string, unknown> | null>(() => {
  const payload = result.value?.domain_payload;
  if (!payload || typeof payload !== "object") return null;
  if (["portrait", "ocr"].includes(String(payload.domain ?? ""))) return null;
  return payload as Record<string, unknown>;
});

function labelTimestampSource(value: string): string {
  return (
    {
      decoder_pts: "解码器时间戳",
      position_msec: "媒体位置时间戳",
      monotonic_clock: "单调作业时钟",
    }[value] ?? "未知"
  );
}

function formatDuration(milliseconds?: number | null): string {
  if (milliseconds == null) return "未知";
  const seconds = milliseconds / 1000;
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function formatUnitPosition(unit: MediaUnitResult): string {
  if (unit.pts_ms == null) return `单元 ${unit.index + 1}`;
  const seconds = Math.floor(unit.pts_ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

const objectColumns: TableColumn<{
  object_id: string;
  object_type: string;
  score?: number | null;
  bbox?: { x: number; y: number; width: number; height: number } | null;
}>[] = [
  { key: "object_id", label: "目标编号", class: "mono truncate" },
  { key: "object_type", label: "类别" },
  { key: "score", label: "置信度" },
  { key: "bbox", label: "坐标位置 (x, y, w, h)", class: "mono" },
];

function formatBox(
  item:
    | { x: number; y: number; width: number; height: number }
    | null
    | undefined,
): string {
  if (!item) return "-";
  return [item.x, item.y, item.width, item.height]
    .map((value) => value.toFixed(1))
    .join(", ");
}

function resultTitle(item: ResultSummary): string {
  return item.resource_name || item.asset_id || item.source_id || item.run_id;
}

function exportResult(format: "json" | "csv"): void {
  const current = result.value;
  if (!current) return;
  let blob: Blob;
  let extension: string;
  if (format === "json") {
    blob = new Blob([JSON.stringify(current, null, 2)], {
      type: "application/json",
    });
    extension = "json";
  } else {
    const header =
      "单元标识,单元类型,索引,时间点毫秒,页码,宽,高,对象标识,对象类型,置信度,边框x,边框y,边框宽,边框高";
    const rows: string[] = [header];
    for (const unit of current.units) {
      if (!unit.objects.length) {
        rows.push(
          [
            unit.unit_id,
            unit.unit_type,
            unit.index,
            unit.pts_ms ?? "",
            unit.page_number ?? "",
            unit.width,
            unit.height,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
          ].join(","),
        );
        continue;
      }
      for (const item of unit.objects) {
        rows.push(
          [
            unit.unit_id,
            unit.unit_type,
            unit.index,
            unit.pts_ms ?? "",
            unit.page_number ?? "",
            unit.width,
            unit.height,
            item.object_id,
            item.object_type,
            item.score?.toFixed(4) ?? "",
            item.bbox?.x.toFixed(2) ?? "",
            item.bbox?.y.toFixed(2) ?? "",
            item.bbox?.width.toFixed(2) ?? "",
            item.bbox?.height.toFixed(2) ?? "",
          ].join(","),
        );
      }
    }
    blob = new Blob(["\uFEFF" + rows.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    extension = "csv";
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `scenara-${current.run_id}.${extension}`;
  link.click();
  URL.revokeObjectURL(url);
}

async function loadDetail(runId: string): Promise<void> {
  detailLoading.value = true;
  error.value = "";
  result.value = null;
  selectedUnit.value = null;
  resolvedSummary.value = null;

  try {
    const [page, runInfo] = await Promise.all([
      api<ResultPage>(`/api/v1/runs/${runId}/result?unit_limit=1000`),
      props.summary
        ? Promise.resolve(null)
        : api<Run>(`/api/v1/runs/${runId}`).catch(() => null),
    ]);

    result.value = page.result;
    unitTotal.value = page.unit_total ?? page.result.units.length;
    selectedUnit.value = page.result.units[0] ?? null;

    if (!props.summary) {
      const currentRes = page.result;
      const persons = Array.isArray(currentRes.domain_payload?.persons)
        ? (currentRes.domain_payload.persons as unknown[]).length
        : 0;
      const faces = Array.isArray(currentRes.domain_payload?.faces)
        ? (currentRes.domain_payload.faces as unknown[]).length
        : 0;
      const ocrBlocks = Array.isArray(currentRes.domain_payload?.blocks)
        ? (currentRes.domain_payload.blocks as unknown[]).length
        : 0;
      const textLen =
        typeof currentRes.domain_payload?.text === "string"
          ? currentRes.domain_payload.text.length
          : 0;
      const totalObjs = currentRes.units.reduce((s, u) => s + u.objects.length, 0);

      resolvedSummary.value = {
        result_id: currentRes.run_id,
        run_id: currentRes.run_id,
        domain: currentRes.domain,
        pipeline: currentRes.pipeline,
        status: runInfo?.status ?? "completed",
        asset_id: runInfo?.asset_id ?? null,
        source_id: runInfo?.source_id ?? null,
        media_kind: runInfo?.source_id ? "stream" : "image",
        resource_name: runInfo?.asset_id || runInfo?.source_id || currentRes.run_id,
        unit_count: currentRes.units.length,
        object_count: totalObjs,
        person_count: persons,
        face_count: faces,
        ocr_block_count: ocrBlocks,
        text_length: textLen,
        warning_count: currentRes.warnings.length,
        index_status: "ready",
        created_at: currentRes.created_at,
      };
    }
  } catch (err) {
    error.value = userFacingError(err, "加载解析结果详情失败");
  } finally {
    detailLoading.value = false;
  }
}

function close(): void {
  if (detailDialog.value?.open) {
    if (typeof detailDialog.value.close === "function") {
      detailDialog.value.close();
    } else {
      detailDialog.value.removeAttribute("open");
    }
  }
  emit("update:open", false);
  emit("close");
}

function onDialogClosed(): void {
  emit("update:open", false);
  emit("close");
}

function handleBackdropClick(event: MouseEvent): void {
  if (event.target === detailDialog.value) {
    close();
  }
}

watch(
  () => [props.open, props.runId],
  async ([isOpen, runId]) => {
    if (isOpen && runId) {
      await nextTick();
      if (detailDialog.value && !detailDialog.value.open) {
        if (typeof detailDialog.value.showModal === "function") {
          detailDialog.value.showModal();
        } else {
          detailDialog.value.setAttribute("open", "");
        }
      }
      await loadDetail(String(runId));
    } else if (!isOpen && detailDialog.value?.open) {
      if (typeof detailDialog.value.close === "function") {
        detailDialog.value.close();
      } else {
        detailDialog.value.removeAttribute("open");
      }
    }
  },
  { immediate: true },
);
</script>

<template>
  <dialog
    ref="detailDialog"
    class="modal result-detail-drawer"
    @close="onDialogClosed"
    @click="handleBackdropClick"
  >
    <div class="drawer-content" @click.stop>
      <div class="drawer-header">
        <div class="detail-header-info">
          <div class="detail-header-tags">
            <span
              v-if="currentSummary?.domain"
              class="badge"
              :class="currentSummary.domain"
            >
              {{ labelDomain(currentSummary.domain) }}
            </span>
            <span
              v-if="currentSummary?.media_kind"
              class="badge media-badge"
            >
              {{ labelMediaKind(currentSummary.media_kind) }}
            </span>
            <span
              v-if="currentSummary?.status"
              class="badge"
              :class="currentSummary.status"
            >
              {{ labelRunStatus(currentSummary.status) }}
            </span>
          </div>
          <h3>{{ currentSummary ? resultTitle(currentSummary) : (props.runId || "") }}</h3>
          <p v-if="currentSummary" class="detail-description">
            {{ resultDescription }}
          </p>
        </div>
        <div class="drawer-header-actions">
          <template v-if="result">
            <button
              class="button secondary header-action-btn"
              title="导出结构化结果 JSON"
              @click="exportResult('json')"
            >
              <Download :size="13" />导出 JSON
            </button>
            <button
              class="button secondary header-action-btn"
              title="导出对象明细表 CSV"
              @click="exportResult('csv')"
            >
              <Download :size="13" />导出 CSV
            </button>
          </template>
          <button
            class="icon-button close-btn"
            title="关闭详情"
            aria-label="关闭详情"
            @click="close"
          >
            <X :size="16" />
          </button>
        </div>
      </div>

      <div class="drawer-body">
        <div v-if="detailLoading" class="empty detail-loading">
          正在加载解析结果详情...
        </div>
        <div v-else-if="error" class="callout error">
          {{ error }}
        </div>
        <template v-else-if="currentSummary">
          <!-- 顶部核心指标栏 -->
          <dl class="result-counters">
            <div>
              <dt>分析单元</dt>
              <dd>{{ unitTotal || currentSummary.unit_count }}</dd>
            </div>
            <div>
              <dt>识别对象</dt>
              <dd>{{ objectCount }}</dd>
            </div>
            <div v-if="result?.models.length">
              <dt>使用模型</dt>
              <dd>{{ result.models.length }}</dd>
            </div>
            <div v-if="currentSummary.domain === 'portrait'">
              <dt>人员 / 人脸</dt>
              <dd>{{ currentSummary.person_count ?? 0 }} / {{ currentSummary.face_count ?? 0 }}</dd>
            </div>
            <div v-else-if="currentSummary.domain === 'ocr'">
              <dt>文本块 / 字符</dt>
              <dd>{{ currentSummary.ocr_block_count ?? 0 }} / {{ currentSummary.text_length ?? 0 }}</dd>
            </div>
            <div v-else-if="currentSummary.domain === 'fashion'">
              <dt>识别目标</dt>
              <dd>{{ objectCount }} 个</dd>
            </div>
            <div v-else-if="currentSummary.domain === 'behavior'">
              <dt>动作对象</dt>
              <dd>{{ objectCount }} 个</dd>
            </div>
          </dl>

          <!-- 媒体技术元数据网格（如有） -->
          <dl v-if="mediaMetadata && hasMediaMetadataItems" class="metadata-grid">
            <div v-if="mediaMetadata.width && mediaMetadata.height">
              <dt>画面尺寸</dt>
              <dd>{{ mediaMetadata.width }} × {{ mediaMetadata.height }}</dd>
            </div>
            <div v-if="mediaMetadata.duration_ms != null">
              <dt>时长</dt>
              <dd>{{ formatDuration(mediaMetadata.duration_ms) }}</dd>
            </div>
            <div v-if="mediaMetadata.fps != null">
              <dt>帧率</dt>
              <dd>{{ mediaMetadata.fps.toFixed(2) }}</dd>
            </div>
            <div v-if="mediaMetadata.codec || mediaMetadata.format">
              <dt>编码格式</dt>
              <dd>{{ mediaMetadata.codec || mediaMetadata.format }}</dd>
            </div>
            <div v-if="mediaMetadata.sample_strategy">
              <dt>采样策略</dt>
              <dd>{{ labelSampleStrategy(mediaMetadata.sample_strategy) }}</dd>
            </div>
            <div v-if="mediaMetadata.frames_read != null">
              <dt>读取帧数</dt>
              <dd>{{ mediaMetadata.frames_read }}</dd>
            </div>
            <div v-if="mediaMetadata.reconnect_count != null">
              <dt>重连次数</dt>
              <dd>{{ mediaMetadata.reconnect_count }}</dd>
            </div>
            <div v-if="mediaMetadata.elapsed_ms != null">
              <dt>解码耗时</dt>
              <dd>{{ (mediaMetadata.elapsed_ms / 1000).toFixed(2) }} 秒</dd>
            </div>
            <div v-if="mediaMetadata.timestamp_source" class="metadata-wide">
              <dt>时间戳来源</dt>
              <dd>{{ labelTimestampSource(mediaMetadata.timestamp_source) }}</dd>
            </div>
          </dl>


          <template v-if="result">
            <!-- 两栏式科学布局：左侧时间轴，右侧特征图片与目标明细 -->
            <div class="result-inspect-layout">
              <!-- 左栏：时间轴 / 单元序列 -->
              <section class="timeline-column panel">
                <div class="panel-header">
                  <div class="column-title">
                    <Clock :size="15" />
                    <strong>时间轴 / 单元序列</strong>
                  </div>
                  <span class="badge">{{ result.units.length }}</span>
                </div>
                <div class="timeline-scroll-list">
                  <button
                    v-for="(unit, idx) in result.units"
                    :key="unit.unit_id"
                    class="timeline-card"
                    :class="{ selected: selectedUnit?.unit_id === unit.unit_id }"
                    @click="selectedUnit = unit"
                  >
                    <div class="timeline-card-main">
                      <span class="timeline-seq">#{{ idx + 1 }}</span>
                      <div class="timeline-info">
                        <strong class="timeline-time">
                          {{ unit.page_number ? `第 ${unit.page_number} 页` : formatUnitPosition(unit) }}
                        </strong>
                        <span class="timeline-res">{{ unit.width }} × {{ unit.height }}</span>
                      </div>
                    </div>
                    <span
                      class="timeline-obj-badge"
                      :class="{ 'has-obj': unit.objects.length > 0 }"
                    >
                      {{ unit.objects.length }} 个对象
                    </span>
                  </button>
                </div>
              </section>

              <!-- 右栏：当前单元特征图片与对象明细 -->
              <section class="detail-main-column">
                <!-- 当前单元特征图片展示区 -->
                <div class="feature-crops-wrapper panel">
                  <div class="panel-header">
                    <div class="column-title">
                      <ScanFace :size="15" />
                      <strong>当前单元特征图片</strong>
                    </div>
                    <small v-if="selectedUnit" class="muted">
                      {{ selectedUnit.page_number ? `第 ${selectedUnit.page_number} 页` : formatUnitPosition(selectedUnit) }} · {{ selectedUnit.objects.length }} 个识别目标
                    </small>
                  </div>
                  <div class="panel-body feature-crops-body">
                    <FeatureCropGallery
                      :run-id="result.run_id"
                      :unit="selectedUnit"
                    />
                  </div>
                </div>

                <!-- OCR 综合展示面板（HTML 排版、合规审查、海报轮播、原始文本） -->
                <div v-if="currentSummary.domain === 'ocr'" class="panel ocr-panel">
                  <div class="panel-header ocr-panel-header">
                    <div class="ocr-tabs">
                      <button
                        type="button"
                        class="ocr-tab-btn"
                        :class="{ active: activeOcrTab === 'layout' }"
                        @click="activeOcrTab = 'layout'"
                      >
                        <Layout :size="14" />
                        <span>视觉排版</span>
                      </button>
                      <button
                        type="button"
                        class="ocr-tab-btn"
                        :class="{ active: activeOcrTab === 'compliance' }"
                        @click="activeOcrTab = 'compliance'"
                      >
                        <ShieldAlert
                          v-if="complianceReport?.status === 'block'"
                          :size="14"
                          class="text-danger"
                        />
                        <ShieldAlert
                          v-else-if="complianceReport?.status === 'suspect'"
                          :size="14"
                          class="text-warning"
                        />
                        <ShieldCheck v-else :size="14" class="text-success" />
                        <span>合规质检</span>
                        <span
                          v-if="complianceReport?.total_hits"
                          class="tab-badge"
                          :class="complianceReport.status"
                        >
                          {{ complianceReport.total_hits }}
                        </span>
                      </button>
                      <button
                        v-if="ocrSlides.length > 0"
                        type="button"
                        class="ocr-tab-btn"
                        :class="{ active: activeOcrTab === 'slides' }"
                        @click="activeOcrTab = 'slides'"
                      >
                        <Film :size="14" />
                        <span>大屏海报集</span>
                        <span class="tab-badge info">{{ ocrSlides.length }}</span>
                      </button>
                      <button
                        type="button"
                        class="ocr-tab-btn"
                        :class="{ active: activeOcrTab === 'raw' }"
                        @click="activeOcrTab = 'raw'"
                      >
                        <FileText :size="14" />
                        <span>提取纯文本</span>
                      </button>
                    </div>

                    <!-- 右侧操作栏 -->
                    <div class="ocr-tab-actions">
                      <template v-if="activeOcrTab === 'layout'">
                        <button
                          type="button"
                          class="button small"
                          :class="underlayMode ? 'primary' : 'secondary'"
                          :title="underlayMode ? '退出左右双屏对照' : '开启左右双屏对照'"
                          :disabled="underlayLoading"
                          @click="toggleUnderlayMode"
                        >
                          <Loader2 v-if="underlayLoading" :size="13" class="spin" />
                          <Columns2 v-else :size="13" />
                          {{ underlayLoading ? "加载原图中..." : underlayMode ? "退出双屏" : "左右双屏" }}
                        </button>
                        <button
                          type="button"
                          class="button small secondary"
                          title="一键导出为标准 HTML 独立单页"
                          @click="exportHtmlLayout"
                        >
                          <Download :size="13" />
                          导出 HTML
                        </button>
                      </template>
                      <template v-else-if="activeOcrTab === 'raw'">
                        <button
                          type="button"
                          class="button small secondary"
                          title="复制全部纯文本"
                          @click="copyRawOcrText"
                        >
                          <Check v-if="copiedText" :size="13" class="text-success" />
                          <Copy v-else :size="13" />
                          {{ copiedText ? "已复制" : "复制文本" }}
                        </button>
                      </template>
                    </div>
                  </div>

                  <div class="panel-body ocr-panel-body">
                    <!-- Tab 1: 视觉仿真排版 -->
                    <div v-show="activeOcrTab === 'layout'" class="ocr-layout-view">
                      <div
                        v-if="currentHtmlLayout"
                        class="ocr-layout-canvas-wrapper"
                        :class="{
                          'split-mode': underlayMode && underlayImageUrl,
                        }"
                      >
                        <!-- 左右分栏模式下的左侧原始原图 -->
                        <div
                          v-if="underlayMode && underlayImageUrl"
                          class="ocr-split-underlay-column"
                        >
                          <div class="split-column-header">
                            <Eye :size="13" />
                            <strong>原始文档 / 视频帧原图</strong>
                          </div>
                          <div class="split-image-container">
                            <img
                              :src="underlayImageUrl"
                              alt="原始文档原图"
                              class="underlay-split-img"
                            />
                          </div>
                        </div>

                        <!-- 仿真排版展示容器 -->
                        <div class="ocr-split-rendered-column">
                          <div
                            v-if="underlayMode && underlayImageUrl"
                            class="split-column-header"
                          >
                            <Layout :size="13" />
                            <strong>1:1 视觉仿真排版还原</strong>
                          </div>
                          <div class="ocr-html-rendered" v-html="currentHtmlLayout" />
                        </div>
                      </div>
                      <div v-else class="empty-state">
                        <Layout :size="32" class="muted" />
                        <p>当前单元未生成 HTML 排版，请确认流水线已开启版面排版还原。</p>
                      </div>
                    </div>

                    <!-- Tab 2: 文本合规质检报告 -->
                    <div v-show="activeOcrTab === 'compliance'" class="ocr-compliance-view">
                      <div v-if="complianceReport" class="compliance-report-container">
                        <div class="compliance-summary-card" :class="complianceReport.status">
                          <div class="summary-icon">
                            <ShieldAlert v-if="complianceReport.status === 'block'" :size="24" />
                            <ShieldAlert v-else-if="complianceReport.status === 'suspect'" :size="24" />
                            <ShieldCheck v-else :size="24" />
                          </div>
                          <div class="summary-content">
                            <div class="summary-title-row">
                              <span class="compliance-status-tag" :class="complianceReport.status">
                                {{ complianceReport.status === 'block' ? '严重违规' : complianceReport.status === 'suspect' ? '疑似存疑' : '合规通过' }}
                              </span>
                              <span class="risk-score">风险评分: {{ (complianceReport.risk_score * 100).toFixed(0) }}</span>
                            </div>
                            <p class="summary-desc">{{ complianceReport.summary }}</p>
                          </div>
                        </div>

                        <!-- 违规命中列表 -->
                        <div v-if="complianceReport.hits?.length" class="compliance-hits-list">
                          <div
                            v-for="(hit, idx) in complianceReport.hits"
                            :key="idx"
                            class="compliance-hit-item"
                            :class="hit.severity"
                          >
                            <div class="hit-header">
                              <span class="hit-word-badge">{{ hit.word }}</span>
                              <span class="hit-category">{{ hit.rule_category }}</span>
                              <span
                                v-if="hit.rule_id?.startsWith('custom_')"
                                class="hit-custom-tag"
                              >
                                企业自定义
                              </span>
                              <span class="hit-severity-badge" :class="hit.severity">
                                {{ hit.severity === 'block' ? '禁止发布' : '建议修改' }}
                              </span>
                            </div>
                            <div class="hit-body">
                              <div class="hit-ref">
                                <strong>法规依据:</strong> {{ hit.legal_reference }}
                              </div>
                              <div class="hit-sug">
                                <strong>处置建议:</strong> {{ hit.suggestion }}
                              </div>
                            </div>
                          </div>
                        </div>
                        <div v-else class="compliance-all-clear">
                          <ShieldCheck :size="40" class="text-success" />
                          <h4>未检测到违规极限词或风险信息</h4>
                          <p class="muted">符合《中华人民共和国广告法》及公共内容安全要求</p>
                        </div>
                      </div>
                      <div v-else class="empty-state">
                        <p class="muted">未检测到合规分析结果</p>
                      </div>
                    </div>

                    <!-- Tab 3: 大屏海报轮播集 -->
                    <div v-show="activeOcrTab === 'slides'" class="ocr-slides-view">
                      <div class="slides-grid">
                        <div
                          v-for="(slide, idx) in ocrSlides"
                          :key="slide.slide_id"
                          class="slide-card"
                          :class="{ active: activeSlideIndex === idx }"
                          @click="activeSlideIndex = idx; activeOcrTab = 'layout'"
                        >
                          <div class="slide-card-header">
                            <span class="slide-title">海报 #{{ idx + 1 }}</span>
                            <span
                              v-if="slide.compliance"
                              class="slide-status-tag"
                              :class="slide.compliance.status"
                            >
                              {{ slide.compliance.status === 'block' ? '违规' : slide.compliance.status === 'suspect' ? '存疑' : '合规' }}
                            </span>
                          </div>
                          <div class="slide-card-body">
                            <p class="slide-text-snippet">{{ slide.text }}</p>
                          </div>
                          <div class="slide-card-footer">
                            <span class="slide-count">轮播 {{ slide.display_count }} 次</span>
                            <span v-if="slide.duration_seconds" class="slide-dur">展示 {{ slide.duration_seconds.toFixed(1) }}s</span>
                            <span class="slide-action">查看排版 →</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- Tab 4: 提取纯文本 -->
                    <div v-show="activeOcrTab === 'raw'" class="ocr-raw-view">
                      <textarea
                        class="result-text-preview"
                        readonly
                        :value="ocrText"
                        aria-label="OCR 结果文本"
                      />
                    </div>
                  </div>
                </div>

                <!-- 通用领域扩展数据（如适用） -->
                <GenericDomainResult
                  v-if="genericPayload"
                  :payload="genericPayload"
                />

                <!-- 当前单元识别对象明细表 -->
                <div v-if="selectedUnit?.objects.length" class="panel objects-panel">
                  <div class="panel-header">
                    <div class="column-title">
                      <Layers :size="15" />
                      <strong>当前单元目标明细</strong>
                    </div>
                    <span class="badge">{{ selectedUnit.objects.length }}</span>
                  </div>
                  <div class="panel-body">
                    <DataTable
                      :columns="objectColumns"
                      :items="selectedUnit.objects"
                      :page-size="10"
                      :page-size-options="[5, 10, 20, 50]"
                      table-class="bordered-table"
                      empty-text="当前单元未检出目标"
                    >
                      <template #object_type="{ row }">
                        {{ labelObjectType(row.object_type) }}
                      </template>
                      <template #score="{ row }">
                        {{ row.score?.toFixed(3) ?? "-" }}
                      </template>
                      <template #bbox="{ row }">
                        <span class="mono">{{ formatBox(row.bbox) }}</span>
                      </template>
                    </DataTable>
                  </div>
                </div>

                <!-- 原始 JSON 结果折叠区 -->
                <details class="json-details">
                  <summary>原始结果（JSON）</summary>
                  <pre>{{ JSON.stringify(result, null, 2) }}</pre>
                </details>
              </section>
            </div>
          </template>
        </template>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
/* Drawer Dialog Styles */
.result-detail-drawer {
  position: fixed;
  inset: 0 0 0 auto;
  width: min(1200px, 98vw);
  max-width: 100vw;
  height: 100vh;
  max-height: 100vh;
  margin: 0;
  padding: 0;
  border: 0;
  border-left: 1px solid var(--line);
  background: var(--color-surface);
  box-shadow: -12px 0 36px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
}
.result-detail-drawer::backdrop {
  background: rgba(17, 26, 24, 0.45);
  backdrop-filter: blur(3px);
}
.result-detail-drawer:not([open]) {
  display: none;
}
.drawer-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-soft, #fbfcfc);
  flex-shrink: 0;
}
.detail-header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.detail-header-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.drawer-header h3 {
  margin: 2px 0 0;
  font-size: 16px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-description {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.header-action-btn {
  height: 30px;
  min-height: 30px;
  padding: 0 10px;
  font-size: 12px;
  gap: 5px;
}
.close-btn {
  width: 30px;
  height: 30px;
  min-width: 30px;
  min-height: 30px;
  border-radius: 5px;
  padding: 0;
}
.drawer-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
  scrollbar-width: thin;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* Counters Grid */
.result-counters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f8faf9;
  overflow: hidden;
  flex-shrink: 0;
}
.result-counters div {
  padding: 10px 14px;
  border-right: 1px solid var(--line);
}
.result-counters div:last-child {
  border-right: 0;
}
.result-counters dt {
  color: var(--muted);
  font-size: 11px;
  font-weight: 650;
}
.result-counters dd {
  margin: 4px 0 0;
  font-size: 19px;
  font-weight: 700;
  color: #17211f;
}

/* Metadata Strip */
.metadata-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 24px;
  margin: 0;
  padding: 8px 14px;
  background: #f8fafc;
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 6px;
  box-sizing: border-box;
  flex-shrink: 0;
}
.metadata-grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: transparent;
  padding: 0;
}
.metadata-grid .metadata-wide {
  width: 100%;
}
.metadata-grid dt {
  color: var(--muted, #64748b);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.2;
}
.metadata-grid dd {
  margin: 0;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text, #1e293b);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

/* Replay Layout: 2 Columns */
.result-inspect-layout {
  display: grid;
  grid-template-columns: 290px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  min-height: 480px;
}

/* Timeline Left Column */
.timeline-column {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface, #fff);
  overflow: hidden;
}
.timeline-column .panel-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  background: #fbfcfc;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.column-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: var(--color-text, #17211f);
}
.timeline-scroll-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  max-height: 600px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.timeline-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: #fdfefe;
  text-align: left;
  cursor: pointer;
  transition: all 120ms ease;
  width: 100%;
}
.timeline-card:hover {
  border-color: var(--line-strong, #c4d0cc);
  background: var(--surface-soft, #f4f7f6);
}
.timeline-card.selected {
  border-color: var(--teal, #1c7c68);
  background: rgba(28, 124, 104, 0.08);
}
.timeline-card-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.timeline-seq {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  min-width: 24px;
}
.timeline-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.timeline-time {
  font-size: 12.5px;
  color: #17211f;
}
.timeline-res {
  font-size: 10.5px;
  color: var(--muted);
}
.timeline-obj-badge {
  font-size: 10.5px;
  padding: 2px 6px;
  border-radius: 10px;
  background: #eaefed;
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}
.timeline-obj-badge.has-obj {
  background: rgba(28, 124, 104, 0.15);
  color: #166555;
  font-weight: 600;
}

/* Detail Main Right Column */
.detail-main-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.feature-crops-wrapper,
.ocr-panel,
.objects-panel {
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface, #fff);
  overflow: hidden;
}
.feature-crops-wrapper .panel-header,
.ocr-panel .panel-header,
.objects-panel .panel-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: #fbfcfc;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.feature-crops-body {
  padding: 12px 14px;
}
.ocr-panel .panel-body,
.objects-panel .panel-body {
  padding: 12px 14px;
}
.result-text-preview {
  width: 100%;
  min-height: 120px;
  max-height: 240px;
  resize: vertical;
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: var(--surface-soft, #f8faf9);
}
.json-details {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 12px;
  background: #fbfcfc;
  font-size: 12px;
}
.json-details summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--muted);
}
.json-details pre {
  margin: 8px 0 0;
  max-height: 320px;
  overflow-y: auto;
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  background: var(--surface-soft, #f8faf9);
  padding: 10px;
  border-radius: 4px;
  scrollbar-width: thin;
}
.detail-loading {
  min-height: 180px;
}

@media (max-width: 900px) {
  .result-inspect-layout {
    grid-template-columns: 1fr;
  }
  .timeline-scroll-list {
    max-height: 240px;
  }
}

/* OCR Tabs & Multifunctional Views */
.ocr-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--line, #e2e8f0);
  padding: 10px 14px;
}

.ocr-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.ocr-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ocr-tab-btn:hover {
  background: var(--surface-soft, #f1f5f9);
  color: var(--text);
}

.ocr-tab-btn.active {
  background: var(--color-accent-soft, #e4f1f1);
  color: var(--color-accent-hover, #065e67);
  border-color: var(--color-accent-soft, #e4f1f1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.tab-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.tab-badge.block {
  background: #fee2e2;
  color: #ef4444;
}

.tab-badge.suspect {
  background: #fef3c7;
  color: #d97706;
}

.tab-badge.pass {
  background: #dcfce7;
  color: #16a34a;
}

.tab-badge.info {
  background: #e0f2fe;
  color: #0284c7;
}

.ocr-tab-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ocr-panel-body {
  padding: 14px;
}

/* Layout View */
.ocr-layout-canvas-wrapper {
  width: 100%;
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
  overflow: auto;
  box-sizing: border-box;
  position: relative;
  transition: all 0.2s ease;
}

/* 左右双屏分栏模式 */
.ocr-layout-canvas-wrapper.split-mode {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
  background: #f1f5f9;
}

.ocr-split-underlay-column,
.ocr-split-rendered-column {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.split-column-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted, #64748b);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
}

.split-image-container {
  width: 100%;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  background: #ffffff;
  border: 1px solid var(--line, #e2e8f0);
}

.underlay-split-img {
  width: 100%;
  height: auto;
  display: block;
  object-fit: contain;
}

.ocr-html-rendered {
  width: 100%;
}

/* Compliance Report View */
.compliance-report-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.compliance-summary-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid transparent;
}

.compliance-summary-card.block {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

.compliance-summary-card.suspect {
  background: #fffbeb;
  border-color: #fde68a;
  color: #92400e;
}

.compliance-summary-card.pass {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.summary-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.compliance-status-tag {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.compliance-status-tag.block {
  background: #ef4444;
  color: #fff;
}

.compliance-status-tag.suspect {
  background: #f59e0b;
  color: #fff;
}

.compliance-status-tag.pass {
  background: #22c55e;
  color: #fff;
}

.risk-score {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.85;
}

.summary-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}

.compliance-hits-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.compliance-hit-item {
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 6px;
  padding: 12px;
  background: var(--surface, #fff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.compliance-hit-item.block {
  border-left: 4px solid #ef4444;
}

.compliance-hit-item.suspect {
  border-left: 4px solid #f59e0b;
}

.hit-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.hit-word-badge {
  font-size: 13px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: #fee2e2;
  color: #dc2626;
}

.hit-category {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.hit-custom-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.hit-severity-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
}

.hit-severity-badge.block {
  background: #fee2e2;
  color: #dc2626;
}

.hit-severity-badge.suspect {
  background: #fef3c7;
  color: #d97706;
}

.hit-body {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-soft, #475569);
}

.hit-ref,
.hit-sug {
  margin-top: 4px;
}

.compliance-all-clear {
  text-align: center;
  padding: 32px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

/* Slides Grid */
.slides-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.slide-card {
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface, #fff);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slide-card:hover {
  border-color: var(--brand, #3b82f6);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
}

.slide-card.active {
  border-color: var(--brand, #3b82f6);
  background: #eff6ff;
}

.slide-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.slide-title {
  font-size: 13px;
  font-weight: 600;
}

.slide-status-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.slide-status-tag.block {
  background: #fee2e2;
  color: #dc2626;
}

.slide-status-tag.suspect {
  background: #fef3c7;
  color: #d97706;
}

.slide-status-tag.pass {
  background: #dcfce7;
  color: #16a34a;
}

.slide-text-snippet {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.slide-card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--muted);
  margin-top: auto;
  border-top: 1px dashed var(--line, #e2e8f0);
  padding-top: 6px;
}

.slide-action {
  margin-left: auto;
  color: var(--brand, #3b82f6);
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 36px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--muted);
}
</style>
