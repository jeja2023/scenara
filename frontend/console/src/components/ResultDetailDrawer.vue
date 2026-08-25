<script setup lang="ts">
import {
  Clock,
  Download,
  FileText,
  Layers,
  ScanFace,
  X,
} from "@lucide/vue";
import { computed, nextTick, ref, watch } from "vue";
import { api, userFacingError } from "../api";
import DataTable from "./DataTable.vue";
import FeatureCropGallery from "./FeatureCropGallery.vue";
import GenericDomainResult from "./GenericDomainResult.vue";
import {
  labelDomain,
  labelMediaKind,
  labelRunStatus,
  labelSampleStrategy,
} from "../labels";
import type {
  MediaUnitResult,
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
  return `${currentSummary.value.person_count ?? 0} 个人员 · ${currentSummary.value.face_count ?? 0} 张人脸`;
});

const mediaMetadata = computed(() => result.value?.media_metadata ?? null);
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
  { key: "object_id", label: "标识", class: "mono truncate" },
  { key: "object_type", label: "类别" },
  { key: "score", label: "置信度" },
  { key: "bbox", label: "边界框 (x, y, w, h)", class: "mono" },
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
          </dl>

          <!-- 媒体技术元数据网格（如有） -->
          <dl v-if="mediaMetadata" class="metadata-grid">
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

                <!-- OCR 文本预览（如适用） -->
                <div v-if="currentSummary.domain === 'ocr'" class="panel ocr-panel">
                  <div class="panel-header">
                    <div class="column-title">
                      <FileText :size="15" />
                      <strong>识别文本</strong>
                    </div>
                  </div>
                  <div class="panel-body">
                    <textarea
                      class="result-text-preview"
                      readonly
                      :value="ocrText"
                      aria-label="OCR 结果文本"
                    />
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
                      table-class="bordered-table"
                    >
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

/* Metadata Grid */
.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 1px;
  margin: 0;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}
.metadata-grid div {
  padding: 8px 12px;
  background: var(--surface, #fff);
}
.metadata-grid .metadata-wide {
  grid-column: 1 / -1;
}
.metadata-grid dt {
  color: var(--muted);
  font-size: 11px;
}
.metadata-grid dd {
  margin: 2px 0 0;
  font-size: 12.5px;
  font-weight: 700;
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
</style>
