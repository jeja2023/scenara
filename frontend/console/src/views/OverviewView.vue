<script setup lang="ts">
import { RefreshCw } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { DomainManifest, Pipeline, RunPage } from "../types";

const loading = ref(false);
const error = ref("");
const runs = ref<RunPage>({ items: [], offset: 0, limit: 10, total: 0 });
const domains = ref<DomainManifest[]>([]);
const pipelines = ref<Pipeline[]>([]);
const activeRuns = computed(() => runs.value.items.filter((run) => ["queued", "running", "pausing", "paused"].includes(run.status)).length);
const failedRuns = computed(() => runs.value.items.filter((run) => ["failed", "cancelled"].includes(run.status)).length);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    [runs.value, domains.value, pipelines.value] = await Promise.all([
      api<RunPage>("/api/v1/runs?limit=10"),
      api<DomainManifest[]>("/api/v1/domains"),
      api<Pipeline[]>("/api/v1/pipelines"),
    ]);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div><h1>总览</h1><p>最近运行、启用领域与 Pipeline 状态。</p></div>
      <button class="button secondary" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新</button>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="stats">
      <div class="stat teal"><span>Runs</span><strong>{{ runs.total }}</strong><small>当前项目</small></div>
      <div class="stat green"><span>Active</span><strong>{{ activeRuns }}</strong><small>队列与执行中</small></div>
      <div class="stat coral"><span>Attention</span><strong>{{ failedRuns }}</strong><small>失败或取消</small></div>
      <div class="stat"><span>Pipelines</span><strong>{{ pipelines.length }}</strong><small>{{ domains.length }} 个领域</small></div>
    </div>
    <div class="two-column">
      <section class="panel">
        <div class="panel-header"><h2>最近运行</h2><RouterLink class="button secondary" to="/runs">队列</RouterLink></div>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Run</th><th>领域</th><th>状态</th><th>Pipeline</th><th>更新时间</th></tr></thead><tbody>
          <tr v-for="run in runs.items" :key="run.run_id"><td class="mono">{{ run.run_id }}</td><td>{{ run.domain }}</td><td><span class="badge" :class="run.status">{{ run.status }}</span></td><td class="truncate">{{ run.pipeline.pipeline_id }}@{{ run.pipeline.version }}</td><td>{{ new Date(run.updated_at * 1000).toLocaleString() }}</td></tr>
        </tbody></table><div v-if="!runs.items.length" class="empty">暂无运行记录</div></div>
      </section>
      <section class="panel"><div class="panel-header"><h2>领域</h2></div><div class="panel-body">
        <div v-for="domain in domains" :key="domain.domain_id" class="domain-row"><strong>{{ domain.display_name }}</strong><span>{{ domain.capabilities.join(" · ") }}</span></div>
        <div v-if="!domains.length" class="empty">未读取到领域注册信息</div>
      </div></section>
    </div>
  </section>
</template>

<style scoped>
.domain-row { display: grid; gap: 5px; padding: 13px 0; border-bottom: 1px solid var(--line); }
.domain-row:last-child { border-bottom: 0; }
.domain-row span { color: var(--muted); font-size: 12px; }
</style>
