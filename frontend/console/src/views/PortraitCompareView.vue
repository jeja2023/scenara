<script setup lang="ts">
import {
  CheckCircle2,
  FileImage,
  Layers,
  RotateCcw,
  ScanFace,
  ShieldCheck,
  Upload,
  UserCheck,
  X,
  XCircle,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import {
  api,
  apiBlob,
  apiForm,
  blobToDataUrl,
  revokeBlobUrl,
  userFacingError,
} from "../api";
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
  if (result.value.matched === true) return "同一人判定通过 (Match)";
  if (result.value.matched === false) return "未达阈值 (No Match)";
  return "无阈值判定";
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
  if (!value) return "未提取特征";
  return `${value.face_count} 张人脸 · 选中第 ${value.selected_face_index + 1} 人脸 · ${value.embedding_dimension} 维特征`;
}

async function compare(): Promise<void> {
  clearFeedback();
  result.value = null;
  if (!hasLeft.value || !hasRight.value) {
    error.value = "请为左右两侧各选择一张人像图片";
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
      error.value = "请为左右两侧各选择一张人像图片";
      return;
    }
    result.value = data;
    contract.featureSpaceId = data.feature_space_id;
    contract.model = data.left
      ? `${data.left.model_id} (v${data.left.model_version})`
      : "已按索引契约完成比对";
    message.value = "人像特征 1:1 比对完成，判定报告已就绪";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "人像比对失败，请检查图片清晰度与算法服务状态",
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
    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-if="message" class="success-banner">{{ message }}</p>

    <!-- 1. 顶部数据统计卡片 -->
    <section class="stats">
      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">比对工作模式</span>
          <div class="stat-icon-badge">
            <UserCheck :size="15" />
          </div>
        </div>
        <strong class="stat-value">
          {{
            result
              ? result.mode === "image"
                ? "本地图片 1:1"
                : result.mode === "asset"
                  ? "资产库 1:1"
                  : "混合输入 1:1"
              : "1:1 人像比对"
          }}
        </strong>
        <small class="stat-desc">高维生物特征余弦相似度核验</small>
      </article>

      <article
        class="stat"
        :class="
          result
            ? result.matched === true
              ? 'green'
              : result.matched === false
                ? 'amber'
                : 'teal'
            : 'teal'
        "
      >
        <div class="stat-top-row">
          <span class="stat-title">判定结论</span>
          <div class="stat-icon-badge">
            <CheckCircle2 v-if="result?.matched === true" :size="15" />
            <XCircle v-else-if="result?.matched === false" :size="15" />
            <ScanFace v-else :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ verdictLabel }}</strong>
        <small class="stat-desc">{{
          result ? `阈值: ${result.threshold ?? threshold}` : "等待两侧人像输入"
        }}</small>
      </article>

      <article class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">相似度得分</span>
          <div class="stat-icon-badge">
            <Layers :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{
          result ? `${(result.score * 100).toFixed(2)}%` : "-"
        }}</strong>
        <small class="stat-desc">{{
          result
            ? `特征欧氏距离 ${result.distance.toFixed(4)}`
            : "余弦相似度 [-1.0 ~ 1.0]"
        }}</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">图片资产库</span>
          <div class="stat-icon-badge">
            <FileImage :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ imageAssets.length }} 张</strong>
        <small class="stat-desc">支持从已入库数据资产直接选取</small>
      </article>
    </section>

    <!-- 2. 顶部工具栏 -->
    <div class="filter-controls">
      <div class="filter-left">
        <div class="filter-item">
          <span class="filter-label">判定阈值:</span>
          <input
            v-model="threshold"
            type="number"
            min="-1"
            max="1"
            step="0.01"
            class="filter-input threshold-input mono"
          />
        </div>

        <div class="quick-pills">
          <button
            type="button"
            class="quick-pill"
            :class="{ selected: threshold === '0.70' }"
            @click="threshold = '0.70'"
          >
            0.70 (宽松)
          </button>
          <button
            type="button"
            class="quick-pill"
            :class="{ selected: threshold === '0.80' }"
            @click="threshold = '0.80'"
          >
            0.80 (标准)
          </button>
          <button
            type="button"
            class="quick-pill"
            :class="{ selected: threshold === '0.85' }"
            @click="threshold = '0.85'"
          >
            0.85 (严格)
          </button>
        </div>
      </div>

      <div class="filter-right">
        <button class="button secondary tiny-btn" @click="resetAll">
          <RotateCcw :size="12" />
          <span>重置对比</span>
        </button>
        <button
          class="button primary tiny-btn compare-main-btn"
          :disabled="comparing || !hasLeft || !hasRight"
          @click="compare"
        >
          <ScanFace :size="13" />
          <span>{{ comparing ? "特征提取与比对中…" : "开始 1:1 比对" }}</span>
        </button>
      </div>
    </div>

    <!-- 3. 双栏人像比对工作台 -->
    <div class="compare-arena-layout">
      <!-- 左右输入源卡片 -->
      <div class="compare-sources-grid">
        <!-- 输入源 A -->
        <article class="panel source-panel">
          <div class="panel-header">
            <div class="header-left">
              <span class="badge source-tag tag-a">源 A</span>
              <h3>待核验人像 (Subject A)</h3>
            </div>
            <button
              v-if="hasLeft"
              class="icon-button close-btn"
              title="清除输入 A"
              @click="clearSide('left')"
            >
              <X :size="13" />
            </button>
          </div>

          <div class="source-preview-box">
            <img
              v-if="leftPreview"
              :src="leftPreview"
              alt="人像 A 预览"
              class="preview-img"
            />
            <div v-else class="source-empty-state">
              <ScanFace :size="36" class="empty-scan-icon" />
              <p>请选择或上传待核验人像</p>
            </div>
          </div>

          <div class="source-actions-bar">
            <label class="button secondary tiny-btn upload-btn">
              <Upload :size="12" />本地上传
              <input
                type="file"
                accept="image/*"
                class="hidden-file-input"
                @change="setFile('left', $event)"
              />
            </label>

            <select
              :value="leftAssetId"
              class="field-select"
              @change="
                setAsset('left', ($event.target as HTMLSelectElement).value)
              "
            >
              <option value="">从数据资产库选择...</option>
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

        <!-- 输入源 B -->
        <article class="panel source-panel">
          <div class="panel-header">
            <div class="header-left">
              <span class="badge source-tag tag-b">源 B</span>
              <h3>参照标准人像 (Subject B)</h3>
            </div>
            <button
              v-if="hasRight"
              class="icon-button close-btn"
              title="清除输入 B"
              @click="clearSide('right')"
            >
              <X :size="13" />
            </button>
          </div>

          <div class="source-preview-box">
            <img
              v-if="rightPreview"
              :src="rightPreview"
              alt="人像 B 预览"
              class="preview-img"
            />
            <div v-else class="source-empty-state">
              <ScanFace :size="36" class="empty-scan-icon" />
              <p>请选择或上传参照标准人像</p>
            </div>
          </div>

          <div class="source-actions-bar">
            <label class="button secondary tiny-btn upload-btn">
              <Upload :size="12" />本地上传
              <input
                type="file"
                accept="image/*"
                class="hidden-file-input"
                @change="setFile('right', $event)"
              />
            </label>

            <select
              :value="rightAssetId"
              class="field-select"
              @change="
                setAsset('right', ($event.target as HTMLSelectElement).value)
              "
            >
              <option value="">从数据资产库选择...</option>
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

      <!-- 右侧：比对结论与特征分析面板 -->
      <aside class="panel compare-result-panel">
        <div class="panel-header">
          <div class="header-left">
            <ShieldCheck :size="14" class="header-icon" />
            <h3>1:1 研判结果报告</h3>
          </div>
          <span v-if="result" class="badge status-badge active">
            {{
              result.mode === "asset"
                ? "资产比对"
                : result.mode === "mixed"
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
            <CheckCircle2 v-if="result.matched === true" :size="22" />
            <XCircle v-else-if="result.matched === false" :size="22" />
            <ScanFace v-else :size="22" />
            <div class="verdict-text-box">
              <strong>{{ verdictLabel }}</strong>
              <small>{{
                result.matched === true
                  ? "双侧人脸生物特征达到同人判定阈值"
                  : "双侧特征余弦相似度未达到判定标准"
              }}</small>
            </div>
          </div>

          <div class="score-card">
            <span class="score-num"
              >{{ (result.score * 100).toFixed(2) }}%</span
            >
            <span class="score-label"
              >余弦相似度分数 ({{ result.score.toFixed(4) }})</span
            >
            <div class="score-progress-bar">
              <div
                class="score-progress-fill"
                :style="{
                  width: `${Math.max(0, Math.min(100, result.score * 100))}%`,
                }"
              />
            </div>
          </div>

          <div class="result-metrics-grid">
            <div class="metric-item">
              <span class="metric-label">特征欧氏距离</span>
              <strong class="metric-val mono">{{
                result.distance.toFixed(4)
              }}</strong>
            </div>
            <div class="metric-item">
              <span class="metric-label">判定阈值</span>
              <strong class="metric-val mono">{{
                result.threshold?.toFixed(2) ?? threshold
              }}</strong>
            </div>
            <div class="metric-item span-full">
              <span class="metric-label">特征空间契约</span>
              <strong class="metric-val mono accent-text">{{
                result.feature_space_id
              }}</strong>
            </div>
          </div>

          <div class="input-summary-box">
            <div class="summary-row">
              <span class="summary-label">输入源 A:</span>
              <span class="summary-val">{{ summaryLabel(result.left) }}</span>
            </div>
            <div class="summary-row">
              <span class="summary-label">输入源 B:</span>
              <span class="summary-val">{{ summaryLabel(result.right) }}</span>
            </div>
          </div>
        </div>

        <div v-else class="result-empty-box">
          <ScanFace :size="40" class="empty-icon" />
          <p>在左侧选择两侧人像图片后，点击「开始 1:1 比对」查看高维特征报告</p>
        </div>
      </aside>
    </div>

    <!-- 4. 底部索引契约与安全摘要 -->
    <div class="contract-strip">
      <FileImage :size="14" class="contract-icon" />
      <div class="contract-item">
        <strong class="contract-label">索引契约：</strong>
        <span class="mono">{{ contract.featureSpaceId }}</span>
      </div>
      <div class="contract-item">
        <strong class="contract-label">模型版本：</strong>
        <span>{{ contract.model }}</span>
      </div>
      <div class="contract-note">
        原始人脸生物特征仅在内存中进行安全计算，平台严禁持久化未脱敏原始特征向量。
      </div>
    </div>
  </section>
</template>

<style scoped>
.portrait-compare-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.error-banner {
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

.success-banner {
  padding: 8px 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

/* 顶部统计卡片 */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 2px;
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat {
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  transition: all 0.15s ease;
}

.stat:hover {
  transform: translateY(-1px);
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.04);
}

.stat-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.stat-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.stat-icon-badge {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat.teal .stat-icon-badge {
  background: #f0fdfa;
  color: var(--color-accent, #087682);
  border: 1px solid #ccfbf1;
}

.stat.green .stat-icon-badge {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #dcfce7;
}

.stat.amber .stat-icon-badge {
  background: #fffbeb;
  color: #d97706;
  border: 1px solid #fef3c7;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  line-height: 1.2;
  margin: 2px 0 1px;
}

.stat-desc {
  font-size: 10.5px;
  color: #8c9b97;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 过滤控制栏 */
.filter-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 6px 12px;
  flex-wrap: wrap;
}

.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--muted, #64716d);
}

.filter-label {
  font-weight: 500;
  white-space: nowrap;
}

.threshold-input {
  width: 70px;
  height: 28px;
  padding: 0 6px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  text-align: center;
}
.threshold-input:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.quick-pills {
  display: flex;
  align-items: center;
  gap: 4px;
}

.quick-pill {
  padding: 3px 8px;
  font-size: 11px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  cursor: pointer;
  transition: all 0.15s ease;
}
.quick-pill:hover {
  background: #ffffff;
}
.quick-pill.selected {
  background: var(--color-accent-soft, #e4f1f1);
  color: var(--color-accent-hover, #065e67);
  border-color: var(--color-accent, #087682);
  font-weight: 600;
}

/* 比对工作台结构 */
.compare-arena-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
  gap: 12px;
  align-items: start;
}

@media (max-width: 950px) {
  .compare-arena-layout {
    grid-template-columns: 1fr;
  }
}

.compare-sources-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

@media (max-width: 600px) {
  .compare-sources-grid {
    grid-template-columns: 1fr;
  }
}

/* 面板通用 */
.panel {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.header-icon {
  color: var(--color-accent, #087682);
}

.panel-header h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.source-tag {
  font-size: 10.5px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 700;
}
.source-tag.tag-a {
  background: #e0f2fe;
  color: #0369a1;
}
.source-tag.tag-b {
  background: #fef3c7;
  color: #92400e;
}

.source-preview-box {
  height: 240px;
  background: #fafbfb;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  overflow: hidden;
  border-bottom: 1px solid var(--line, #e2e8e6);
}

.preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.source-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--muted, #64716d);
  font-size: 11.5px;
}

.empty-scan-icon {
  color: #b7c2bd;
}

.source-actions-bar {
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #ffffff;
}

.upload-btn {
  position: relative;
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
}

.hidden-file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.field-select {
  flex: 1;
  height: 28px;
  padding: 0 6px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  cursor: pointer;
  min-width: 0;
}
.field-select:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

/* 比对结果卡片 */
.compare-result-panel {
  display: flex;
  flex-direction: column;
}

.result-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.verdict-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #e2e8e6;
  background: #fafbfb;
}

.verdict-banner.matched {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.verdict-banner.unmatched {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

.verdict-text-box strong {
  display: block;
  font-size: 13px;
}

.verdict-text-box small {
  font-size: 10.5px;
  opacity: 0.85;
}

.score-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  gap: 4px;
}

.score-num {
  font-size: 26px;
  font-weight: 800;
  color: var(--color-accent-hover, #065e67);
  font-family: var(--font-mono, monospace);
  line-height: 1;
}

.score-label {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.score-progress-bar {
  width: 100%;
  height: 6px;
  background: #e2e8e6;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 4px;
}

.score-progress-fill {
  height: 100%;
  background: var(--color-accent, #087682);
  transition: width 0.3s ease;
}

.result-metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
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

.metric-item.span-full {
  grid-column: span 2;
}

.metric-label {
  font-size: 10px;
  color: var(--muted, #64716d);
}

.metric-val {
  font-size: 11.5px;
  color: var(--graphite, #17211f);
}

.accent-text {
  color: var(--color-accent-hover, #065e67);
}

.input-summary-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  font-size: 10.5px;
}

.summary-row {
  display: flex;
  gap: 6px;
}

.summary-label {
  color: var(--muted, #64716d);
  flex-shrink: 0;
}

.summary-val {
  color: var(--graphite, #17211f);
}

.result-empty-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  gap: 8px;
  color: var(--muted, #64716d);
  text-align: center;
}

.result-empty-box p {
  margin: 0;
  font-size: 11.5px;
  max-width: 240px;
  line-height: 1.4;
}

.empty-icon {
  color: #b7c2bd;
}

/* 底部契约栏 */
.contract-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  font-size: 11px;
  color: var(--graphite, #17211f);
  flex-wrap: wrap;
}

.contract-icon {
  color: var(--color-accent, #087682);
}

.contract-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.contract-label {
  color: var(--muted, #64716d);
}

.contract-note {
  margin-left: auto;
  font-size: 10.5px;
  color: #8c9b97;
}

.mono {
  font-family: var(--font-mono, monospace);
}

.close-btn {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  cursor: pointer;
  border-radius: 3px;
}
.close-btn:hover {
  background: #f1f5f4;
  color: #dc2626;
}
</style>
