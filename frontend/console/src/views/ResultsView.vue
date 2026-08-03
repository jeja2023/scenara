<script setup lang="ts">
import {
  ArrowRight,
  FileSearch,
  FileText,
  Filter,
  RefreshCw,
  Search,
  UserRound,
  Video,
  X,
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, userFacingError } from "../api";
import FeatureCropGallery from "../components/FeatureCropGallery.vue";
import { labelDomain, labelMediaKind, labelUnitType } from "../labels";
import type {
  Domain,
  DomainManifest,
  MediaKind,
  MediaUnitResult,
  ResultEnvelope,
  ResultSummary,
  ResultSummaryPage,
} from "../types";

const router = useRouter();
const route = useRoute();
const items = ref<ResultSummary[]>([]);
const domains = ref<DomainManifest[]>([]);
const selected = ref<ResultSummary | null>(null);
const result = ref<ResultEnvelope | null>(null);
const loading = ref(false);
const detailLoading = ref(false);
const error = ref("");
const query = ref("");
const domain = ref<Domain | "">("");
const mediaKind = ref<MediaKind | "">("");
const total = ref(0);
const unitTotal = ref(0);
const selectedUnit = ref<MediaUnitResult | null>(null);

const selectedPayload = computed(() => result.value?.domain_payload ?? null);
const ocrText = computed(() =>
  selectedPayload.value?.domain === "ocr"
    ? String(selectedPayload.value.text ?? "")
    : "",
);
const objectCount = computed(
  () =>
    result.value?.units.reduce((sum, unit) => sum + unit.objects.length, 0) ??
    selected.value?.object_count ??
    0,
);
const resultDescription = computed(() => {
  if (!selected.value) return "选择一条结果查看原始内容和解析单元。";
  if (selected.value.domain === "ocr") {
    return `${selected.value.ocr_block_count} 个文本块 · ${selected.value.text_length} 个字符`;
  }
  return `${selected.value.person_count} 个人员 · ${selected.value.face_count} 张人脸`;
});

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString();
}

function formatBytesCount(value: number): string {
  if (value < 1000) return String(value);
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}k`;
  return `${(value / 1_000_000).toFixed(1)}m`;
}

function formatUnitPosition(unit: MediaUnitResult): string {
  if (unit.pts_ms == null) return `单元 ${unit.index + 1}`;
  const seconds = Math.floor(unit.pts_ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function resultTitle(item: ResultSummary): string {
  return item.resource_name || item.asset_id || item.source_id || item.run_id;
}

function resultIcon(item: ResultSummary): typeof FileText {
  if (item.media_kind === "video" || item.media_kind === "stream") return Video;
  if (item.domain === "portrait") return UserRound;
  return FileText;
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({ limit: "50" });
    if (query.value.trim()) params.set("query", query.value.trim());
    if (domain.value) params.set("domain", domain.value);
    if (mediaKind.value) params.set("media_kind", mediaKind.value);
    const [page, manifests] = await Promise.all([
      api<ResultSummaryPage>(`/api/v1/results?${params.toString()}`),
      api<DomainManifest[]>("/api/v1/domains"),
    ]);
    items.value = page.items;
    total.value = page.total;
    domains.value = manifests;
    if (selected.value) {
      const next = items.value.find(
        (item) => item.result_id === selected.value?.result_id,
      );
      selected.value = next ?? null;
      if (!next) {
        result.value = null;
        selectedUnit.value = null;
      }
    }
    const requestedRun =
      typeof route.query.run === "string" ? route.query.run : "";
    const requestedItem = requestedRun
      ? items.value.find((item) => item.run_id === requestedRun)
      : null;
    if (requestedItem) await openResult(requestedItem);
    else if (!selected.value && items.value[0])
      await openResult(items.value[0]);
    if (!items.value.length) {
      result.value = null;
      selectedUnit.value = null;
    }
  } catch (caught) {
    error.value = userFacingError(caught, "解析结果加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function openResult(item: ResultSummary): Promise<void> {
  selected.value = item;
  detailLoading.value = true;
  error.value = "";
  try {
    const page = await api<{ result: ResultEnvelope; unit_total: number }>(
      `/api/v1/runs/${encodeURIComponent(item.run_id)}/result?unit_limit=50`,
    );
    result.value = page.result;
    unitTotal.value = page.unit_total;
    selectedUnit.value = result.value.units[0] ?? null;
  } catch (caught) {
    result.value = null;
    error.value = userFacingError(caught, "结果详情加载失败，请稍后重试");
  } finally {
    detailLoading.value = false;
  }
}

function openWorkspace(item: ResultSummary): void {
  void router.push({ path: "/parse", query: { run: item.run_id } });
}

function clearFilters(): void {
  query.value = "";
  domain.value = "";
  mediaKind.value = "";
  void refresh();
}

onMounted(refresh);
</script>

<template>
  <section class="page results-page">
    <div class="page-header results-header">
      <div>
        <span class="eyebrow">结果中心</span>
        <h1>解析结果</h1>
        <p>跨人像、OCR 文档和全部数据资产查看已产生的解析结果。</p>
      </div>
      <div class="toolbar">
        <button class="button secondary" :disabled="loading" @click="refresh">
          <RefreshCw :size="16" :class="{ spin: loading }" />刷新
        </button>
        <button class="button primary" @click="router.push('/parse')">
          <FileSearch :size="16" />新建解析
        </button>
      </div>
    </div>

    <div class="stats result-stats">
      <div class="stat teal">
        <span>结果总数</span><strong>{{ total }}</strong
        ><small>当前筛选范围</small>
      </div>
      <div class="stat">
        <span>人像结果</span
        ><strong>{{
          items.filter((item) => item.domain === "portrait").length
        }}</strong
        ><small>当前页</small>
      </div>
      <div class="stat green">
        <span>OCR 结果</span
        ><strong>{{
          items.filter((item) => item.domain === "ocr").length
        }}</strong
        ><small>当前页</small>
      </div>
      <div class="stat coral">
        <span>待关注</span
        ><strong>{{
          items.filter(
            (item) => item.warning_count > 0 || item.status === "failed",
          ).length
        }}</strong
        ><small>告警或失败</small>
      </div>
    </div>

    <section class="panel result-filter-panel">
      <div class="panel-body result-filters">
        <div class="search-field result-search">
          <Search :size="16" />
          <input
            v-model.trim="query"
            type="search"
            placeholder="搜索文件名、来源或运行编号"
            @keyup.enter="refresh"
          />
        </div>
        <select v-model="domain" aria-label="领域筛选" @change="refresh">
          <option value="">全部领域</option>
          <option
            v-for="item in domains"
            :key="item.domain_id"
            :value="item.domain_id"
          >
            {{ item.display_name || labelDomain(item.domain_id) }}
          </option>
        </select>
        <select v-model="mediaKind" aria-label="资产类型筛选" @change="refresh">
          <option value="">全部资产类型</option>
          <option value="image">图片</option>
          <option value="video">视频</option>
          <option value="document">文档</option>
          <option value="stream">视频流</option>
        </select>
        <button class="button secondary" @click="clearFilters">
          <Filter :size="15" />重置
        </button>
      </div>
    </section>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="results-browser-layout">
      <section class="panel result-list-panel">
        <div class="panel-header">
          <div>
            <h2>结果列表</h2>
            <p>{{ total }} 条结果</p>
          </div>
          <span class="badge">按最新解析排序</span>
        </div>
        <div v-if="items.length" class="result-list">
          <button
            v-for="item in items"
            :key="item.result_id"
            class="result-list-item"
            :class="{ selected: selected?.result_id === item.result_id }"
            @click="openResult(item)"
          >
            <span class="result-list-icon"
              ><component :is="resultIcon(item)" :size="18"
            /></span>
            <span class="result-list-main">
              <strong>{{ resultTitle(item) }}</strong>
              <small
                >{{ labelDomain(item.domain) }} ·
                {{ labelMediaKind(item.media_kind || "") }} ·
                {{ formatDate(item.created_at) }}</small
              >
              <span class="result-list-meta">
                <span>{{
                  item.domain === "ocr"
                    ? `${formatBytesCount(item.ocr_block_count)} 个文本块`
                    : `${formatBytesCount(item.person_count)} 个人员`
                }}</span>
                <span
                  >{{ item.unit_count }}
                  {{ item.media_kind === "document" ? "页" : "个单元" }}</span
                >
                <span v-if="item.warning_count" class="warning-text"
                  >{{ item.warning_count }} 个告警</span
                >
              </span>
            </span>
            <ArrowRight :size="16" class="result-list-arrow" />
          </button>
        </div>
        <div v-else class="empty result-list-empty">
          <FileSearch :size="28" />
          <strong>还没有匹配的解析结果</strong>
          <span>完成一次解析后，结果会自动出现在这里。</span>
          <button class="button primary" @click="router.push('/parse')">
            开始解析
          </button>
        </div>
      </section>

      <aside class="result-detail-panel">
        <section v-if="selected" class="panel result-detail-card">
          <div class="panel-header">
            <div>
              <span class="eyebrow">结果详情</span>
              <h2>{{ resultTitle(selected) }}</h2>
              <p>{{ resultDescription }}</p>
            </div>
            <button
              class="icon-button"
              title="关闭详情"
              aria-label="关闭详情"
              @click="
                selected = null;
                result = null;
              "
            >
              <X :size="17" />
            </button>
          </div>
          <div class="panel-body">
            <div class="detail-summary-grid">
              <div>
                <span>领域</span
                ><strong>{{ labelDomain(selected.domain) }}</strong>
              </div>
              <div>
                <span>资产类型</span
                ><strong>{{
                  labelMediaKind(selected.media_kind || "")
                }}</strong>
              </div>
              <div>
                <span>解析单元</span
                ><strong>{{ unitTotal || selected.unit_count }}</strong>
              </div>
              <div>
                <span>对象数量</span><strong>{{ objectCount }}</strong>
              </div>
            </div>
            <div class="detail-actions">
              <button class="button secondary" @click="openWorkspace(selected)">
                回到解析工作台
              </button>
              <button
                class="button primary"
                @click="
                  router.push({
                    path: '/parse',
                    query: { run: selected.run_id },
                  })
                "
              >
                继续处理
              </button>
            </div>
            <div v-if="detailLoading" class="empty detail-loading">
              正在加载结果详情
            </div>
            <template v-else-if="result">
              <textarea
                v-if="selected.domain === 'ocr'"
                class="result-text-preview"
                readonly
                :value="ocrText"
                aria-label="OCR 结果文本"
              />
              <div
                v-if="selected.domain === 'portrait'"
                class="result-domain-note"
              >
                <UserRound :size="17" />
                <span
                  >已识别 {{ selected.person_count }} 个人员、{{
                    selected.face_count
                  }}
                  张人脸，可从解析工作台继续进行人像检索和比对。</span
                >
              </div>
              <FeatureCropGallery
                v-if="selected.domain === 'portrait' && result.units.length"
                :run-id="result.run_id"
                :unit="selectedUnit"
              />
              <div class="result-unit-list">
                <div class="result-unit-header">
                  <strong>解析单元</strong
                  ><span>{{ result.units.length }}</span>
                </div>
                <button
                  v-for="unit in result.units.slice(0, 8)"
                  :key="unit.unit_id"
                  :class="{ selected: selectedUnit?.unit_id === unit.unit_id }"
                  @click="selectedUnit = unit"
                >
                  <span>{{
                    unit.page_number
                      ? `第 ${unit.page_number} 页`
                      : formatUnitPosition(unit)
                  }}</span>
                  <small
                    >{{ labelUnitType(unit.unit_type) }} ·
                    {{ unit.objects.length }} 个对象</small
                  >
                </button>
              </div>
            </template>
          </div>
        </section>
        <section v-else class="panel result-detail-card empty-detail">
          <FileSearch :size="32" />
          <strong>选择一条结果</strong>
          <span>在左侧列表选择结果，查看文本、对象和来源信息。</span>
        </section>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.results-page {
  max-width: 1500px;
}
.results-header {
  align-items: flex-end;
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
.result-filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.result-search {
  flex: 1 1 320px;
}
.result-search input {
  min-width: 0;
  width: 100%;
}
.results-browser-layout {
  display: grid;
  grid-template-columns: minmax(360px, 0.85fr) minmax(480px, 1.15fr);
  gap: 16px;
  align-items: start;
}
.result-list-panel,
.result-detail-card {
  min-height: 560px;
}
.result-list {
  display: flex;
  flex-direction: column;
}
.result-list-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  width: 100%;
  padding: 15px 18px;
  border: 0;
  border-top: 1px solid var(--line);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.result-list-item:hover,
.result-list-item.selected {
  background: var(--surface-soft);
}
.result-list-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  flex: 0 0 auto;
}
.result-list-main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 4px;
}
.result-list-main strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-list-main small {
  color: var(--text-muted);
}
.result-list-meta {
  display: flex;
  gap: 12px;
  color: var(--text-muted);
  font-size: 12px;
  flex-wrap: wrap;
}
.warning-text {
  color: var(--warning);
}
.result-list-arrow {
  margin-top: 9px;
  color: var(--text-muted);
}
.result-list-empty,
.empty-detail {
  min-height: 480px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 10px;
  padding: 36px;
  text-align: center;
}
.result-list-empty svg,
.empty-detail svg {
  color: var(--accent-strong);
}
.result-detail-card {
  position: sticky;
  top: 78px;
}
.detail-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.detail-summary-grid div {
  display: grid;
  gap: 4px;
  padding: 11px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface-soft);
}
.detail-summary-grid span {
  color: var(--text-muted);
  font-size: 12px;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}
.result-text-preview {
  width: 100%;
  min-height: 150px;
  resize: vertical;
  margin-bottom: 14px;
}
.result-domain-note {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface-soft);
  color: var(--text-muted);
  margin-bottom: 14px;
}
.result-unit-list {
  border-top: 1px solid var(--line);
  margin-top: 16px;
  padding-top: 12px;
  display: grid;
  gap: 6px;
}
.result-unit-header {
  display: flex;
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 12px;
}
.result-unit-list button {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 8px 10px;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.result-unit-list button:hover,
.result-unit-list button.selected {
  border-color: var(--line-strong);
  background: var(--surface-soft);
}
.result-unit-list small {
  color: var(--text-muted);
}
.detail-loading {
  min-height: 160px;
}
@media (max-width: 980px) {
  .results-browser-layout {
    grid-template-columns: 1fr;
  }
  .result-detail-card {
    position: static;
  }
}
@media (max-width: 620px) {
  .detail-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
