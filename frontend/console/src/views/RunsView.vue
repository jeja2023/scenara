<script setup lang="ts">
import { Activity, AlertCircle, ArrowRight, CheckCircle2, Filter, Play, RotateCcw } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { useRoute, useRouter } from "vue-router";
import { api, userFacingError } from "../api";
import { labelDomain, labelPipeline, labelRunStatus } from "../labels";
import type { Domain, DomainManifest, Run, RunPage, RunStatus } from "../types";

const runs = ref<Run[]>([]);
const domains = ref<DomainManifest[]>([]);
const total = ref(0);
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
  const query = new URLSearchParams({ limit: "100" });
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

function resetFilters(): void {
  status.value = "";
  domain.value = "";
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
          <select v-model="domain" aria-label="领域筛选" @change="refresh">
            <option value="">全部领域</option>
            <option
              v-for="item in domains"
              :key="item.domain_id"
              :value="item.domain_id"
            >
              {{ item.display_name }}
            </option>
          </select>
          <select v-model="status" aria-label="状态筛选" @change="refresh">
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
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>运行</th>
              <th>领域</th>
              <th>状态</th>
              <th>进度</th>
              <th>流水线</th>
              <th>资产/源</th>
              <th>耗时</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(run, index) in runs" :key="run.run_id">
              <td class="muted">{{ index + 1 }}</td>
              <td class="mono truncate">{{ run.run_id }}</td>
              <td>{{ domainLabel(run.domain) }}</td>
              <td>
                <span class="badge" :class="run.status">{{
                  labelRunStatus(run.status)
                }}</span>
              </td>
              <td class="progress-cell">
                <div class="progress-inline">
                  <div
                    class="progress-track"
                    role="progressbar"
                    :aria-valuenow="progressPercent(run)"
                    aria-valuemin="0"
                    aria-valuemax="100"
                  >
                    <span :style="{ width: `${progressPercent(run)}%` }" />
                  </div>
                  <span class="progress-value"
                    >{{ progressPercent(run) }}%</span
                  >
                </div>
              </td>
              <td class="truncate">
                {{ labelPipeline(run.pipeline.pipeline_id) }} ·
                {{ run.pipeline.version }}
              </td>
              <td class="mono truncate">{{ run.asset_id || run.source_id }}</td>
              <td>{{ duration(run) }}</td>
              <td>
                <div class="toolbar compact">
                  <button class="button secondary" @click="openWorkspace(run)">
                    查看<ArrowRight :size="12" />
                  </button>
                  <button
                    class="button secondary"
                    :disabled="run.status !== 'running'"
                    @click="transition(run, 'pause')"
                  >
                    暂停
                  </button>
                  <button
                    class="button secondary"
                    :disabled="run.status !== 'paused'"
                    @click="transition(run, 'resume')"
                  >
                    恢复
                  </button>
                  <button
                    class="button danger"
                    :disabled="
                      ['completed', 'failed', 'cancelled'].includes(run.status)
                    "
                    @click="transition(run, 'cancel')"
                  >
                    {{ run.status === "cancelling" ? "强制取消" : "取消" }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!runs.length" class="empty">暂无运行记录</div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.filter-panel {
  margin-top: 14px;
}
.filter-panel .panel-body {
  padding: 10px 16px;
}
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.filter-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.filter-heading {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 650;
  color: var(--color-text);
  margin-right: 2px;
  white-space: nowrap;
}
.filter-heading svg {
  color: var(--teal);
}
.filter-controls select {
  width: 170px;
  min-width: 130px;
  height: 34px;
  min-height: 34px;
  padding: 0 10px;
  font-size: 13px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background-color: var(--color-surface);
}
.filter-controls .button {
  height: 34px;
  min-height: 34px;
}
.runs-panel {
  margin-top: 14px;
}
.runs-panel .data-table th {
  height: 32px;
  padding: 4px 10px;
}
.runs-panel .data-table td {
  min-height: 34px;
  padding: 5px 10px;
  vertical-align: middle;
}
.runs-panel .badge {
  min-height: 20px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 20px;
}
.compact {
  gap: 4px;
  flex-wrap: nowrap;
}
.compact .button {
  min-height: 24px;
  height: 24px;
  padding: 0 7px;
  font-size: 11.5px;
  font-weight: 550;
  gap: 4px;
  border-radius: 4px;
}
@media (max-width: 900px) {
  .filter-controls .button,
  .filter-controls select,
  .compact .button {
    min-height: 44px;
    height: 44px;
  }
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
