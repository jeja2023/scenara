<script setup lang="ts">
import {
  AlertCircle,
  Eye,
  FileSearch,
  FileText,
  Play,
  Plus,
  RotateCcw,
  ScanFace,
  Search,
  UserRound,
  Video,
} from "@lucide/vue";
import { onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import type { Router } from "vue-router";
import { useRoute, useRouter } from "vue-router";

import { api, userFacingError } from "../api";
import DataTable from "../components/DataTable.vue";
import ResultDetailDrawer from "../components/ResultDetailDrawer.vue";
import { labelDomain, labelMediaKind, labelRunStatus } from "../labels";
import type {
  Domain,
  DomainManifest,
  MediaKind,
  ResultSummary,
  ResultSummaryPage,
  TableColumn,
} from "../types";

const pageSize = ref(20);

const columns: TableColumn<ResultSummary>[] = [
  { key: "title", label: "标识 / 资源名称" },
  { key: "domain", label: "领域", width: "90px" },
  { key: "media_kind", label: "资产类型", width: "80px" },
  { key: "summary", label: "解析成果概况", width: "200px" },
  { key: "status", label: "状态", width: "80px" },
  {
    key: "created_at",
    label: "解析时间",
    class: "muted time-cell",
    width: "140px",
  },
  {
    key: "actions",
    label: "操作",
    align: "right",
    headerAlign: "right",
    width: "110px",
  },
];

const router: Router = useRouter();
const route = useRoute();
const items = ref<ResultSummary[]>([]);
const domains = ref<DomainManifest[]>([]);
const selected = ref<ResultSummary | null>(null);
const loading = ref(false);
const error = ref("");
const query = ref("");
const domain = ref<Domain | "">("");
const mediaKind = ref<MediaKind | "">("");
const total = ref(0);
const offset = ref(0);

const detailRunId = ref<string | null>(null);
const isDetailOpen = ref(false);

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString();
}

function formatBytesCount(value: number): string {
  if (value < 1000) return String(value);
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}k`;
  return `${(value / 1_000_000).toFixed(1)}m`;
}

function resultTitle(item: ResultSummary): string {
  return item.resource_name || item.asset_id || item.source_id || item.run_id;
}

function resultIcon(item: ResultSummary): typeof FileText {
  if (item.media_kind === "video" || item.media_kind === "stream") return Video;
  if (item.domain === "portrait") return UserRound;
  return FileText;
}

function onPageSizeChange(newSize: number): void {
  pageSize.value = newSize;
  offset.value = 0;
  void refresh();
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({
      limit: String(pageSize.value),
      offset: String(offset.value),
    });
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
    }
    const requestedRun =
      typeof route.query.run === "string" ? route.query.run.trim() : "";
    if (requestedRun) {
      const requestedItem = items.value.find(
        (item) => item.run_id === requestedRun,
      );
      if (requestedItem) {
        selected.value = requestedItem;
      }
      detailRunId.value = requestedRun;
      isDetailOpen.value = true;
    }
  } catch (caught) {
    error.value = userFacingError(caught, "解析结果加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

function showDetail(item: ResultSummary): void {
  selected.value = item;
  detailRunId.value = item.run_id;
  isDetailOpen.value = true;
}

function onDetailClosed(): void {
  isDetailOpen.value = false;
  selected.value = null;
  detailRunId.value = null;
  if (route.query.run || route.query.unit) {
    const q = { ...route.query };
    delete q.run;
    delete q.unit;
    void router.replace({ query: q });
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

function goToPage(nextOffset: number): void {
  offset.value = Math.max(0, nextOffset);
  void refresh();
}

function onFilterChange(): void {
  offset.value = 0;
  void refresh();
}

function clearFilters(): void {
  query.value = "";
  domain.value = "";
  mediaKind.value = "";
  offset.value = 0;
  void refresh();
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page results-page">
    <div class="stats result-stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">结果总数</span>
          <div class="stat-icon-badge">
            <FileSearch :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-desc">当前筛选范围</div>
      </div>

      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">人像结果</span>
          <div class="stat-icon-badge">
            <ScanFace :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{ items.filter((item) => item.domain === "portrait").length }}
        </div>
        <div class="stat-desc">当前页</div>
      </div>

      <div class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">OCR 结果</span>
          <div class="stat-icon-badge">
            <FileText :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{ items.filter((item) => item.domain === "ocr").length }}
        </div>
        <div class="stat-desc">当前页</div>
      </div>

      <div class="stat coral">
        <div class="stat-top-row">
          <span class="stat-title">待关注</span>
          <div class="stat-icon-badge">
            <AlertCircle :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{
            items.filter(
              (item) => item.warning_count > 0 || item.status === "failed",
            ).length
          }}
        </div>
        <div class="stat-desc">告警或失败</div>
      </div>
    </div>

    <section class="panel result-filter-panel">
      <div class="panel-body result-filters">
        <div class="search-field result-search">
          <Search :size="13" />
          <input
            v-model.trim="query"
            type="search"
            placeholder="搜索文件名、来源或运行编号"
            @keyup.enter="onFilterChange"
          />
        </div>

        <div class="select-field">
          <select
            v-model="domain"
            class="filter-select"
            aria-label="筛选领域"
            @change="onFilterChange"
          >
            <option value="">全部领域</option>
            <option
              v-for="item in domains"
              :key="item.domain_id"
              :value="item.domain_id"
            >
              {{ item.display_name }}
            </option>
          </select>
        </div>

        <div class="select-field">
          <select
            v-model="mediaKind"
            class="filter-select"
            aria-label="筛选资产类型"
            @change="onFilterChange"
          >
            <option value="">全部类型</option>
            <option value="image">图片</option>
            <option value="video">视频</option>
            <option value="document">文档</option>
            <option value="stream">视频流</option>
          </select>
        </div>

        <button
          class="button secondary filter-btn"
          title="重置所有筛选"
          @click="clearFilters"
        >
          <RotateCcw :size="13" />重置
        </button>

        <button
          class="button primary parse-btn"
          style="margin-left: auto"
          @click="navigateToParse()"
        >
          <Plus :size="13" />发起新解析
        </button>
      </div>
    </section>

    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel result-list-panel">
      <DataTable
        :columns="columns"
        :items="items"
        :loading="loading"
        :total="total"
        :offset="offset"
        :page-size="pageSize"
        :page-size-options="[10, 20, 50, 100]"
        table-class="results-table"
        wrapper-class="results-table-wrapper"
        @page-change="goToPage"
        @page-size-change="onPageSizeChange"
      >
        <!-- 1. 标识 / 资源名称（严格单行） -->
        <template #title="{ row }">
          <div
            class="result-title-cell"
            :title="`${resultTitle(row)} (${row.run_id})`"
          >
            <component
              :is="resultIcon(row)"
              :size="14"
              class="result-kind-icon"
            />
            <strong class="result-name">{{ resultTitle(row) }}</strong>
          </div>
        </template>

        <!-- 2. 领域 -->
        <template #domain="{ row }">
          <span class="badge status-badge" :class="row.domain">{{
            labelDomain(row.domain)
          }}</span>
        </template>

        <!-- 3. 资产类型 -->
        <template #media_kind="{ row }">
          <span class="badge status-badge media-badge">{{
            row.media_kind ? labelMediaKind(row.media_kind) : "-"
          }}</span>
        </template>

        <!-- 4. 解析成果概况（严格单行） -->
        <template #summary="{ row }">
          <span class="result-summary-text">
            <template v-if="row.domain === 'portrait'">
              <strong>{{ row.person_count }}</strong> 个人员
              <small v-if="row.face_count" class="muted"
                >({{ row.face_count }} 人脸)</small
              >
            </template>
            <template v-else-if="row.domain === 'ocr'">
              <strong>{{ row.ocr_block_count }}</strong> 个文本块
              <small v-if="row.text_length" class="muted"
                >({{ formatBytesCount(row.text_length) }} 字符)</small
              >
            </template>
            <template v-else>
              <strong>{{ row.unit_count }}</strong> 单元 ·
              <strong>{{ row.object_count }}</strong> 对象
            </template>
          </span>
        </template>

        <!-- 5. 状态 -->
        <template #status="{ row }">
          <span class="badge status-badge" :class="row.status">{{
            labelRunStatus(row.status)
          }}</span>
        </template>

        <!-- 6. 解析时间 -->
        <template #created_at="{ row }">
          <span class="muted time-cell mono">{{
            formatDate(row.created_at)
          }}</span>
        </template>

        <!-- 7. 操作（微型按钮 20px） -->
        <template #actions="{ row }">
          <div class="row-actions">
            <button
              class="button secondary table-btn detail-btn"
              title="查看详情"
              aria-label="查看详情"
              @click="showDetail(row)"
            >
              <Eye :size="11" />详情
            </button>
            <button
              class="button secondary table-btn"
              title="回到解析工作台"
              aria-label="回到解析工作台"
              @click="openWorkspace(row)"
            >
              <Play :size="11" />处理
            </button>
          </div>
        </template>

        <template #empty>
          <div class="empty result-list-empty">
            <FileSearch :size="32" />
            <strong>还没有匹配的解析结果</strong>
            <span>完成一次解析后，结果会自动出现在这里。</span>
            <button class="button primary" @click="navigateToParse()">
              开始解析
            </button>
          </div>
        </template>
      </DataTable>
    </section>

    <!-- 详情抽屉组件 -->
    <ResultDetailDrawer
      v-model:open="isDetailOpen"
      :run-id="detailRunId"
      :summary="selected"
      @close="onDetailClosed"
    />
  </section>
</template>

<style scoped>
.results-page {
  width: 100%;
}

.result-stats {
  margin-bottom: 14px;
}

.result-filter-panel {
  margin-bottom: 14px;
  background: #ffffff;
}

.result-filter-panel .panel-body {
  padding: 8px 14px;
}

.result-filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.result-search {
  flex: 1 1 240px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  padding: 0 8px;
  height: 28px;
  box-sizing: border-box;
}

.result-search svg {
  color: var(--muted, #64716d);
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
  font-size: 11.5px;
  outline: none;
}

.filter-select {
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
}

.filter-btn,
.parse-btn {
  height: 28px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.result-list-panel {
  flex: 1;
  background: #ffffff;
}

:deep(.results-table-wrapper .table-scroll) {
  min-height: 480px;
}

/* 全局统一 28px 数据表格行高与 3px 8px 内边距（严格单行不折行） */
:deep(.results-table td),
:deep(.results-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  line-height: 1.3;
}

:deep(.results-table tr) {
  height: 28px;
}

.result-title-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-kind-icon {
  color: var(--muted, #64716d);
  flex-shrink: 0;
}

.result-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-summary-text {
  display: inline-block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 190px;
  font-size: 11.5px;
  line-height: 20px;
}

.media-badge {
  background: #f0f4f3;
  color: #3b504b;
}

.time-cell {
  font-size: 11px;
  color: var(--muted, #64716d);
  white-space: nowrap;
}

:deep(.results-table .badge),
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

.row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.table-btn {
  height: 20px !important;
  min-height: 20px !important;
  padding: 0 6px !important;
  font-size: 10.5px !important;
  line-height: 1 !important;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.detail-btn {
  border-color: var(--line, #e2e8e6);
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
  color: var(--accent-strong, #0ea5e9);
}
</style>
