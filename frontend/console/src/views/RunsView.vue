<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, userFacingError } from "../api";
import { labelDomain, labelPipeline, labelRunError, labelRunStatus } from "../labels";
import type { Run, RunPage, RunStatus } from "../types";

const runs = ref<Run[]>([]);
const total = ref(0);
const status = ref<RunStatus | "">("");
const domain = ref<"" | "portrait" | "ocr">("");
const loading = ref(false);
const error = ref("");
const selected = ref<Run | null>(null);
const rawResult = ref("");

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  const query = new URLSearchParams({ limit: "100" });
  if (status.value) query.set("status", status.value);
  if (domain.value) query.set("domain", domain.value);
  try {
    const page = await api<RunPage>("/api/v1/runs?" + query.toString());
    runs.value = page.items;
    total.value = page.total;
  } catch (caught) {
    error.value = userFacingError(caught, "运行记录加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function transition(run: Run, action: "cancel" | "pause" | "resume"): Promise<void> {
  try {
    await api<Run>("/api/v1/runs/" + encodeURIComponent(run.run_id) + "/" + action, { method: "POST" });
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "运行状态更新失败，请稍后重试");
  }
}

async function openResult(run: Run): Promise<void> {
  selected.value = run;
  rawResult.value = "";
  try {
    const page = await api<unknown>("/api/v1/runs/" + encodeURIComponent(run.run_id) + "/result");
    rawResult.value = JSON.stringify(page, null, 2);
  } catch (caught) {
    error.value = userFacingError(caught, "运行结果加载失败，请稍后重试");
  }
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div><h1>运行</h1><p>队列、生命周期与结果引用。</p></div>
      <button class="button secondary" :disabled="loading" @click="refresh">刷新</button>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>筛选</h2><span class="badge">{{ total }}</span></div>
      <div class="panel-body">
        <div class="toolbar">
          <select v-model="domain" @change="refresh"><option value="">全部领域</option><option value="portrait">人像</option><option value="ocr">OCR 文档</option></select>
          <select v-model="status" @change="refresh"><option value="">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select>
          <button class="button secondary" @click="status = ''; domain = ''; refresh()">重置</button>
        </div>
      </div>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <section class="panel runs-panel">
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>运行</th><th>领域</th><th>状态</th><th>流水线</th><th>资产/源</th><th>时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="run in runs" :key="run.run_id">
              <td class="mono">{{ run.run_id }}</td>
              <td>{{ labelDomain(run.domain) }}</td>
              <td><span class="badge" :class="run.status">{{ labelRunStatus(run.status) }}</span><div v-if="run.error_code" class="muted">{{ labelRunError(run.error_code) }}</div></td>
              <td class="truncate">{{ labelPipeline(run.pipeline.pipeline_id) }} · {{ run.pipeline.version }}</td>
              <td class="mono truncate">{{ run.asset_id || run.source_id }}</td>
              <td>{{ new Date(run.created_at * 1000).toLocaleString() }}</td>
              <td>
                <div class="toolbar compact">
                  <button class="button secondary" :disabled="run.status !== 'completed'" @click="openResult(run)">结果</button>
                  <button class="button secondary" :disabled="run.status !== 'running'" @click="transition(run, 'pause')">暂停</button>
                  <button class="button secondary" :disabled="run.status !== 'paused'" @click="transition(run, 'resume')">恢复</button>
                  <button class="button danger" :disabled="['completed', 'failed', 'cancelled'].includes(run.status)" @click="transition(run, 'cancel')">取消</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!runs.length" class="empty">暂无运行记录</div>
      </div>
    </section>
    <dialog :open="!!selected" class="modal result-modal">
      <form method="dialog">
        <div class="modal-header"><div><h2>{{ selected?.run_id }}</h2><p>{{ selected ? labelRunStatus(selected.status) : "" }}</p></div><button class="icon-button" title="关闭" aria-label="关闭" @click="selected = null">×</button></div>
        <pre v-if="rawResult">{{ rawResult }}</pre><div v-else class="empty">暂无结果</div>
      </form>
    </dialog>
  </section>
</template>

<style scoped>
.runs-panel { margin-top: 14px; }
.compact { gap: 5px; flex-wrap: nowrap; }
.result-modal { width: min(880px, calc(100% - 32px)); }
pre { max-height: 68vh; overflow: auto; padding: 12px; background: #101816; color: #dbe6e2; border-radius: 4px; font-size: 11px; }
</style>
