<script setup lang="ts">
import {
  Bookmark,
  Clock,
  ExternalLink,
  Eye,
  FileSearch,
  FileText,
  Image as ImageIcon,
  Layers,
  Loader2,
  Maximize2,
  RotateCcw,
  ScanFace,
  Search as SearchIcon,
  Trash2,
  Upload,
  UserRound,
  Video,
  X,
} from "@lucide/vue";

import { computed, ref, watch } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { useRouter } from "vue-router";

import {
  api,
  apiBlob,
  apiForm,
  apiImageDataUrl,
  blobToDataUrl,
  revokeBlobUrl,
  userFacingError,
} from "../api";
import ResultDetailDrawer from "../components/ResultDetailDrawer.vue";
import { labelDomain, labelMediaKind } from "../labels";
import type { MediaAsset, MediaKind, SavedSearch } from "../types";

type SearchMode = "text" | "portrait";

interface SearchHit {
  record_id: string;
  index_id: string;
  domain: string;
  source: Record<string, unknown>;
  score?: number | null;
  distance?: number | null;
  text_snippet?: string | null;
  metadata: Record<string, unknown>;
  media_kind?: MediaKind | null;
  resource_name?: string | null;
}

interface SearchResponse {
  search_id: string;
  mode: SearchMode;
  query?: string | null;
  feature_space_id?: string | null;
  query_summary?: {
    face_count: number;
    selected_face_index: number;
    quality_score?: number | null;
    feature_space_id: string;
    model_id: string;
    model_version: string;
    embedding_dimension: number;
    fallback: boolean;
  } | null;
  hits: SearchHit[];
  total: number;
  searched_indexes: string[];
}

const router = useRouter();
const mode = ref<SearchMode>("text");
const query = ref("");
const file = ref<File | null>(null);
const assets = ref<MediaAsset[]>([]);
const assetId = ref("");
const preview = ref("");
const mediaKinds = ref<MediaKind[]>([]);
const threshold = ref("0.80");
const loading = ref(false);
const error = ref("");
const response = ref<SearchResponse | null>(null);
const savedSearches = ref<SavedSearch[]>([]);
const savedName = ref("");

// 图像缩略图缓存与大图/抽屉状态
const hitThumbnails = ref<Record<string, string>>({});
const loadingThumbnails = ref<Record<string, boolean>>({});
const lightboxHit = ref<SearchHit | null>(null);
const drawerOpen = ref(false);
const drawerRunId = ref<string | null>(null);

const imageAssets = computed(() =>
  assets.value.filter((asset) => asset.kind === "image"),
);
const hasQuery = computed(() =>
  mode.value === "text"
    ? Boolean(query.value.trim())
    : Boolean(file.value || assetId.value),
);

async function loadAssets(): Promise<void> {
  try {
    const page = await api<{ items: MediaAsset[] }>(
      "/api/v1/media/assets?limit=200",
    );
    assets.value = page.items;
  } catch {
    assets.value = [];
  }
}

async function loadSavedSearches(): Promise<void> {
  try {
    const page = await api<{ items: SavedSearch[] }>(
      "/api/v1/search/saved?limit=100",
    );
    savedSearches.value = page.items;
  } catch {
    savedSearches.value = [];
  }
}

function toggleMediaKind(value: MediaKind): void {
  mediaKinds.value = mediaKinds.value.includes(value)
    ? mediaKinds.value.filter((item) => item !== value)
    : [...mediaKinds.value, value];
}

function setFile(event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
  if (!selected) return;
  if (!selected.type.startsWith("image/")) {
    error.value = "请选择图片文件";
    return;
  }
  error.value = "";
  file.value = selected;
  assetId.value = "";
  revokeBlobUrl(preview.value);
  preview.value = URL.createObjectURL(selected);
}

async function setAsset(value: string): Promise<void> {
  assetId.value = value;
  if (!value) {
    revokeBlobUrl(preview.value);
    preview.value = "";
    return;
  }
  file.value = null;
  try {
    revokeBlobUrl(preview.value);
    preview.value = await blobToDataUrl(
      await apiBlob(
        `/api/v1/media/assets/${encodeURIComponent(value)}/preview`,
      ),
    );
  } catch (caught) {
    error.value = userFacingError(caught, "资产预览加载失败");
  }
}

function clearFile(): void {
  file.value = null;
  assetId.value = "";
  revokeBlobUrl(preview.value);
  preview.value = "";
}

function setMode(next: SearchMode): void {
  mode.value = next;
  response.value = null;
  error.value = "";
}

function hitImagePath(hit: SearchHit): string | null {
  const runId = typeof hit.source.run_id === "string" ? hit.source.run_id : "";
  const artifactId =
    typeof hit.source.artifact_id === "string" ? hit.source.artifact_id : "";
  const assetIdVal =
    typeof hit.source.asset_id === "string" ? hit.source.asset_id : "";

  if (runId && artifactId) {
    return `/api/v1/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
  }
  if (assetIdVal && hit.media_kind === "image") {
    return `/api/v1/assets/${encodeURIComponent(assetIdVal)}/content`;
  }
  return null;
}

async function fetchThumbnail(hit: SearchHit): Promise<void> {
  const path = hitImagePath(hit);
  if (
    !path ||
    hitThumbnails.value[hit.record_id] ||
    loadingThumbnails.value[hit.record_id]
  )
    return;
  loadingThumbnails.value[hit.record_id] = true;
  try {
    const url = await apiImageDataUrl(path);
    if (url) {
      hitThumbnails.value[hit.record_id] = url;
    }
  } catch {
    // 忽略加载失败，回退到图标
  } finally {
    loadingThumbnails.value[hit.record_id] = false;
  }
}

watch(
  () => response.value?.hits,
  (hits) => {
    if (hits?.length) {
      for (const hit of hits) {
        void fetchThumbnail(hit);
      }
    }
  },
  { immediate: true },
);

async function runSearch(): Promise<void> {
  if (!hasQuery.value) {
    error.value =
      mode.value === "text" ? "请输入要检索的文字" : "请选择一张查询图片";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    if (mode.value === "text") {
      response.value = await api<SearchResponse>("/api/v1/search/text", {
        method: "POST",
        body: JSON.stringify({
          query: query.value.trim(),
          media_kinds: mediaKinds.value,
          limit: 50,
        }),
      });
    } else if (assetId.value) {
      const cutoff = Number(threshold.value);
      response.value = await api<SearchResponse>("/api/v1/search/asset", {
        method: "POST",
        body: JSON.stringify({
          asset_id: assetId.value,
          media_kinds: mediaKinds.value,
          limit: 50,
          threshold: Number.isFinite(cutoff) ? cutoff : null,
        }),
      });
    } else {
      const form = new FormData();
      form.append("file", file.value as File);
      form.append("media_kinds", mediaKinds.value.join(","));
      const cutoff = Number(threshold.value);
      if (Number.isFinite(cutoff)) form.append("threshold", String(cutoff));
      response.value = await apiForm<SearchResponse>(
        "/api/v1/search/image",
        form,
      );
    }
  } catch (caught) {
    error.value = userFacingError(caught, "检索失败，请检查索引和输入内容");
  } finally {
    loading.value = false;
  }
}

function savedDefinition(): Record<string, unknown> | null {
  if (mode.value === "text" && query.value.trim()) {
    return {
      query: query.value.trim(),
      media_kinds: mediaKinds.value,
      limit: 50,
    };
  }
  if (mode.value === "portrait" && assetId.value) {
    const cutoff = Number(threshold.value);
    return {
      asset_id: assetId.value,
      media_kinds: mediaKinds.value,
      limit: 50,
      threshold: Number.isFinite(cutoff) ? cutoff : null,
    };
  }
  return null;
}

async function saveSearch(): Promise<void> {
  const definition = savedDefinition();
  if (!definition || !savedName.value.trim()) {
    error.value = "请先完成可复用的查询条件并填写名称";
    return;
  }
  try {
    await api<SavedSearch>("/api/v1/search/saved", {
      method: "POST",
      body: JSON.stringify({
        name: savedName.value.trim(),
        mode: mode.value,
        definition,
      }),
    });
    savedName.value = "";
    await loadSavedSearches();
  } catch (caught) {
    error.value = userFacingError(caught, "保存检索失败");
  }
}

async function runSavedSearch(item: SavedSearch): Promise<void> {
  try {
    response.value = await api<SearchResponse>(
      `/api/v1/search/saved/${encodeURIComponent(item.saved_search_id)}/run`,
      { method: "POST" },
    );
    mode.value = item.mode;
  } catch (caught) {
    error.value = userFacingError(caught, "执行保存检索失败");
  }
}

async function deleteSavedSearch(item: SavedSearch): Promise<void> {
  try {
    await api<void>(
      `/api/v1/search/saved/${encodeURIComponent(item.saved_search_id)}`,
      { method: "DELETE" },
    );
    await loadSavedSearches();
  } catch (caught) {
    error.value = userFacingError(caught, "删除保存检索失败");
  }
}

void Promise.all([loadAssets(), loadSavedSearches()]);

function openHitDetail(hit: SearchHit): void {
  const runId = typeof hit.source.run_id === "string" ? hit.source.run_id : "";
  if (runId) {
    drawerRunId.value = runId;
    drawerOpen.value = true;
  } else {
    lightboxHit.value = hit;
  }
}

function navigateToResults(hit: SearchHit): void {
  const runId = typeof hit.source.run_id === "string" ? hit.source.run_id : "";
  if (!runId) return;
  const unitId =
    typeof hit.source.unit_id === "string" ? hit.source.unit_id : "";
  void router.push({
    path: "/results",
    query: unitId ? { run: runId, unit: unitId } : { run: runId },
  });
}

function hitTitle(hit: SearchHit): string {
  return (
    hit.resource_name ||
    String(
      hit.source.asset_id ||
        hit.source.source_id ||
        hit.source.run_id ||
        hit.record_id,
    )
  );
}

function hitIcon(hit: SearchHit): typeof FileText {
  if (hit.media_kind === "video" || hit.media_kind === "stream") return Video;
  if (hit.domain === "portrait") return UserRound;
  return FileText;
}

function scoreLabel(hit: SearchHit): string {
  if (hit.score == null) return "文本匹配";
  return `相似度 ${(hit.score * 100).toFixed(1)}% (${hit.score.toFixed(4)})`;
}

function formatPts(ptsMs: unknown): string {
  if (typeof ptsMs !== "number" || Number.isNaN(ptsMs)) return "";
  const totalSeconds = Math.floor(ptsMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const ms = Math.floor(ptsMs % 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}

useRefresh(runSearch);
</script>

<template>
  <section class="page search-page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel search-controls">
      <div class="panel-header">
        <div>
          <h2>智能多模态检索</h2>
          <p>支持文字检索图像/视频，或选择人像特征检索相似目标。</p>
        </div>
      </div>
      <div class="panel-body search-panel-body">
        <div class="mode-tabs" role="tablist" aria-label="检索方式">
          <button
            class="mode-tab-btn"
            :class="{ active: mode === 'text' }"
            @click="setMode('text')"
          >
            <SearchIcon :size="15" />文搜图 / 文搜视频
          </button>
          <button
            class="mode-tab-btn"
            :class="{ active: mode === 'portrait' }"
            @click="setMode('portrait')"
          >
            <ScanFace :size="15" />人搜图
          </button>
        </div>

        <div class="search-form-section">
          <!-- 1. 文搜图 / 文搜视频 检索行 -->
          <div v-if="mode === 'text'" class="text-search-box">
            <div class="text-query-bar">
              <SearchIcon :size="17" class="text-search-icon" />
              <input
                v-model.trim="query"
                type="search"
                class="text-search-input"
                placeholder="输入文字关键词，例如：红色车辆、安全帽、园区东门人员、合同"
                @keyup.enter="runSearch"
              />
              <button
                v-if="query"
                class="query-clear-icon-btn"
                title="清空文字"
                @click="query = ''"
              >
                <X :size="14" />
              </button>
            </div>
          </div>

          <!-- 2. 人搜图 优雅多源输入卡片 -->
          <div v-else class="portrait-query-card">
            <!-- 左侧：图像缩略图预览 / 空状态 -->
            <div
              class="portrait-preview-box"
              :class="{ 'has-preview': preview }"
            >
              <template v-if="preview">
                <img :src="preview" alt="查询图片预览" class="preview-img" />
                <button
                  class="preview-clear-btn"
                  title="清除已选图片"
                  aria-label="清除图片"
                  @click="clearFile"
                >
                  <X :size="11" />
                </button>
              </template>
              <div v-else class="preview-placeholder">
                <ScanFace :size="24" class="preview-scan-icon" />
                <span class="preview-tip">人像特征</span>
              </div>
            </div>

            <!-- 中间：上传本地图片 + 从资产库选择 -->
            <div class="portrait-inputs-area">
              <div class="portrait-source-bar">
                <label class="button secondary portrait-upload-btn">
                  <Upload :size="14" />
                  <span>上传本地图片</span>
                  <input
                    type="file"
                    accept="image/*"
                    aria-label="上传本地查询图片"
                    @change="setFile"
                  />
                </label>

                <span class="portrait-source-sep">或</span>

                <div class="portrait-asset-dropdown">
                  <ImageIcon :size="14" class="asset-select-icon" />
                  <select
                    :value="assetId"
                    class="portrait-asset-select"
                    aria-label="从图片资产库选择查询图片"
                    @change="
                      setAsset(($event.target as HTMLSelectElement).value)
                    "
                  >
                    <option value="">
                      从图片资产库选择 (共 {{ imageAssets.length }} 张图片)
                    </option>
                    <option
                      v-for="asset in imageAssets"
                      :key="asset.asset_id"
                      :value="asset.asset_id"
                    >
                      {{ asset.filename || asset.asset_id }}
                    </option>
                  </select>
                </div>

                <button
                  v-if="file || assetId"
                  class="button secondary portrait-clear-btn"
                  title="重置已选图片"
                  @click="clearFile"
                >
                  <RotateCcw :size="12" />
                  <span>重置</span>
                </button>
              </div>

              <!-- 当前所选源状态提示 -->
              <div class="portrait-status-hint">
                <template v-if="file">
                  <span class="status-badge local">本地文件</span>
                  <span class="status-text"
                    >{{ file.name }} ({{
                      (file.size / 1024).toFixed(1)
                    }}
                    KB)</span
                  >
                </template>
                <template v-else-if="assetId">
                  <span class="status-badge asset">资产库图片</span>
                  <span class="status-text">{{
                    imageAssets.find((a) => a.asset_id === assetId)?.filename ||
                    assetId
                  }}</span>
                </template>
                <template v-else>
                  <span class="status-hint-muted"
                    >请上传一张包含清晰人脸或人体的照片，系统将提取特征向量进行全库多模态向量比对。</span
                  >
                </template>
              </div>
            </div>

            <!-- 右侧：相似度阈值控件 -->
            <div class="portrait-threshold-box">
              <div class="threshold-header">
                <span class="threshold-title">相似度阈值</span>
                <span class="threshold-hint">[-1 ~ 1]</span>
              </div>
              <div class="threshold-input-group">
                <input
                  v-model="threshold"
                  type="number"
                  min="-1"
                  max="1"
                  step="0.01"
                  class="threshold-field"
                  aria-label="相似度阈值"
                />
              </div>
            </div>
          </div>

          <!-- 3. 数据类型过滤与检索发起栏 -->
          <div class="filter-row">
            <div class="filter-group">
              <span class="filter-label">限定数据类型</span>
              <div class="filter-chips">
                <button
                  v-for="kind in [
                    'image',
                    'video',
                    'document',
                    'stream',
                  ] as MediaKind[]"
                  :key="kind"
                  class="filter-chip"
                  :class="{ active: mediaKinds.includes(kind) }"
                  @click="toggleMediaKind(kind)"
                >
                  <span class="chip-dot" />
                  {{
                    kind === "image"
                      ? "图片"
                      : kind === "video"
                        ? "视频"
                        : kind === "document"
                          ? "文档"
                          : "视频流"
                  }}
                </button>
              </div>
            </div>
            <button
              class="button primary search-submit"
              :disabled="loading || !hasQuery"
              @click="runSearch"
            >
              <SearchIcon :size="15" :class="{ spin: loading }" />
              <span>{{ loading ? "正在检索..." : "开始检索" }}</span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="panel saved-panel">
      <div class="panel-header">
        <div>
          <h2>保存检索</h2>
          <p>把常用的文字或人像资产查询保存下来，下一次直接执行。</p>
        </div>
        <span class="badge">{{ savedSearches.length }} 个</span>
      </div>
      <div class="saved-create">
        <input
          v-model.trim="savedName"
          placeholder="保存名称，例如：园区东门人员"
          @keyup.enter="saveSearch"
        /><button
          class="button secondary"
          :disabled="!savedDefinition() || !savedName.trim()"
          @click="saveSearch"
        >
          <Bookmark :size="15" />保存当前检索
        </button>
      </div>
      <div class="saved-list">
        <div
          v-for="item in savedSearches"
          :key="item.saved_search_id"
          class="saved-item"
        >
          <span
            ><strong>{{ item.name }}</strong
            ><small
              >{{ item.mode === "text" ? "文字检索" : "人像资产检索" }} ·
              {{ item.last_run_at ? "最近已执行" : "尚未执行" }}</small
            ></span
          ><span class="saved-actions"
            ><button
              class="icon-button"
              title="执行保存检索"
              @click="runSavedSearch(item)"
            >
              <SearchIcon :size="16" /></button
            ><button
              class="icon-button"
              title="删除保存检索"
              @click="deleteSavedSearch(item)"
            >
              <Trash2 :size="16" /></button
          ></span>
        </div>
        <div v-if="!savedSearches.length" class="saved-empty">
          还没有保存的检索
        </div>
      </div>
    </section>

    <!-- 检索结果面板 -->
    <section class="panel result-panel">
      <div class="panel-header">
        <div>
          <h2>检索结果</h2>
          <p v-if="response">
            {{ response.total }} 条命中 ·
            {{ response.searched_indexes.length }} 个索引
          </p>
          <p v-else>执行一次检索后显示命中内容</p>
        </div>
        <span v-if="response?.query_summary" class="badge"
          >{{ response.query_summary.embedding_dimension }} 维特征</span
        >
      </div>
      <div v-if="response?.query_summary" class="query-summary">
        <UserRound :size="17" /><span
          >检测到 {{ response.query_summary.face_count }} 张人脸，使用
          {{ response.query_summary.model_id }} ·
          {{ response.query_summary.model_version }} 查询</span
        >
      </div>

      <!-- 命中列表展示 -->
      <div v-if="response?.hits.length" class="hit-list">
        <div
          v-for="hit in response.hits"
          :key="hit.record_id"
          class="hit-card"
          @click="openHitDetail(hit)"
        >
          <!-- 缩略图与快速放大 -->
          <div
            class="hit-thumbnail-box"
            :title="
              hitThumbnails[hit.record_id]
                ? '点击查看原图大图'
                : '无预览图像'
            "
            @click.stop="
              hitThumbnails[hit.record_id]
                ? (lightboxHit = hit)
                : openHitDetail(hit)
            "
          >
            <img
              v-if="hitThumbnails[hit.record_id]"
              :src="hitThumbnails[hit.record_id]"
              alt="命中预览"
              class="hit-thumbnail-img"
            />
            <span
              v-else-if="loadingThumbnails[hit.record_id]"
              class="hit-thumbnail-loading"
            >
              <Loader2 :size="18" class="spin" />
            </span>
            <span v-else class="hit-fallback-icon">
              <component :is="hitIcon(hit)" :size="22" />
            </span>
            <div
              v-if="hitThumbnails[hit.record_id]"
              class="thumbnail-zoom-hint"
            >
              <Eye :size="14" />
            </div>
          </div>

          <!-- 主信息区域 -->
          <div class="hit-main-info">
            <div class="hit-header-row">
              <strong class="hit-title">{{ hitTitle(hit) }}</strong>
              <div class="hit-badges">
                <span
                  class="hit-badge"
                  :class="{
                    portrait: hit.domain === 'portrait',
                    ocr: hit.domain === 'ocr',
                  }"
                >
                  {{ labelDomain(hit.domain) }}
                </span>
                <span class="hit-badge media-kind">
                  {{ labelMediaKind(hit.media_kind || "") }}
                </span>
                <span v-if="hit.score != null" class="hit-badge score">
                  {{ scoreLabel(hit) }}
                </span>
                <span
                  v-if="hit.source.pts_ms != null"
                  class="hit-badge timestamp"
                  title="视频时间戳"
                >
                  <Clock :size="11" />
                  {{ formatPts(hit.source.pts_ms) }} ({{
                    hit.source.pts_ms
                  }}ms)
                </span>
                <span
                  v-if="hit.source.page_number != null"
                  class="hit-badge page"
                >
                  第 {{ hit.source.page_number }} 页
                </span>
              </div>
            </div>

            <!-- 文字片段或详细描述 -->
            <p v-if="hit.text_snippet" class="hit-snippet">
              {{ hit.text_snippet }}
            </p>

            <!-- 来源定位 -->
            <div class="hit-source-location">
              <span v-if="hit.source.run_id" class="loc-item"
                >任务: {{ hit.source.run_id }}</span
              >
              <span v-if="hit.source.unit_id" class="loc-item"
                >单元: {{ hit.source.unit_id }}</span
              >
              <span v-if="hit.source.object_id" class="loc-item"
                >目标: {{ hit.source.object_id }}</span
              >
              <span v-if="hit.source.artifact_id" class="loc-item"
                >产物: {{ hit.source.artifact_id }}</span
              >
            </div>
          </div>

          <!-- 操作按钮组 -->
          <div class="hit-action-group" @click.stop>
            <button
              v-if="hitThumbnails[hit.record_id]"
              class="button secondary hit-action-btn"
              title="全屏查看原图/裁剪图"
              @click="lightboxHit = hit"
            >
              <Maximize2 :size="13" />
              <span>查看大图</span>
            </button>
            <button
              v-if="hit.source.run_id"
              class="button secondary hit-action-btn"
              title="在抽屉中查看结构化结果详情"
              @click="openHitDetail(hit)"
            >
              <Layers :size="13" />
              <span>结果详情</span>
            </button>
            <button
              v-if="hit.source.run_id"
              class="button primary hit-action-btn"
              title="跳转至完整结果工作台"
              @click="navigateToResults(hit)"
            >
              <ExternalLink :size="13" />
              <span>跳转结果页</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 空状态提示 -->
      <div v-else class="empty search-empty">
        <FileSearch :size="30" /><strong>{{
          response ? "没有符合条件的结果" : "等待检索"
        }}</strong
        ><span>{{
          response
            ? "可以调整文字、数据类型或相似度阈值后重试。"
            : "检索结果会按分数和来源位置排序。"
        }}</span>
      </div>
    </section>

    <!-- 1. 结构化结果抽屉 -->
    <ResultDetailDrawer
      :open="drawerOpen"
      :run-id="drawerRunId"
      @close="drawerOpen = false"
    />

    <!-- 2. 单张命中图片大图查看模态框 -->
    <div
      v-if="lightboxHit"
      class="lightbox-backdrop"
      @click="lightboxHit = null"
    >
      <div class="lightbox-modal" @click.stop>
        <div class="lightbox-header">
          <div>
            <h3>检索命中图像查看</h3>
            <p>{{ hitTitle(lightboxHit) }}</p>
          </div>
          <button
            class="icon-button"
            title="关闭大图预览"
            aria-label="关闭预览"
            @click="lightboxHit = null"
          >
            <X :size="18" />
          </button>
        </div>
        <div class="lightbox-body">
          <img
            v-if="hitThumbnails[lightboxHit.record_id]"
            :src="hitThumbnails[lightboxHit.record_id]"
            alt="检索匹配大图"
            class="lightbox-img"
          />
          <div v-else class="lightbox-no-img">
            <ImageIcon :size="48" />
            <p>暂无可用大图数据</p>
          </div>
        </div>
        <div class="lightbox-footer">
          <div class="lightbox-meta">
            <span v-if="lightboxHit.score != null" class="hit-badge score">
              {{ scoreLabel(lightboxHit) }}
            </span>
            <span
              v-if="lightboxHit.source.pts_ms != null"
              class="hit-badge timestamp"
            >
              时间戳: {{ formatPts(lightboxHit.source.pts_ms) }} ({{
                lightboxHit.source.pts_ms
              }}ms)
            </span>
            <span
              v-if="lightboxHit.source.object_id"
              class="hit-badge location"
            >
              目标: {{ lightboxHit.source.object_id }}
            </span>
          </div>
          <div class="lightbox-actions">
            <button
              v-if="lightboxHit.source.run_id"
              class="button secondary"
              @click="
                openHitDetail(lightboxHit!);
                lightboxHit = null;
              "
            >
              <Layers :size="14" />
              <span>查看结构化抽屉</span>
            </button>
            <button
              v-if="lightboxHit.source.run_id"
              class="button primary"
              @click="
                navigateToResults(lightboxHit!);
                lightboxHit = null;
              "
            >
              <ExternalLink :size="14" />
              <span>跳转至结果工作台</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.search-page {
  max-width: 1320px;
}
.eyebrow {
  display: block;
  margin-bottom: 5px;
  color: var(--text-muted, #64716d);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.notice {
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 12.5px;
}
.notice.error {
  color: #991b1b;
  background: #fef2f2;
  border-color: #fecaca;
}
.search-controls {
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  background: var(--color-surface, #fff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}
.mode-tabs {
  display: flex;
  gap: 0;
  padding: 0 16px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fff;
}
.mode-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 11px 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted, #64716d);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  position: relative;
  top: 1px;
  transition: all 120ms ease;
}
.mode-tab-btn:hover:not(.active) {
  color: var(--color-text, #17211f);
}
.mode-tab-btn.active {
  border-bottom-color: #10b981;
  color: #047857;
  font-weight: 600;
  background: transparent;
}

.search-form-section {
  padding: 16px 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 1. 文搜图行 */
.text-search-box {
  width: 100%;
}
.text-query-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  min-height: 42px;
  background: #fff;
  transition: all 140ms ease;
}
.text-query-bar:focus-within {
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15);
}
.text-search-icon {
  color: #64716d;
  flex-shrink: 0;
}
.text-query-bar:focus-within .text-search-icon {
  color: #10b981;
}
.text-search-input {
  flex: 1;
  min-width: 0;
  height: 38px;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 0 !important;
  font-size: 13.5px;
  color: var(--color-text, #17211f);
  -webkit-appearance: none;
  appearance: none;
}
.text-search-input:focus,
.text-search-input:focus-visible {
  outline: none !important;
  outline-offset: 0 !important;
  border: none !important;
  box-shadow: none !important;
}
.text-search-input::-webkit-search-cancel-button,
.text-search-input::-webkit-search-decoration {
  -webkit-appearance: none;
  appearance: none;
  display: none;
}
.query-clear-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #f1f5f4;
  color: var(--muted, #64716d);
  cursor: pointer;
  transition: all 120ms ease;
}
.query-clear-icon-btn:hover {
  background: #e2e8e6;
  color: var(--color-text, #17211f);
}

/* 2. 人搜图卡片 */
.portrait-query-card {
  display: flex;
  align-items: stretch;
  gap: 16px;
  padding: 14px 16px;
  background: #f8faf9;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  transition: border-color 140ms ease;
}
.portrait-query-card:focus-within {
  border-color: #cbd5e1;
}

/* 缩略图 */
.portrait-preview-box {
  width: 66px;
  height: 66px;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
  border: 1.5px dashed #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  flex-shrink: 0;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04);
  transition: all 140ms ease;
}
.portrait-preview-box.has-preview {
  border: 1.5px solid #10b981;
  background: #0f172a;
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.18);
}
.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.preview-clear-btn {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease, background 120ms ease;
}
.preview-clear-btn:hover {
  background: #ef4444;
  transform: scale(1.1);
}
.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: var(--muted, #64716d);
}
.preview-scan-icon {
  color: #10b981;
  opacity: 0.85;
}
.preview-tip {
  font-size: 10px;
  font-weight: 500;
  color: var(--muted, #64716d);
}

/* 中间输入区 */
.portrait-inputs-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
}
.portrait-source-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.portrait-upload-btn {
  position: relative;
  overflow: hidden;
  height: 32px;
  min-height: 32px;
  font-size: 12px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fff;
  color: var(--color-text, #17211f);
  cursor: pointer;
  transition: all 120ms ease;
}
.portrait-upload-btn:hover {
  border-color: #10b981;
  color: #047857;
  background: #ecfdf5;
}
.portrait-upload-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.portrait-source-sep {
  color: #94a3b8;
  font-size: 11px;
  font-weight: 600;
  padding: 0 2px;
}
.portrait-asset-dropdown {
  flex: 1;
  min-width: 240px;
  position: relative;
  display: flex;
  align-items: center;
}
.asset-select-icon {
  position: absolute;
  left: 10px;
  color: #64748b;
  pointer-events: none;
}
.portrait-asset-select {
  width: 100%;
  height: 32px;
  min-height: 32px;
  padding: 0 10px 0 30px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fff;
  color: var(--color-text, #17211f);
  font-size: 12px;
  outline: none;
  cursor: pointer;
  transition: all 120ms ease;
}
.portrait-asset-select:hover {
  border-color: #cbd5e1;
}
.portrait-asset-select:focus {
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15);
}
.portrait-clear-btn {
  height: 32px;
  min-height: 32px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #b91c1c;
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 4px;
  cursor: pointer;
  transition: all 120ms ease;
}
.portrait-clear-btn:hover {
  background: #fef2f2;
  border-color: #f87171;
}

/* 状态提示 */
.portrait-status-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  line-height: 1.4;
  color: var(--muted, #64716d);
  min-height: 20px;
}
.status-badge {
  padding: 1px 7px;
  border-radius: 3px;
  font-size: 10.5px;
  font-weight: 600;
  flex-shrink: 0;
}
.status-badge.local {
  background: #e0f2fe;
  color: #0369a1;
  border: 1px solid #bae6fd;
}
.status-badge.asset {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}
.status-text {
  font-weight: 500;
  color: var(--color-text, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-hint-muted {
  color: #64748b;
  font-size: 11.5px;
}

/* 阈值控件 */
.portrait-threshold-box {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  padding-left: 16px;
  border-left: 1px solid var(--line, #e2e8e6);
  min-width: 120px;
  flex-shrink: 0;
}
.threshold-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px;
}
.threshold-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--color-text, #17211f);
  white-space: nowrap;
}
.threshold-hint {
  font-size: 10px;
  color: #94a3b8;
  white-space: nowrap;
}
.threshold-input-group {
  display: flex;
  align-items: center;
}
.threshold-field {
  width: 100%;
  height: 32px;
  min-height: 32px;
  padding: 2px 8px;
  text-align: center;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  background: #fff;
  color: var(--color-text, #17211f);
  outline: none;
  transition: all 120ms ease;
}
.threshold-field:hover {
  border-color: #cbd5e1;
}
.threshold-field:focus {
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15);
}

/* 3. 数据类型过滤与检索发起栏 */
.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 2px 0 0;
  background: transparent;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.filter-label {
  color: var(--muted, #64716d);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.filter-chips {
  display: flex;
  align-items: center;
  gap: 6px;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 11px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fff;
  color: var(--muted, #64716d);
  cursor: pointer;
  font-size: 11.5px;
  font-weight: 500;
  transition: all 120ms ease;
}
.filter-chip:hover {
  border-color: #cbd5e1;
  color: var(--color-text, #17211f);
}
.filter-chip.active {
  border-color: #10b981;
  background: #ecfdf5;
  color: #047857;
  font-weight: 600;
}
.chip-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: background 120ms ease;
}
.filter-chip.active .chip-dot {
  background: #10b981;
}
.search-submit {
  min-height: 34px;
  height: 34px;
  font-size: 12.5px;
  padding: 0 18px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 4px;
  margin-left: auto;
}

/* 保存检索与结果列表 */
.result-panel {
  margin-top: 14px;
}
.saved-panel {
  margin-top: 14px;
}
.saved-create {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}
.saved-create input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  padding: 5px 10px;
  min-height: 32px;
  height: 32px;
  font-size: 12px;
  background: #fff;
  outline: none;
}
.saved-create input:focus {
  border-color: #10b981;
}
.saved-create button {
  min-height: 32px;
  height: 32px;
  font-size: 12px;
  padding: 0 12px;
}
.saved-list {
  display: flex;
  flex-direction: column;
}
.saved-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--line, #e2e8e6);
}
.saved-item > span:first-child {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.saved-item small {
  color: var(--muted, #64716d);
  font-size: 11px;
}
.saved-actions {
  display: flex;
  gap: 4px;
}
.saved-empty {
  padding: 12px 14px;
  color: var(--muted, #64716d);
  text-align: center;
  font-size: 11.5px;
}
.query-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--line, #e2e8e6);
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #f8fafc;
  color: #0369a1;
  font-size: 12px;
}
.hit-list {
  display: flex;
  flex-direction: column;
}
.hit-card {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 12px 16px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #fff;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 120ms ease;
}
.hit-card:hover {
  background: #f8fafc;
}
.hit-thumbnail-box {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 6px;
  overflow: hidden;
  background: #0f172a;
  border: 1px solid var(--line, #e2e8e6);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.hit-thumbnail-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.hit-thumbnail-loading {
  color: #94a3b8;
}
.hit-fallback-icon {
  color: #10b981;
}
.thumbnail-zoom-hint {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 120ms ease;
}
.hit-thumbnail-box:hover .thumbnail-zoom-hint {
  opacity: 1;
}
.hit-main-info {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  flex: 1;
}
.hit-header-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.hit-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hit-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.hit-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: #f1f5f9;
  color: #475569;
}
.hit-badge.portrait {
  background: #fdf4ff;
  color: #a21caf;
  border: 1px solid #f5d0fe;
}
.hit-badge.ocr {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}
.hit-badge.score {
  background: #ecfdf5;
  color: #047857;
  font-weight: 600;
  border: 1px solid #a7f3d0;
}
.hit-badge.timestamp {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fed7aa;
  font-weight: 600;
}
.hit-badge.page {
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e2e8e6;
}
.hit-snippet {
  margin: 0;
  color: var(--graphite, #17211f);
  font-size: 12px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.hit-source-location {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--muted, #64716d);
}
.loc-item {
  background: #f8faf9;
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid #eef2f1;
}
.hit-action-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.hit-action-btn {
  height: 30px;
  min-height: 30px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 4px;
}
.search-empty {
  min-height: 130px;
  padding: 24px 14px;
  gap: 6px;
  color: var(--muted, #64716d);
}
.search-empty strong {
  font-size: 13px;
  color: var(--color-text, #17211f);
}
.search-empty span {
  font-size: 11.5px;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Lightbox 大图预览弹窗 */
.lightbox-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.78);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.lightbox-modal {
  background: #fff;
  border-radius: 10px;
  max-width: 720px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow:
    0 20px 25px -5px rgba(0, 0, 0, 0.3),
    0 8px 10px -6px rgba(0, 0, 0, 0.3);
}
.lightbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
}
.lightbox-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text, #17211f);
}
.lightbox-header p {
  margin: 2px 0 0;
  font-size: 11.5px;
  color: var(--muted, #64716d);
}
.lightbox-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #090d16;
  min-height: 320px;
  max-height: 60vh;
  overflow: auto;
}
.lightbox-img {
  max-width: 100%;
  max-height: 56vh;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
}
.lightbox-no-img {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748b;
  gap: 8px;
}
.lightbox-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #f8fafc;
  flex-wrap: wrap;
}
.lightbox-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.lightbox-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.lightbox-actions .button {
  height: 32px;
  min-height: 32px;
  font-size: 12px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 768px) {
  .portrait-query-card {
    flex-direction: column;
  }
  .portrait-threshold-box {
    border-left: 0;
    border-top: 1px solid var(--line, #e2e8e6);
    padding-left: 0;
    padding-top: 10px;
  }
  .filter-row {
    flex-direction: column;
    align-items: stretch;
  }
  .search-submit {
    margin-left: 0;
    width: 100%;
  }
  .hit-card {
    flex-direction: column;
    align-items: flex-start;
  }
  .hit-action-group {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>

