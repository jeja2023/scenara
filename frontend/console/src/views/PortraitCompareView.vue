<script setup lang="ts">
import {
  CheckCircle2,
  FileImage,
  ScanFace,
  Upload,
  XCircle,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, apiBlob, apiForm, blobToDataUrl, userFacingError } from "../api";
import type { MediaAsset } from "../types";

interface PortraitInputSummary {
  face_count: number;
  selected_face_index: number;
  selected_face_box?: number[] | null;
  quality_score?: number | null;
  model_id: string;
  model_version: string;
  embedding_dimension: number;
  fallback: boolean;
  metadata: Record<string, unknown>;
}

interface CompareResult {
  feature_space_id: string;
  score: number;
  distance: number;
  threshold?: number | null;
  matched?: boolean | null;
  mode: "image" | "asset" | "mixed";
  comparison_id?: string | null;
  left?: PortraitInputSummary | null;
  right?: PortraitInputSummary | null;
}

const assets = ref<MediaAsset[]>([]);
const loading = ref(false);
const comparing = ref(false);
const error = ref("");
const message = ref("");
const result = ref<CompareResult | null>(null);
const threshold = ref("0.80");
const leftFile = ref<File | null>(null);
const rightFile = ref<File | null>(null);
const leftAssetId = ref("");
const rightAssetId = ref("");
const leftPreview = ref("");
const rightPreview = ref("");
const contract = reactive({ featureSpaceId: "自动选择", model: "等待输入" });

const imageAssets = computed(() =>
  assets.value.filter((asset) => asset.kind === "image"),
);
const hasLeft = computed(() => Boolean(leftFile.value || leftAssetId.value));
const hasRight = computed(() => Boolean(rightFile.value || rightAssetId.value));
const verdictLabel = computed(() => {
  if (!result.value) return "等待比对";
  if (result.value.matched === true) return "同一人概率较高";
  if (result.value.matched === false) return "未达到当前阈值";
  return "未设置判定阈值";
});

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

async function refreshAssets(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const page = await api<{ items: MediaAsset[] }>(
      "/api/v1/media/assets?limit=200",
    );
    assets.value = page.items;
  } catch (caught) {
    error.value = userFacingError(caught, "图片资产加载失败");
  } finally {
    loading.value = false;
  }
}

function setFile(side: "left" | "right", event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null;
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    error.value = "请选择图片文件";
    return;
  }
  clearFeedback();
  if (side === "left") {
    leftFile.value = file;
    leftAssetId.value = "";
    leftPreview.value = URL.createObjectURL(file);
  } else {
    rightFile.value = file;
    rightAssetId.value = "";
    rightPreview.value = URL.createObjectURL(file);
  }
}

async function setAsset(
  side: "left" | "right",
  assetId: string,
): Promise<void> {
  if (!assetId) return;
  clearFeedback();
  try {
    const preview = await blobToDataUrl(
      await apiBlob(
        `/api/v1/media/assets/${encodeURIComponent(assetId)}/preview`,
      ),
    );
    if (side === "left") {
      leftAssetId.value = assetId;
      leftFile.value = null;
      leftPreview.value = preview;
    } else {
      rightAssetId.value = assetId;
      rightFile.value = null;
      rightPreview.value = preview;
    }
  } catch (caught) {
    error.value = userFacingError(caught, "资产预览加载失败");
  }
}

function clearSide(side: "left" | "right"): void {
  if (side === "left") {
    leftFile.value = null;
    leftAssetId.value = "";
    leftPreview.value = "";
  } else {
    rightFile.value = null;
    rightAssetId.value = "";
    rightPreview.value = "";
  }
}

function summaryLabel(value: PortraitInputSummary | null | undefined): string {
  if (!value) return "未提取";
  return `${value.face_count} 张人脸 · 选中 ${value.selected_face_index + 1} · ${value.embedding_dimension} 维`;
}

async function compare(): Promise<void> {
  clearFeedback();
  result.value = null;
  if (!hasLeft.value || !hasRight.value) {
    error.value = "请为左右两侧各选择一张图片";
    return;
  }
  comparing.value = true;
  try {
    let data: CompareResult;
    const cutoff = Number(threshold.value);
    if (leftAssetId.value && rightAssetId.value) {
      data = await api<CompareResult>("/api/v1/portrait/compare/assets", {
        method: "POST",
        body: JSON.stringify({
          left_asset_id: leftAssetId.value,
          right_asset_id: rightAssetId.value,
          threshold: Number.isFinite(cutoff) ? cutoff : null,
        }),
      });
    } else if (leftFile.value && rightFile.value) {
      const form = new FormData();
      form.append("left", leftFile.value);
      form.append("right", rightFile.value);
      if (Number.isFinite(cutoff)) form.append("threshold", String(cutoff));
      data = await apiForm<CompareResult>(
        "/api/v1/portrait/compare/images",
        form,
      );
    } else if (leftAssetId.value && rightFile.value) {
      const form = new FormData();
      form.append("asset_id", leftAssetId.value);
      form.append("file", rightFile.value);
      if (Number.isFinite(cutoff)) form.append("threshold", String(cutoff));
      data = await apiForm<CompareResult>(
        "/api/v1/portrait/compare/asset-image",
        form,
      );
    } else if (leftFile.value && rightAssetId.value) {
      const form = new FormData();
      form.append("file", leftFile.value);
      form.append("asset_id", rightAssetId.value);
      if (Number.isFinite(cutoff)) form.append("threshold", String(cutoff));
      data = await apiForm<CompareResult>(
        "/api/v1/portrait/compare/image-asset",
        form,
      );
    } else {
      error.value = "请为左右两侧各选择一张图片";
      return;
    }
    result.value = data;
    contract.featureSpaceId = data.feature_space_id;
    contract.model = data.left
      ? `${data.left.model_id} · ${data.left.model_version}`
      : "已按索引契约完成比对";
    message.value = "比对完成，结果已记录审计事件";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "人像比对失败，请检查图片质量和索引契约",
    );
  } finally {
    comparing.value = false;
  }
}

onMounted(() => void refreshAssets());
useRefresh(refreshAssets);
</script>

<template>
  <section class="page portrait-compare-page">
    <div class="page-header">
      <div class="toolbar">
        <label class="threshold-control">
          <span>判定阈值</span>
          <input
            v-model="threshold"
            type="number"
            min="-1"
            max="1"
            step="0.01"
          />
        </label>
      </div>
    </div>

    <div v-if="error" class="notice error">{{ error }}</div>
    <div v-if="message" class="notice success">{{ message }}</div>

    <div class="compare-layout">
      <div class="compare-sources">
        <article
          v-for="side in ['left', 'right']"
          :key="side"
          class="panel source-panel"
        >
          <div class="panel-header">
            <div>
              <h2>{{ side === "left" ? "输入 A" : "输入 B" }}</h2>
              <span class="muted">{{
                side === "left" ? "待核验的人像" : "参照人像"
              }}</span>
            </div>
            <button
              class="icon-button"
              title="清除输入"
              @click="clearSide(side as 'left' | 'right')"
            >
              <XCircle :size="17" />
            </button>
          </div>
          <div class="source-preview">
            <img
              v-if="side === 'left' ? leftPreview : rightPreview"
              :src="side === 'left' ? leftPreview : rightPreview"
              alt=""
            />
            <div v-else class="source-empty">
              <ScanFace :size="30" /><span>未选择图片</span>
            </div>
          </div>
          <div class="source-actions">
            <label class="button secondary upload-button">
              <Upload :size="15" />上传图片
              <input
                type="file"
                accept="image/*"
                @change="setFile(side as 'left' | 'right', $event)"
              />
            </label>
            <select
              :value="side === 'left' ? leftAssetId : rightAssetId"
              @change="
                setAsset(
                  side as 'left' | 'right',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option value="">从图片资产选择</option>
              <option
                v-for="asset in imageAssets"
                :key="asset.asset_id"
                :value="asset.asset_id"
              >
                {{ asset.filename || asset.asset_id }}
              </option>
            </select>
          </div>
        </article>
      </div>

      <aside class="panel compare-result-panel">
        <div class="panel-header">
          <h2>比对结论</h2>
          <span class="badge">{{
            result?.mode === "asset"
              ? "资产"
              : result?.mode === "mixed"
                ? "混合输入"
                : "图片"
          }}</span>
        </div>
        <div v-if="result" class="result-body">
          <div
            class="verdict"
            :class="{
              matched: result.matched === true,
              unmatched: result.matched === false,
            }"
          >
            <CheckCircle2 v-if="result.matched === true" :size="25" />
            <XCircle v-else-if="result.matched === false" :size="25" />
            <ScanFace v-else :size="25" />
            <strong>{{ verdictLabel }}</strong>
          </div>
          <div class="score-value">
            <strong>{{ result.score.toFixed(4) }}</strong
            ><span>相似度分数</span>
          </div>
          <div class="result-metrics">
            <div>
              <span>距离</span><strong>{{ result.distance.toFixed(4) }}</strong>
            </div>
            <div>
              <span>阈值</span
              ><strong>{{ result.threshold?.toFixed(2) ?? "未设置" }}</strong>
            </div>
            <div>
              <span>索引契约</span
              ><strong class="mono">{{ result.feature_space_id }}</strong>
            </div>
          </div>
          <div class="input-summary">
            <div>
              <span>输入 A</span
              ><strong>{{ summaryLabel(result.left) }}</strong>
            </div>
            <div>
              <span>输入 B</span
              ><strong>{{ summaryLabel(result.right) }}</strong>
            </div>
          </div>
        </div>
        <div v-else class="empty result-empty">
          <ScanFace :size="28" /><span>完成两侧输入后开始比对</span>
        </div>
        <div class="panel-footer">
          <button
            class="button primary compare-button"
            :disabled="comparing || !hasLeft || !hasRight"
            @click="compare"
          >
            <ScanFace :size="16" />{{ comparing ? "分析中…" : "开始比对" }}
          </button>
        </div>
      </aside>
    </div>

    <div class="contract-strip">
      <FileImage :size="18" />
      <div>
        <strong>当前索引契约</strong><span>{{ contract.featureSpaceId }}</span>
      </div>
      <div>
        <strong>模型</strong><span>{{ contract.model }}</span>
      </div>
      <div class="contract-note">
        原始特征仅在服务端参与计算，控制台只展示脱敏摘要。
      </div>
    </div>
  </section>
</template>

<style scoped>
.portrait-compare-page {
  padding-bottom: 28px;
}
.threshold-control {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.threshold-control input {
  width: 84px;
  min-height: 34px;
}
.notice {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 5px;
  margin-bottom: 12px;
  font-size: 13px;
}
.notice.error {
  color: #963d32;
  background: #fff5f2;
  border-color: #edc5be;
}
.notice.success {
  color: #2b6d4a;
  background: #f0f8f2;
  border-color: #c5e0cc;
}
.compare-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(330px, 0.85fr);
  gap: 16px;
  align-items: start;
}
.compare-sources {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.source-panel {
  overflow: hidden;
}
.panel-header > div {
  display: grid;
  gap: 3px;
}
.panel-header .muted {
  font-size: 11px;
}
.source-preview {
  aspect-ratio: 4 / 3;
  margin: 14px;
  background: #0d1917;
  border-radius: 4px;
  overflow: hidden;
  display: grid;
  place-items: center;
}
.source-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.source-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  color: #8ba09a;
  font-size: 12px;
}
.source-actions {
  display: grid;
  gap: 8px;
  padding: 0 14px 14px;
}
.upload-button {
  position: relative;
  overflow: hidden;
}
.upload-button input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.source-actions select {
  min-height: 34px;
}
.compare-result-panel {
  min-height: 100%;
}
.result-body {
  padding: 16px;
}
.verdict {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 12px;
  color: #5f6d69;
  background: #f1f4f3;
  border-radius: 5px;
}
.verdict.matched {
  color: #216640;
  background: #eaf7ee;
}
.verdict.unmatched {
  color: #963d32;
  background: #fff0ed;
}
.score-value {
  display: grid;
  gap: 4px;
  margin: 24px 0;
  text-align: center;
}
.score-value strong {
  font-size: 42px;
  line-height: 1;
  color: var(--graphite);
}
.score-value span,
.result-metrics span,
.input-summary span {
  color: var(--muted);
  font-size: 11px;
}
.result-metrics {
  display: grid;
  gap: 10px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.result-metrics div,
.input-summary div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: baseline;
}
.result-metrics strong {
  text-align: right;
}
.input-summary {
  display: grid;
  gap: 9px;
  padding-top: 14px;
}
.input-summary strong {
  font-size: 12px;
  text-align: right;
}
.panel-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}
.compare-button {
  width: 100%;
}
.result-empty {
  min-height: 300px;
  gap: 10px;
}
.contract-strip {
  display: grid;
  grid-template-columns: auto minmax(150px, 1fr) minmax(150px, 1fr) minmax(
      220px,
      1.3fr
    );
  align-items: center;
  gap: 14px;
  margin-top: 16px;
  padding: 14px 16px;
  background: #f8faf9;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--muted);
}
.contract-strip > svg {
  color: var(--teal);
}
.contract-strip div {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.contract-strip strong {
  color: var(--graphite);
  font-size: 11px;
}
.contract-strip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.contract-note {
  font-size: 12px;
  line-height: 1.5;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 980px) {
  .compare-layout {
    grid-template-columns: 1fr;
  }
  .contract-strip {
    grid-template-columns: auto 1fr 1fr;
  }
  .contract-note {
    grid-column: 2 / -1;
  }
}
@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
  }
  .compare-sources {
    grid-template-columns: 1fr;
  }
  .contract-strip {
    grid-template-columns: auto 1fr;
  }
  .contract-strip > div:nth-of-type(2),
  .contract-note {
    grid-column: 2;
  }
}
</style>
