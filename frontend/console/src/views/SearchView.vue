<script setup lang="ts">
import {
  ArrowRight,
  Bookmark,
  FileSearch,
  FileText,
  ScanFace,
  Search as SearchIcon,
  Trash2,
  Upload,
  UserRound,
  Video,
} from "@lucide/vue";
import { computed, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { useRouter } from "vue-router";

import { api, apiBlob, apiForm, blobToDataUrl, userFacingError } from "../api";
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
  preview.value = URL.createObjectURL(selected);
}

async function setAsset(value: string): Promise<void> {
  assetId.value = value;
  if (!value) {
    preview.value = "";
    return;
  }
  file.value = null;
  try {
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
  preview.value = "";
}

function setMode(next: SearchMode): void {
  mode.value = next;
  response.value = null;
  error.value = "";
}

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

function openHit(hit: SearchHit): void {
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
  if (hit.score == null) return "文本命中";
  return `相似度 ${hit.score.toFixed(4)}`;
}

useRefresh(runSearch);
</script>

<template>
  <section class="page search-page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel search-controls">
      <div class="mode-tabs" role="tablist" aria-label="检索方式">
        <button :class="{ active: mode === 'text' }" @click="setMode('text')">
          <SearchIcon :size="16" />文搜图 / 文搜视频
        </button>
        <button
          :class="{ active: mode === 'portrait' }"
          @click="setMode('portrait')"
        >
          <ScanFace :size="16" />人搜图
        </button>
      </div>
      <div v-if="mode === 'text'" class="text-query-row">
        <SearchIcon :size="17" />
        <input
          v-model.trim="query"
          type="search"
          placeholder="输入文字，例如：红色车辆、合同编号、人员姓名"
          @keyup.enter="runSearch"
        />
      </div>
      <div v-else class="portrait-query-row">
        <div class="query-preview">
          <img v-if="preview" :src="preview" alt="查询图片预览" />
          <ScanFace v-else :size="28" />
        </div>
        <label class="button secondary upload-button"
          ><Upload :size="16" />选择查询图片<input
            type="file"
            accept="image/*"
            @change="setFile"
        /></label>
        <button
          v-if="file || assetId"
          class="button secondary"
          @click="clearFile"
        >
          清除图片
        </button>
        <select
          :value="assetId"
          aria-label="从图片资产选择查询图片"
          @change="setAsset(($event.target as HTMLSelectElement).value)"
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
        <label class="threshold"
          ><span>相似度阈值</span
          ><input
            v-model="threshold"
            type="number"
            min="-1"
            max="1"
            step="0.01"
        /></label>
      </div>
      <div class="filter-row">
        <span>限定数据类型</span>
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
        <button
          class="button primary search-submit"
          :disabled="loading || !hasQuery"
          @click="runSearch"
        >
          <SearchIcon :size="16" />开始检索
        </button>
      </div>
    </section>

    <section class="panel saved-panel">
      <div class="panel-header">
        <div>
          <h2><Bookmark :size="17" />保存检索</h2>
          <p>把常用的文字或人像资产查询保存下来，下一次直接执行。</p>
        </div>
        <span class="muted">{{ savedSearches.length }} 个</span>
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
      <div v-if="response?.hits.length" class="hit-list">
        <button
          v-for="hit in response.hits"
          :key="hit.record_id"
          class="hit-item"
          @click="openHit(hit)"
        >
          <span class="hit-icon"
            ><component :is="hitIcon(hit)" :size="18"
          /></span>
          <span class="hit-main"
            ><strong>{{ hitTitle(hit) }}</strong
            ><small
              >{{ labelDomain(hit.domain) }} ·
              {{ labelMediaKind(hit.media_kind || "") }} ·
              {{ scoreLabel(hit) }}</small
            ><span v-if="hit.text_snippet" class="snippet">{{
              hit.text_snippet
            }}</span
            ><small class="location"
              >{{
                hit.source.unit_id ? `单元 ${hit.source.unit_id}` : "来源结果"
              }}{{
                hit.source.object_id ? ` · 对象 ${hit.source.object_id}` : ""
              }}</small
            ></span
          >
          <ArrowRight :size="16" />
        </button>
      </div>
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
  </section>
</template>

<style scoped>
.search-page {
  max-width: 1320px;
}
.eyebrow {
  display: block;
  margin-bottom: 5px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
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
.search-controls {
  padding: 0;
  overflow: hidden;
}
.mode-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--line);
}
.mode-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 13px 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.mode-tabs button.active {
  border-bottom-color: var(--teal);
  color: var(--graphite);
  background: #f6faf8;
  font-weight: 700;
}
.text-query-row {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 16px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 5px;
  min-height: 42px;
}
.text-query-row input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
}
.portrait-query-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px;
}
.query-preview {
  display: grid;
  place-items: center;
  width: 72px;
  height: 54px;
  overflow: hidden;
  border-radius: 4px;
  background: #0d1917;
  color: #8ba09a;
}
.query-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
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
.threshold {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: var(--muted);
  font-size: 12px;
}
.threshold input {
  width: 78px;
  min-height: 34px;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 16px 16px;
  color: var(--muted);
  font-size: 12px;
}
.filter-chip {
  padding: 7px 11px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #fff;
  color: var(--muted);
  cursor: pointer;
}
.filter-chip.active {
  border-color: var(--teal);
  background: #e9f5f2;
  color: #16665c;
}
.search-submit {
  margin-left: auto;
}
.result-panel {
  margin-top: 16px;
  min-height: 420px;
}
.saved-panel {
  margin-top: 16px;
}
.saved-create {
  display: flex;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}
.saved-create input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 9px 10px;
}
.saved-list {
  display: flex;
  flex-direction: column;
}
.saved-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 16px;
  border-bottom: 1px solid var(--line);
}
.saved-item > span:first-child {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.saved-item small {
  color: var(--muted);
  font-size: 11px;
}
.saved-actions {
  display: flex;
  gap: 4px;
}
.saved-empty {
  padding: 18px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}
.query-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 16px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}
.hit-list {
  display: flex;
  flex-direction: column;
}
.hit-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 0;
  border-top: 1px solid var(--line);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.hit-item:hover {
  background: #f7faf9;
}
.hit-icon {
  display: grid;
  place-items: center;
  flex: 0 0 34px;
  height: 34px;
  border-radius: 4px;
  background: #eaf4f1;
  color: var(--teal);
}
.hit-main {
  display: grid;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.hit-main strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hit-main small,
.location {
  color: var(--muted);
  font-size: 11px;
}
.snippet {
  display: -webkit-box;
  overflow: hidden;
  color: var(--graphite);
  font-size: 13px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.search-empty {
  min-height: 300px;
  gap: 10px;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 720px) {
  .portrait-query-row {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .threshold {
    margin-left: 0;
    width: 100%;
  }
  .search-submit {
    margin-left: 0;
    width: 100%;
  }
  .saved-create {
    flex-direction: column;
  }
}
</style>
