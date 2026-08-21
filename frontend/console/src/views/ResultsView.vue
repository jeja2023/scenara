<script setup lang="ts">
import {
  ExternalLink,
  Eye,
  FileSearch,
  FileText,
  Play,
  Plus,
  RotateCcw,
  Search,
  UserRound,
  Video,
  X,
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import type { Router } from "vue-router";
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

const router: Router = useRouter();
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

const detailDialog = ref<HTMLDialogElement | null>(null);
const isDetailOpen = ref(false);

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
    const requestedUnit =
      typeof route.query.unit === "string" ? route.query.unit : "";
    const requestedItem = requestedRun
      ? items.value.find((item) => item.run_id === requestedRun)
      : null;
    if (requestedItem) {
      const detailIsAlreadyOpen =
        isDetailOpen.value &&
        selected.value?.result_id === requestedItem.result_id;
      if (!detailIsAlreadyOpen) {
        await showDetail(requestedItem, requestedUnit);
      }
    } else if (!selected.value && items.value[0]) {
      await openResult(items.value[0]);
    }
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

async function openResult(item: ResultSummary, unitId = ""): Promise<void> {
  selected.value = item;
  detailLoading.value = true;
  error.value = "";
  try {
    const page = await api<{ result: ResultEnvelope; unit_total: number }>(
      `/api/v1/runs/${encodeURIComponent(item.run_id)}/result?unit_limit=1000`,
    );
    result.value = page.result;
    unitTotal.value = page.unit_total;
    selectedUnit.value =
      result.value.units.find((unit) => unit.unit_id === unitId) ??
      result.value.units[0] ??
      null;
  } catch (caught) {
    result.value = null;
    error.value = userFacingError(caught, "结果详情加载失败，请稍后重试");
  } finally {
    detailLoading.value = false;
  }
}

async function showDetail(item: ResultSummary, unitId = ""): Promise<void> {
  isDetailOpen.value = true;
  await openResult(item, unitId);
  if (detailDialog.value && !detailDialog.value.open) {
    detailDialog.value.showModal();
  }
}

function closeDetail(): void {
  isDetailOpen.value = false;
  detailDialog.value?.close();
}

function onDialogClosed(): void {
  isDetailOpen.value = false;
  if (route.query.run || route.query.unit) {
    const query = { ...route.query };
    delete query.run;
    delete query.unit;
    void router.replace({ query });
  }
}

function handleBackdropClick(event: MouseEvent): void {
  if (event.target === detailDialog.value) {
    closeDetail();
  }
}

function openWorkspace(item: ResultSummary): void {
  void router.push({ path: "/parse", query: { run: item.run_id } });
}

function navigateToParse(runId?: string): void {
  if (runId) {
    void router.push({ path: "/parse", query: { run: runId } });
  } else {
    void router.push("/parse");
  }
}

function clearFilters(): void {
  query.value = "";
  domain.value = "";
  mediaKind.value = "";
  void refresh();
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page results-page">
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
          <Search :size="15" />
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
        <button class="button secondary filter-btn" @click="clearFilters">
          <RotateCcw :size="13" />重置
        </button>
        <button
          class="button primary filter-btn action-btn"
          @click="navigateToParse()"
        >
          <Plus :size="14" />新建解析
        </button>
      </div>
    </section>

    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel result-table-panel">
      <div class="panel-header">
        <div class="list-header-left">
          <h2>解析结果列表</h2>
          <span class="badge">{{ total }} 条记录</span>
        </div>
        <span class="badge muted-badge">按最新解析排序</span>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>标识 / 资源名称</th>
              <th>领域</th>
              <th>资产类型</th>
              <th>解析成果概况</th>
              <th>状态</th>
              <th>解析时间</th>
              <th style="text-align: right; width: 140px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(item, index) in items"
              :key="item.result_id"
              :class="{
                selected:
                  selected?.result_id === item.result_id && isDetailOpen,
              }"
            >
              <td class="muted">{{ index + 1 }}</td>
              <td>
                <div class="result-title-cell">
                  <component
                    :is="resultIcon(item)"
                    :size="15"
                    class="cell-icon"
                  />
                  <strong class="title-text" :title="resultTitle(item)">{{
                    resultTitle(item)
                  }}</strong>
                </div>
              </td>
              <td>
                <span class="badge">{{ labelDomain(item.domain) }}</span>
              </td>
              <td>
                <span class="badge">{{
                  labelMediaKind(item.media_kind || "")
                }}</span>
              </td>
              <td>
                <span class="summary-text">
                  {{
                    item.domain === "ocr"
                      ? `${formatBytesCount(item.ocr_block_count)} 个文本块 · ${item.unit_count} ${item.media_kind === "document" ? "页" : "单元"}`
                      : `${formatBytesCount(item.person_count)} 个人员 · ${item.unit_count} 单元`
                  }}
                </span>
              </td>
              <td>
                <span v-if="item.warning_count" class="badge warning">
                  {{ item.warning_count }} 个告警
                </span>
                <span v-else-if="item.status === 'failed'" class="badge danger">
                  失败
                </span>
                <span v-else class="badge green">已完成</span>
              </td>
              <td class="muted time-cell">{{ formatDate(item.created_at) }}</td>
              <td>
                <div class="toolbar compact table-actions">
                  <button
                    class="button secondary compact-btn detail-btn"
                    title="查看详情"
                    aria-label="查看详情"
                    @click="showDetail(item)"
                  >
                    <Eye :size="12" />详情
                  </button>
                  <button
                    class="button secondary compact-btn"
                    title="回到解析工作台"
                    aria-label="回到解析工作台"
                    @click="openWorkspace(item)"
                  >
                    <Play :size="12" />处理
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!items.length" class="empty result-list-empty">
          <FileSearch :size="32" />
          <strong>还没有匹配的解析结果</strong>
          <span>完成一次解析后，结果会自动出现在这里。</span>
          <button class="button primary" @click="navigateToParse()">
            开始解析
          </button>
        </div>
      </div>
    </section>

    <!-- 详情右侧抽屉 / 弹窗 -->
    <dialog
      ref="detailDialog"
      class="modal result-detail-drawer"
      @close="onDialogClosed"
      @click="handleBackdropClick"
    >
      <div class="drawer-content" @click.stop>
        <div class="drawer-header">
          <div class="detail-header-info">
            <span class="eyebrow">解析结果详情</span>
            <h3>{{ selected ? resultTitle(selected) : "" }}</h3>
            <p v-if="selected" class="detail-description">
              {{ resultDescription }}
            </p>
          </div>
          <button
            class="icon-button close-btn"
            title="关闭详情"
            aria-label="关闭详情"
            @click="closeDetail"
          >
            <X :size="16" />
          </button>
        </div>

        <div class="drawer-body">
          <div v-if="detailLoading" class="empty detail-loading">
            正在加载结果详情...
          </div>
          <template v-else-if="selected">
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
              <button
                class="button secondary compact-btn"
                @click="openWorkspace(selected)"
              >
                <ExternalLink :size="13" />回到解析工作台
              </button>
              <button
                class="button primary compact-btn"
                @click="navigateToParse(selected.run_id)"
              >
                <Play :size="13" />继续处理
              </button>
            </div>

            <template v-if="result">
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
                <UserRound :size="16" />
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
                  <strong>解析单元（点击切换对应帧/页特征图）</strong
                  ><span class="badge">{{ result.units.length }}</span>
                </div>
                <div class="unit-button-group">
                  <button
                    v-for="unit in result.units"
                    :key="unit.unit_id"
                    class="unit-button"
                    :class="{
                      selected: selectedUnit?.unit_id === unit.unit_id,
                    }"
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
              </div>
            </template>
          </template>
        </div>
      </div>
    </dialog>
  </section>
</template>

<style scoped>
.results-page {
  max-width: 1500px;
}
.result-stats {
  margin-bottom: 14px;
}
.result-filter-panel {
  margin-bottom: 16px;
}
.result-filter-panel .panel-body {
  padding: 10px 16px;
}
.result-filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.result-search {
  flex: 1 1 280px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--color-surface);
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 0 10px;
  height: 34px;
}
.result-search svg {
  color: var(--muted);
  flex-shrink: 0;
}
.result-search input {
  min-width: 0;
  width: 100%;
  border: 0;
  padding: 0;
  height: 100%;
  min-height: 0;
  background: transparent;
  font-size: 13px;
}
.result-search input:focus {
  outline: none;
  box-shadow: none;
}
.result-filters select {
  width: 150px;
  min-width: 120px;
  height: 34px;
  min-height: 34px;
  padding: 0 10px;
  font-size: 13px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background-color: var(--color-surface);
}
.filter-btn {
  height: 34px;
  min-height: 34px;
  padding: 0 12px;
  font-size: 12.5px;
  gap: 5px;
  white-space: nowrap;
}
.action-btn {
  margin-left: auto;
}
.result-table-panel {
  display: flex;
  flex-direction: column;
}
.result-table-panel .table-scroll {
  height: 480px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.table-scroll thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--color-table-header);
  box-shadow: inset 0 -1px 0 var(--line);
}
.list-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.list-header-left h2 {
  margin: 0;
  font-size: 14px;
}
.muted-badge {
  color: var(--muted);
  font-size: 11px;
}
.data-table th {
  height: 32px;
  padding: 4px 10px;
  font-size: 12px;
}
.data-table td {
  min-height: 34px;
  padding: 5px 10px;
  vertical-align: middle;
}
.data-table tbody tr.selected td {
  background: var(--color-selection);
}
.data-table .badge {
  min-height: 20px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 20px;
}
.result-title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 320px;
}
.cell-icon {
  color: var(--teal);
  flex-shrink: 0;
}
.title-text {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-text {
  font-size: 12px;
  color: var(--text-muted);
}
.time-cell {
  font-size: 12px;
  white-space: nowrap;
}
.table-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  flex-wrap: nowrap;
}
.table-actions .compact-btn {
  height: 24px;
  min-height: 24px;
  padding: 0 7px;
  font-size: 11.5px;
  font-weight: 550;
  gap: 4px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
@media (max-width: 900px) {
  .filter-btn,
  .table-actions .compact-btn,
  .close-btn {
    min-height: 44px;
    height: 44px;
  }
  .close-btn {
    width: 44px;
    min-width: 44px;
  }
  .table-actions .compact-btn {
    padding-inline: 10px;
  }
}
.result-list-empty {
  height: calc(100% - 34px);
  min-height: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 36px;
  text-align: center;
}
.result-list-empty svg {
  color: var(--accent-strong);
}

/* Drawer Dialog Styles */
.result-detail-drawer {
  position: fixed;
  inset: 0 0 0 auto;
  width: min(680px, 100vw);
  max-width: 100vw;
  height: 100vh;
  max-height: 100vh;
  margin: 0;
  padding: 0;
  border: 0;
  border-left: 1px solid var(--line);
  background: var(--color-surface);
  box-shadow: -10px 0 30px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
}
.result-detail-drawer::backdrop {
  background: rgba(17, 26, 24, 0.4);
  backdrop-filter: blur(2px);
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
  align-items: flex-start;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  background: var(--color-surface);
}
.detail-header-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.eyebrow {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.drawer-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 540px;
}
.detail-description {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.close-btn {
  width: 28px;
  height: 28px;
  min-width: 28px;
  min-height: 28px;
  border-radius: 4px;
  padding: 0;
}
.drawer-body {
  padding: 18px 20px;
  overflow-y: auto;
  flex: 1;
  scrollbar-width: thin;
}
.detail-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}
.detail-summary-grid div {
  display: grid;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-soft);
}
.detail-summary-grid span {
  color: var(--text-muted);
  font-size: 11px;
}
.detail-summary-grid strong {
  font-size: 13.5px;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.result-text-preview {
  width: 100%;
  min-height: 120px;
  max-height: 220px;
  resize: vertical;
  margin-bottom: 12px;
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: var(--surface-soft);
}
.result-domain-note {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-soft);
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 12px;
}
.result-domain-note svg {
  color: var(--teal);
  flex-shrink: 0;
  margin-top: 1px;
}
.result-unit-list {
  border-top: 1px solid var(--line);
  margin-top: 14px;
  padding-top: 10px;
  display: grid;
  gap: 6px;
}
.result-unit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 2px;
}
.unit-button-group {
  display: grid;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
  scrollbar-width: thin;
  padding-right: 2px;
}
.unit-button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 6px 10px;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-size: 12px;
  transition: all 120ms ease;
}
.unit-button:hover,
.unit-button.selected {
  border-color: var(--line-strong);
  background: var(--surface-soft);
}
.unit-button small {
  color: var(--text-muted);
  font-size: 11px;
}
.detail-loading {
  min-height: 140px;
}
@media (max-width: 980px) {
  .action-btn {
    margin-left: 0;
  }
}
@media (max-width: 620px) {
  .detail-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
