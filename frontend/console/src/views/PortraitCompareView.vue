<script setup lang="ts">
import {
  CheckCircle2,
  FileImage,
  RotateCcw,
  ScanFace,
  Upload,
  X,
  XCircle,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, apiBlob, apiForm, blobToDataUrl, revokeBlobUrl, userFacingError } from "../api";
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
  if (result.value.matched === true) return "同一人判定通过";
  if (result.value.matched === false) return "未达到匹配阈值";
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
    revokeBlobUrl(leftPreview.value);
    leftPreview.value = URL.createObjectURL(file);
  } else {
    rightFile.value = file;
    rightAssetId.value = "";
    revokeBlobUrl(rightPreview.value);
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
      revokeBlobUrl(leftPreview.value);
      leftPreview.value = preview;
    } else {
      rightAssetId.value = assetId;
      rightFile.value = null;
      revokeBlobUrl(rightPreview.value);
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
    revokeBlobUrl(leftPreview.value);
    leftPreview.value = "";
  } else {
    rightFile.value = null;
    rightAssetId.value = "";
    revokeBlobUrl(rightPreview.value);
    rightPreview.value = "";
  }
}

function resetAll(): void {
  clearSide("left");
  clearSide("right");
  result.value = null;
  clearFeedback();
}

function summaryLabel(value: PortraitInputSummary | null | undefined): string {
  if (!value) return "未提取";
  return `${value.face_count} 张人脸 · 选中第 ${value.selected_face_index + 1} · ${value.embedding_dimension} 维`;
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
      ? `${data.left.model_id} (v${data.left.model_version})`
      : "已按索引契约完成比对";
    message.value = "人像特征比对完成，结果已记录审计事件";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "人像比对失败，请检查图片质量和特征服务状态",
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
    <!-- 顶部单行紧凑控制栏 -->
    <div class="panel filters-panel">
      <div class="filter-toolbar">
        <div class="filter-item">
          <span class="filter-label">判定阈值</span>
          <input
            v-model="threshold"
            type="number"
            min="-1"
            max="1"
            step="0.01"
            class="filter-input threshold-input"
          />
        </div>
        <div class="filter-actions">
          <button class="button secondary filter-btn" @click="resetAll">
            <RotateCcw :size="13" />重置对比
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="callout error">{{ error }}</div>
    <div v-if="message" class="callout success">{{ message }}</div>

    <div class="compare-layout">
      <!-- 左右输入源卡片 -->
      <div class="compare-sources">
        <article
          v-for="side in ['left', 'right']"
          :key="side"
          class="panel source-panel"
        >
          <div class="panel-header">
            <div class="header-left">
              <h2>{{ side === "left" ? "输入源 A" : "输入源 B" }}</h2>
              <span class="muted-text">{{
                side === "left" ? "待核验的人像" : "参照标准人像"
              }}</span>
            </div>
            <button
              v-if="side === 'left' ? hasLeft : hasRight"
              class="icon-button close-btn"
              title="清除输入"
              @click="clearSide(side as 'left' | 'right')"
            >
              <X :size="13" />
            </button>
          </div>

          <div class="source-preview">
            <img
              v-if="side === 'left' ? leftPreview : rightPreview"
              :src="side === 'left' ? leftPreview : rightPreview"
              alt="人像预览"
              class="preview-img"
            />
            <div v-else class="source-empty">
              <ScanFace :size="28" class="text-muted" />
              <span>未选择人像图片</span>
            </div>
          </div>

          <div class="source-actions">
            <label class="button secondary upload-btn">
              <Upload :size="13" />本地上传
              <input
                type="file"
                accept="image/*"
                class="hidden-file-input"
                @change="setFile(side as 'left' | 'right', $event)"
              />
            </label>
            <select
              :value="side === 'left' ? leftAssetId : rightAssetId"
              class="field-select"
              @change="
                setAsset(
                  side as 'left' | 'right',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option value="">从数据资产选择</option>
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

      <!-- 右侧比对结论面板 -->
      <aside class="panel compare-result-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>比对结论</h2>
          </div>
          <span class="badge status-badge" :class="result?.mode ? 'active' : ''">
            {{
              result?.mode === "asset"
                ? "资产比对"
                : result?.mode === "mixed"
                  ? "混合输入"
                  : "图片比对"
            }}
          </span>
        </div>

        <div v-if="result" class="result-body">
          <div
            class="verdict-banner"
            :class="{
              matched: result.matched === true,
              unmatched: result.matched === false,
            }"
          >
            <CheckCircle2 v-if="result.matched === true" :size="20" />
            <XCircle v-else-if="result.matched === false" :size="20" />
            <ScanFace v-else :size="20" />
            <strong>{{ verdictLabel }}</strong>
          </div>

          <div class="score-card">
            <span class="score-num">{{ result.score.toFixed(4) }}</span>
            <span class="score-label">余弦相似度分数</span>
          </div>

          <div class="result-metrics-grid">
            <div class="metric-item">
              <span class="metric-label">特征距离</span>
              <strong class="metric-val">{{ result.distance.toFixed(4) }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">判定阈值</span>
              <strong class="metric-val">{{ result.threshold?.toFixed(2) ?? "未设置" }}</strong>
            </div>
            <div class="metric-item span-full">
              <span class="metric-label">特征空间契约</span>
              <strong class="metric-val mono">{{ result.feature_space_id }}</strong>
            </div>
          </div>

          <div class="input-summary-box">
            <div class="summary-row">
              <span class="summary-label">输入 A</span>
              <span class="summary-val">{{ summaryLabel(result.left) }}</span>
            </div>
            <div class="summary-row">
              <span class="summary-label">输入 B</span>
              <span class="summary-val">{{ summaryLabel(result.right) }}</span>
            </div>
          </div>
        </div>

        <div v-else class="result-empty-box">
          <ScanFace :size="32" class="text-muted" />
          <span>在左侧完成两侧人像输入后开始比对</span>
        </div>

        <div class="panel-footer">
          <button
            class="button primary compare-btn"
            :disabled="comparing || !hasLeft || !hasRight"
            @click="compare"
          >
            <ScanFace :size="14" />{{ comparing ? "特征提取与比对中…" : "开始人像比对" }}
          </button>
        </div>
      </aside>
    </div>

    <!-- 底部索引契约摘要栏 -->
    <div class="contract-strip">
      <FileImage :size="15" class="contract-icon" />
      <div class="contract-item">
        <strong class="contract-label">索引契约：</strong>
        <span class="mono">{{ contract.featureSpaceId }}</span>
      </div>
      <div class="contract-item">
        <strong class="contract-label">模型版本：</strong>
        <span>{{ contract.model }}</span>
      </div>
      <div class="contract-note">
        原始人脸生物特征仅在安全服务内存中计算，控制台绝不存储原始向量。
      </div>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 顶部紧凑控制栏 */
.filters-panel {
  padding: 10px 14px;
  background: #ffffff;
}

.filter-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.filter-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.filter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.filter-input {
  height: 28px;
  line-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  outline: none;
  box-sizing: border-box;
  transition: all 0.15s ease;
}

.threshold-input {
  width: 90px;
}

.filter-input:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.filter-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.filter-btn {
  height: 28px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 对比布局 */
.compare-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(300px, 0.8fr);
  gap: 14px;
}

.compare-sources {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.source-panel {
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-header h2 {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin: 0;
}

.muted-text {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.close-btn {
  height: 20px;
  width: 20px;
  min-height: 20px;
  min-width: 20px;
  padding: 0;
  display: inline-grid;
  place-items: center;
}

.source-preview {
  height: 220px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #fafbfb;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  margin-bottom: 12px;
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.source-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: var(--muted, #64716d);
}

.source-actions {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
}

.upload-btn {
  height: 28px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  margin: 0;
}

.hidden-file-input {
  display: none;
}

.field-select {
  height: 28px;
  line-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  outline: none;
  box-sizing: border-box;
  transition: all 0.15s ease;
}

.field-select:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

/* 结论面板 */
.compare-result-panel {
  display: flex;
  flex-direction: column;
}

.result-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.verdict-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  border-radius: 5px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  color: var(--graphite, #17211f);
  font-size: 13px;
}

.verdict-banner.matched {
  background: #e4f5ed;
  border-color: #a7e1c8;
  color: #0b7557;
}

.verdict-banner.unmatched {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #dc2626;
}

.score-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  text-align: center;
}

.score-num {
  font-size: 26px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  line-height: 1.1;
  font-family: var(--font-mono, monospace);
}

.score-label {
  font-size: 11px;
  color: var(--muted, #64716d);
  margin-top: 4px;
}

.result-metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
}

.span-full {
  grid-column: span 2;
}

.metric-label {
  font-size: 10.5px;
  color: var(--muted, #64716d);
}

.metric-val {
  font-size: 11.5px;
  color: var(--graphite, #17211f);
}

.input-summary-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
}

.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
}

.summary-label {
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.summary-val {
  color: var(--muted, #64716d);
}

.result-empty-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 220px;
  color: var(--muted, #64716d);
  font-size: 11.5px;
  flex: 1;
}

.panel-footer {
  margin-top: 14px;
}

.compare-btn {
  width: 100%;
  height: 30px;
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

/* 底部契约栏 */
.contract-strip {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 14px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  font-size: 11.5px;
  flex-wrap: wrap;
}

.contract-icon {
  color: var(--primary, #0ea5e9);
}

.contract-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.contract-label {
  color: var(--graphite, #17211f);
}

.contract-note {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 10.5px;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .compare-layout {
    grid-template-columns: 1fr;
  }
  .compare-sources {
    grid-template-columns: 1fr;
  }
  .contract-note {
    margin-left: 0;
    width: 100%;
  }
}
</style>
