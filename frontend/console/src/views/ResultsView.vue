<script setup lang="ts">
import { ChevronLeft, ChevronRight, RefreshCw, Search } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";

import { api, userFacingError } from "../api";
import { labelCapability, labelDomain, labelObjectType, labelPipeline, labelUnitType, labelWarning } from "../labels";
import type { ResultEnvelope, ResultPage, Run, RunPage } from "../types";

const runs = ref<Run[]>([]);
const runId = ref("");
const result = ref<ResultEnvelope | null>(null);
const unitOffset = ref(0);
const unitLimit = 20;
const unitTotal = ref(0);
const loading = ref(false);
const error = ref("");

const objectCount = computed(() =>
  result.value?.units.reduce((total, unit) => total + unit.objects.length, 0) ?? 0,
);

async function refreshRuns(): Promise<void> {
  const page = await api<RunPage>("/api/v1/runs?status=completed&limit=100");
  runs.value = page.items;
  const firstRun = runs.value[0];
  if (!runId.value && firstRun) runId.value = firstRun.run_id;
}

async function loadResult(offset = unitOffset.value): Promise<void> {
  if (!runId.value) return;
  loading.value = true;
  error.value = "";
  try {
    const query = new URLSearchParams({
      unit_offset: String(Math.max(0, offset)),
      unit_limit: String(unitLimit),
    });
    const page = await api<ResultPage>(
      "/api/v1/runs/" + encodeURIComponent(runId.value) + "/result?" + query.toString(),
    );
    result.value = page.result;
    unitOffset.value = page.unit_offset;
    unitTotal.value = page.unit_total;
  } catch (caught) {
    result.value = null;
    error.value = userFacingError(caught, "结果加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function initialize(): Promise<void> {
  try {
    await refreshRuns();
    await loadResult(0);
  } catch (caught) {
    error.value = userFacingError(caught, "已完成运行加载失败，请稍后重试");
  }
}

onMounted(initialize);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>结果</h1>
        <p>查看媒体单元、对象、关系、模型来源与告警。</p>
      </div>
      <button class="button secondary" :disabled="loading" @click="initialize">
        <RefreshCw :size="16" />刷新
      </button>
    </div>

    <section class="panel result-query">
      <div class="panel-body toolbar">
        <select v-model="runId" aria-label="已完成运行" @change="loadResult(0)">
          <option value="">选择已完成运行</option>
          <option v-for="run in runs" :key="run.run_id" :value="run.run_id">
            {{ labelDomain(run.domain) }} · {{ run.run_id }}
          </option>
        </select>
        <input v-model.trim="runId" aria-label="运行标识" placeholder="输入运行标识" @keyup.enter="loadResult(0)" />
        <button class="button primary" :disabled="!runId || loading" @click="loadResult(0)">
          <Search :size="16" />加载
        </button>
      </div>
    </section>

    <p v-if="error" class="callout error">{{ error }}</p>

    <template v-if="result">
      <div class="stats">
        <div class="stat teal"><span>领域</span><strong>{{ labelDomain(result.domain) }}</strong><small>{{ labelPipeline(result.pipeline.pipeline_id) }}</small></div>
        <div class="stat"><span>单元</span><strong>{{ unitTotal }}</strong><small>{{ unitOffset + 1 }}-{{ Math.min(unitOffset + unitLimit, unitTotal) }}</small></div>
        <div class="stat green"><span>对象</span><strong>{{ objectCount }}</strong><small>当前页</small></div>
        <div class="stat coral"><span>告警</span><strong>{{ result.warnings.length }}</strong><small>{{ result.models.length }} 条模型记录</small></div>
      </div>

      <div class="result-layout">
        <section class="panel">
          <div class="panel-header">
            <h2>媒体单元</h2>
            <div class="toolbar compact">
              <button class="icon-button" title="上一页" :disabled="unitOffset === 0" @click="loadResult(unitOffset - unitLimit)">
                <ChevronLeft :size="17" />
              </button>
              <button class="icon-button" title="下一页" :disabled="unitOffset + unitLimit >= unitTotal" @click="loadResult(unitOffset + unitLimit)">
                <ChevronRight :size="17" />
              </button>
            </div>
          </div>
          <div class="table-scroll">
            <table class="data-table">
              <thead><tr><th>单元</th><th>位置</th><th>尺寸</th><th>对象</th></tr></thead>
              <tbody>
                <tr v-for="unit in result.units" :key="unit.unit_id">
                  <td><strong>{{ unit.unit_id }}</strong><div class="muted">{{ labelUnitType(unit.unit_type) }}</div></td>
                  <td>{{ unit.page_number ? "第 " + unit.page_number + " 页" : (unit.pts_ms ?? 0) + " 毫秒" }}</td>
                  <td>{{ unit.width }} × {{ unit.height }}</td>
                  <td>
                    <div class="object-list">
                      <span v-for="object in unit.objects" :key="object.object_id" class="badge">
                        {{ labelObjectType(object.object_type) }}<template v-if="object.score != null"> {{ object.score.toFixed(2) }}</template>
                      </span>
                      <span v-if="!unit.objects.length" class="muted">无</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <aside class="result-aside">
          <section class="panel">
            <div class="panel-header"><h2>模型</h2></div>
            <div class="panel-body provenance">
              <div v-for="model in result.models" :key="model.capability + ':' + model.model_id">
                <span>{{ labelCapability(model.capability) }}</span>
                <strong>{{ model.model_id }}@{{ model.version }}</strong>
                <small :class="model.production_ready ? 'ok' : 'warn'">
                  {{ model.production_ready ? "生产就绪" : "开发替代" }}
                </small>
              </div>
              <div v-if="!result.models.length" class="muted">没有模型来源。</div>
            </div>
          </section>
          <section class="panel">
            <div class="panel-header"><h2>告警</h2></div>
            <div class="panel-body warning-list">
              <code v-for="warning in result.warnings" :key="warning">{{ labelWarning(warning) }}</code>
              <span v-if="!result.warnings.length" class="muted">没有告警。</span>
            </div>
          </section>
        </aside>
      </div>
    </template>
    <div v-else-if="!loading" class="empty">选择已完成运行以查看结果。</div>
  </section>
</template>

<style scoped>
.result-query { margin-bottom: 16px; }
.result-query select { min-width: min(420px, 100%); }
.result-query input { flex: 1; min-width: 220px; }
.result-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 340px); gap: 16px; align-items: start; }
.result-aside { display: grid; gap: 16px; }
.compact { flex-wrap: nowrap; }
.object-list { display: flex; flex-wrap: wrap; gap: 5px; }
.provenance { display: grid; gap: 12px; }
.provenance div { display: grid; gap: 3px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }
.provenance div:last-child { padding-bottom: 0; border-bottom: 0; }
.provenance span, .provenance small { color: var(--muted); font-size: 11px; }
.provenance strong { overflow-wrap: anywhere; font-size: 12px; }
.provenance .ok { color: var(--green); }
.provenance .warn { color: var(--amber); }
.warning-list { display: grid; gap: 7px; }
.warning-list code { overflow-wrap: anywhere; color: #7c4b08; font-size: 11px; }
@media (max-width: 980px) { .result-layout { grid-template-columns: 1fr; } }
</style>
