<script setup lang="ts">
import { ArrowRight } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { useRoute, useRouter } from "vue-router";
import { api, userFacingError } from "../api";
import {
  labelDomain,
  labelPipeline,
  labelRunError,
  labelRunStatus,
  labelTerminationReason,
} from "../labels";
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
        <span>全部运行</span><strong>{{ total }}</strong
        ><small>当前筛选条件</small>
      </div>
      <div class="stat">
        <span>进行中</span><strong>{{ activeCount }}</strong
        ><small>排队、运行或暂停</small>
      </div>
      <div class="stat green">
        <span>已完成</span><strong>{{ completedCount }}</strong
        ><small>结果可查询</small>
      </div>
      <div class="stat coral">
        <span>失败</span><strong>{{ failedCount }}</strong
        ><small>需要排查原因</small>
      </div>
    </div>

    <div class="panel filter-panel">
      <div class="panel-header">
        <h2>筛选记录</h2>
        <label class="auto-refresh-label"
          ><input v-model="autoRefresh" type="checkbox" />自动刷新</label
        >
      </div>
      <div class="panel-body">
        <div class="toolbar">
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
          <button
            class="button secondary"
            @click="
              status = '';
              domain = '';
              refresh();
            "
          >
            重置
          </button>
        </div>
      </div>
    </div>
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
                <div v-if="run.error_code" class="muted small">
                  {{ labelRunError(run.error_code) }}
                </div>
                <div v-else-if="run.termination_reason" class="muted small">
                  {{ labelTerminationReason(run.termination_reason) }}
                </div>
              </td>
              <td class="progress-cell">
                <div
                  class="progress-track"
                  role="progressbar"
                  :aria-valuenow="progressPercent(run)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                >
                  <span :style="{ width: `${progressPercent(run)}%` }" />
                </div>
                <small>{{ progressPercent(run) }}%</small>
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
                    查看<ArrowRight :size="14" />
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
                    取消
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
.runs-panel {
  margin-top: 14px;
}
.compact {
  gap: 5px;
  flex-wrap: nowrap;
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
  min-width: 92px;
}
.progress-track {
  height: 6px;
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
.progress-cell small {
  display: block;
  margin-top: 3px;
  color: var(--muted);
  font-size: 11px;
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
