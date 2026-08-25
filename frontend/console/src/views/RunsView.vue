<script setup lang="ts">
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Filter,
  Play,
  RotateCcw,
} from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { useRoute, useRouter } from "vue-router";
import { api, userFacingError } from "../api";
import { labelDomain, labelPipeline, labelRunStatus } from "../labels";
import DataTable from "../components/DataTable.vue";
import type { Domain, DomainManifest, Run, RunPage, RunStatus, TableColumn } from "../types";

const PAGE_SIZE = 20;
const runs = ref<Run[]>([]);
const domains = ref<DomainManifest[]>([]);
const total = ref(0);
const offset = ref(0);
const route = useRoute();
const router = useRouter();
const routeStatus =
  typeof route.query.status === "string" ? route.query.status : "";
const status = ref<RunStatus | "">(
  [
    "queued",
    "running",
    "pausing",
    "paused",
    "completed",
    "failed",
    "cancelling",
    "cancelled",
  ].includes(routeStatus)
    ? (routeStatus as RunStatus)
    : "",
);
const routeDomain =
  typeof route.query.domain === "string" ? (route.query.domain as Domain) : "";
const domain = ref<"" | Domain>(routeDomain);
const loading = ref(false);
const error = ref("");
const autoRefresh = ref(true);
let timer: number | null = null;

const activeCount = computed(
  () =>
    runs.value.filter(
      (item) => !["completed", "failed", "cancelled"].includes(item.status),
    ).length,
);
const failedCount = computed(
  () => runs.value.filter((item) => item.status === "failed").length,
);
const completedCount = computed(
  () => runs.value.filter((item) => item.status === "completed").length,
);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset.value),
  });
  if (status.value) query.set("status", status.value);
  if (domain.value) query.set("domain", domain.value);
  try {
    const [page, manifests] = await Promise.all([
      api<RunPage>("/api/v1/runs?" + query.toString()),
      api<DomainManifest[]>("/api/v1/domains"),
    ]);
    runs.value = page.items;
    total.value = page.total;
    domains.value = manifests;
    if (page.items.length === 0 && offset.value > 0) {
      offset.value = Math.max(0, total.value - PAGE_SIZE);
      const retry = await api<RunPage>(
        "/api/v1/runs?" +
          new URLSearchParams({
            limit: String(PAGE_SIZE),
            offset: String(offset.value),
            ...(status.value ? { status: status.value } : {}),
            ...(domain.value ? { domain: domain.value } : {}),
          }).toString(),
      );
      runs.value = retry.items;
      total.value = retry.total;
    }
  } catch (caught) {
    error.value = userFacingError(caught, "运行记录加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

function scheduleRefresh(): void {
  if (timer !== null) window.clearTimeout(timer);
  timer = window.setTimeout(async () => {
    if (autoRefresh.value && activeCount.value > 0) await refresh();
    scheduleRefresh();
  }, 3000);
}

async function transition(
  run: Run,
  action: "cancel" | "pause" | "resume",
): Promise<void> {
  try {
    await api<Run>(
      "/api/v1/runs/" + encodeURIComponent(run.run_id) + "/" + action,
      { method: "POST" },
    );
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "运行状态更新失败，请稍后重试");
  }
}

function openWorkspace(run: Run): void {
  if (run.status === "completed") {
    void router.push({ path: "/results", query: { run: run.run_id } });
    return;
  }
  void router.push({ path: "/parse", query: { run: run.run_id } });
}

function domainLabel(value: Domain): string {
  return (
    domains.value.find((item) => item.domain_id === value)?.display_name ||
    labelDomain(value)
  );
}

function progressPercent(run: Run): number {
  return Math.round((run.progress ?? 0) * 100);
}

function duration(run: Run): string {
  const start = run.started_at ?? run.created_at;
  const end =
    run.completed_at ??
    (["completed", "failed", "cancelled"].includes(run.status)
      ? run.updated_at
      : Date.now() / 1000);
  const seconds = Math.max(0, end - start);
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`;
}

const columns: TableColumn<Run>[] = [
  { key: "run_id", label: "运行", class: "mono truncate" },
  { key: "domain", label: "领域" },
  { key: "status", label: "状态" },
  { key: "progress", label: "进度", class: "progress-cell" },
  { key: "pipeline", label: "流水线", class: "truncate" },
  { key: "asset_source", label: "资产/源", class: "mono truncate" },
  { key: "duration", label: "耗时" },
  { key: "actions", label: "操作" },
];

function onPageChange(nextOffset: number): void {
  offset.value = nextOffset;
  void refresh();
}

function resetFilters(): void {
  status.value = "";
  domain.value = "";
  offset.value = 0;
  void refresh();
}

function onFilterChange(): void {
  offset.value = 0;
  void refresh();
}

onMounted(async () => {
  await refresh();
  scheduleRefresh();
});
useRefresh(refresh);
onBeforeUnmount(() => {
  if (timer !== null) window.clearTimeout(timer);
});
</script>

<template>
  <section class="page">
    <div class="stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">全部运行</span>
          <div class="stat-icon-badge">
            <Activity :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-desc">当前筛选条件</div>
      </div>
      <div class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">进行中</span>
          <div class="stat-icon-badge">
            <Play :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ activeCount }}</div>
        <div class="stat-desc">排队、运行或暂停</div>
      </div>
      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">已完成</span>
          <div class="stat-icon-badge">
            <CheckCircle2 :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ completedCount }}</div>
        <div class="stat-desc">结果可查询</div>
      </div>
      <div class="stat coral">
        <div class="stat-top-row">
          <span class="stat-title">失败</span>
          <div class="stat-icon-badge">
            <AlertCircle :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ failedCount }}</div>
        <div class="stat-desc">需要排查原因</div>
      </div>
    </div>

    <section class="panel filter-panel">
      <div class="panel-body filter-bar">
        <div class="filter-controls">
          <div class="filter-heading">
            <Filter :size="15" />
            <span>筛选记录</span>
          </div>
          <select v-model="domain" aria-label="领域筛选" @change="onFilterChange">
            <option value="">全部领域</option>
            <option
              v-for="item in domains"
              :key="item.domain_id"
              :value="item.domain_id"
            >
              {{ item.display_name }}
            </option>
          </select>
          <select v-model="status" aria-label="状态筛选" @change="onFilterChange">
            <option value="">全部状态</option>
            <option value="queued">排队中</option>
            <option value="running">运行中</option>
            <option value="paused">已暂停</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
          </select>
          <button class="button secondary" @click="resetFilters">
            <RotateCcw :size="14" />重置
          </button>
        </div>
        <label class="auto-refresh-label">
          <input v-model="autoRefresh" type="checkbox" />自动刷新
        </label>
      </div>
    </section>
    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel runs-panel">
      <DataTable
        :columns="columns"
        :items="runs"
        :loading="loading"
        :total="total"
        :offset="offset"
        :page-size="PAGE_SIZE"
        :index-offset="offset"
        empty-text="暂无运行记录"
        @page-change="onPageChange"
      >
        <template #domain="{ row }">
          {{ domainLabel(row.domain) }}
        </template>
        <template #status="{ row }">
          <span class="badge" :class="row.status">{{
            labelRunStatus(row.status)
          }}</span>
        </template>
        <template #progress="{ row }">
          <div class="progress-inline">
            <div
              class="progress-track"
              role="progressbar"
              :aria-valuenow="progressPercent(row)"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <span :style="{ width: `${progressPercent(row)}%` }" />
            </div>
            <span class="progress-value">{{ progressPercent(row) }}%</span>
          </div>
        </template>
        <template #pipeline="{ row }">
          {{ labelPipeline(row.pipeline.pipeline_id) }} ·
          {{ row.pipeline.version }}
        </template>
        <template #asset_source="{ row }">
          {{ row.asset_id || row.source_id }}
        </template>
        <template #duration="{ row }">
          {{ duration(row) }}
        </template>
        <template #actions="{ row }">
          <div class="toolbar compact">
            <button class="button secondary" @click="openWorkspace(row)">
              查看<ArrowRight :size="12" />
            </button>
            <button
              class="button secondary"
              :disabled="row.status !== 'running'"
              @click="transition(row, 'pause')"
            >
              暂停
            </button>
            <button
              class="button secondary"
              :disabled="row.status !== 'paused'"
              @click="transition(row, 'resume')"
            >
              恢复
            </button>
            <button
              class="button danger"
              :disabled="
                ['completed', 'failed', 'cancelled'].includes(row.status)
              "
              @click="transition(row, 'cancel')"
            >
              {{ row.status === "cancelling" ? "强制取消" : "取消" }}
            </button>
          </div>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.stats {
  gap: 10px;
  margin-bottom: 8px;
}
.stat {
  padding: 8px 12px;
  min-height: 68px;
}
.filter-panel {
  margin-top: 8px;
}
.filter-panel .panel-body {
  padding: 6px 12px;
}
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-heading {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 650;
  color: var(--color-text);
  margin-right: 2px;
  white-space: nowrap;
}
.filter-heading svg {
  color: var(--teal);
}
.filter-controls select {
  width: 150px;
  min-width: 120px;
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  font-size: 12px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background-color: var(--color-surface);
}
.filter-controls .button {
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  font-size: 12px;
}
.runs-panel {
  margin-top: 8px;
}
.runs-panel .data-table th {
  height: 26px;
  padding: 2px 8px;
  font-size: 11px;
}
.runs-panel .data-table td {
  min-height: 26px;
  height: 26px;
  padding: 2px 8px;
  font-size: 11.5px;
  line-height: 1.25;
  vertical-align: middle;
}
.runs-panel .badge {
  min-height: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 10.5px;
  line-height: 18px;
}
.compact {
  gap: 3px;
  flex-wrap: nowrap;
}
.compact .button {
  min-height: 20px;
  height: 20px;
  padding: 0 5px;
  font-size: 10.5px;
  font-weight: 550;
  gap: 3px;
  border-radius: 3px;
}
.runs-panel .pagination {
  padding: 5px 12px;
}
.runs-panel .pagination-info {
  font-size: 11.5px;
}
.runs-panel .pagination-btn {
  height: 24px;
  min-height: 24px;
  font-size: 11px;
  padding: 0 6px;
}
.runs-panel .pagination-page-indicator {
  min-width: 24px;
  height: 24px;
  font-size: 11px;
  padding: 0 4px;
}
.auto-refresh-label {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.auto-refresh-label input[type="checkbox"] {
  width: 15px;
  height: 15px;
  margin: 0;
  cursor: pointer;
  accent-color: var(--teal);
}
.small {
  font-size: 11px;
}
.progress-cell {
  min-width: 110px;
}
.progress-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-track {
  flex: 1;
  min-width: 48px;
  height: 5px;
  overflow: hidden;
  background: #dfe6e3;
  border-radius: 3px;
}
.progress-track span {
  display: block;
  height: 100%;
  background: var(--teal);
  transition: width 0.2s ease;
}
.progress-value {
  color: var(--muted);
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  min-width: 28px;
  text-align: right;
  flex-shrink: 0;
}
.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
