<script setup lang="ts">
import { Check, History, Plus, RefreshCw, RotateCcw, X } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";

import { ApiError, api } from "../api";
import {
  labelDeploymentAction,
  labelFeedbackKind,
  labelFeedbackStatus,
  labelModelReleaseStatus,
} from "../labels";
import type {
  FeedbackRecord,
  HardSampleManifest,
  ModelDeploymentEvent,
  ModelPackage,
  ModelRelease,
  ModelProvenance,
  ResultPage,
  Run,
  RunPage,
} from "../types";

type Tab = "feedback" | "manifests" | "releases";

const tab = ref<Tab>("feedback");
const feedback = ref<FeedbackRecord[]>([]);
const manifests = ref<HardSampleManifest[]>([]);
const releases = ref<ModelRelease[]>([]);
const events = ref<ModelDeploymentEvent[]>([]);
const models = ref<ModelPackage[]>([]);
const runs = ref<Run[]>([]);
const traceModels = ref<ModelProvenance[]>([]);
const selectedModelKey = ref("");
const selectedFeedback = ref<string[]>([]);
const loading = ref(false);
const error = ref("");

const feedbackForm = reactive({
  kind: "false_negative",
  run_id: "",
  model_id: "",
  model_version: "",
  correction: "{}",
  authorized_for_training: false,
  deidentified: false,
});
const manifestForm = reactive({
  dataset_id: "",
  version: "1.0.0",
  label_schema: "scenara.feedback.correction.v1",
  split: "train" as "train" | "validation" | "test",
});
const releaseForm = reactive({ package_key: "", evidence_refs: "" });

const approvedFeedback = computed(() => feedback.value.filter((item) => item.status === "approved"));
const selectedPackage = computed(() => models.value.find((item) => `${item.model_id}@${item.version}` === releaseForm.package_key));

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [feedbackRows, manifestRows, releaseRows, eventRows, modelRows, runPage] = await Promise.all([
      api<FeedbackRecord[]>("/api/v1/feedback"),
      api<HardSampleManifest[]>("/api/v1/hard-sample-manifests"),
      api<ModelRelease[]>("/api/v1/model-releases"),
      api<ModelDeploymentEvent[]>("/api/v1/model-deployment-events?limit=100"),
      api<ModelPackage[]>("/api/v1/models"),
      api<RunPage>("/api/v1/runs?status=completed&limit=100"),
    ]);
    feedback.value = feedbackRows;
    manifests.value = manifestRows;
    releases.value = releaseRows;
    events.value = eventRows;
    models.value = modelRows;
    runs.value = runPage.items;
  } catch (caught) {
    showError(caught);
  } finally {
    loading.value = false;
  }
}

function showError(caught: unknown): void {
  error.value = caught instanceof ApiError ? caught.message : "操作失败，请检查输入后重试";
}

async function selectRun(): Promise<void> {
  traceModels.value = [];
  selectedModelKey.value = "";
  feedbackForm.model_id = "";
  feedbackForm.model_version = "";
  if (!feedbackForm.run_id) return;
  try {
    const page = await api<ResultPage>(`/api/v1/runs/${encodeURIComponent(feedbackForm.run_id)}/result?unit_limit=1`);
    traceModels.value = page.result.models;
  } catch (caught) {
    showError(caught);
  }
}

function selectModel(): void {
  const model = traceModels.value.find((item) => `${item.model_id}@${item.version}` === selectedModelKey.value);
  feedbackForm.model_id = model?.model_id ?? "";
  feedbackForm.model_version = model?.version ?? "";
}

async function submitFeedback(): Promise<void> {
  error.value = "";
  try {
    await api<FeedbackRecord>("/api/v1/feedback", {
      method: "POST",
      body: JSON.stringify({
        ...feedbackForm,
        correction: JSON.parse(feedbackForm.correction) as Record<string, unknown>,
      }),
    });
    Object.assign(feedbackForm, {
      run_id: "", model_id: "", model_version: "", correction: "{}",
      authorized_for_training: false, deidentified: false,
    });
    selectedModelKey.value = "";
    traceModels.value = [];
    await refresh();
  } catch (caught) {
    showError(caught);
  }
}

async function review(item: FeedbackRecord, status: "approved" | "rejected"): Promise<void> {
  try {
    await api<FeedbackRecord>(`/api/v1/feedback/${encodeURIComponent(item.feedback_id)}/review`, {
      method: "POST",
      body: JSON.stringify({ status, notes: status === "approved" ? "已核验授权与脱敏状态" : "不符合训练数据要求" }),
    });
    await refresh();
  } catch (caught) { showError(caught); }
}

async function createManifest(): Promise<void> {
  try {
    await api<HardSampleManifest>("/api/v1/hard-sample-manifests", {
      method: "POST",
      body: JSON.stringify({ ...manifestForm, feedback_ids: selectedFeedback.value }),
    });
    selectedFeedback.value = [];
    await refresh();
  } catch (caught) { showError(caught); }
}

async function createRelease(): Promise<void> {
  const model = selectedPackage.value;
  if (!model) return;
  try {
    await api<ModelRelease>("/api/v1/model-releases", {
      method: "POST",
      body: JSON.stringify({
        model_id: model.model_id,
        version: model.version,
        package_sha256: model.sha256,
        evidence_refs: releaseForm.evidence_refs.split("\n").map((item) => item.trim()).filter(Boolean),
      }),
    });
    releaseForm.package_key = "";
    releaseForm.evidence_refs = "";
    await refresh();
  } catch (caught) { showError(caught); }
}

function nextStatus(item: ModelRelease): ModelRelease["status"] | null {
  return ({ candidate: "validated", validated: "approved", approved: "active", active: "retired", retired: null } as const)[item.status];
}

async function transition(item: ModelRelease): Promise<void> {
  const status = nextStatus(item);
  if (!status) return;
  try {
    await api<ModelRelease>(`/api/v1/model-releases/${encodeURIComponent(item.model_id)}/versions/${encodeURIComponent(item.version)}/transition`, {
      method: "POST",
      body: JSON.stringify({ status, reason: `控制台迁移至${labelModelReleaseStatus(status)}` }),
    });
    await refresh();
  } catch (caught) { showError(caught); }
}

async function rollback(item: ModelRelease): Promise<void> {
  try {
    await api<ModelRelease>(`/api/v1/model-releases/${encodeURIComponent(item.model_id)}/rollback`, {
      method: "POST",
      body: JSON.stringify({ target_version: item.version, reason: "控制台执行受控回滚" }),
    });
    await refresh();
  } catch (caught) { showError(caught); }
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header"><div><h1>反馈与发布</h1><p>审核纠错反馈、导出合规难例并管理模型发布。</p></div><button class="button secondary" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新</button></div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="segmented" role="tablist" aria-label="反馈与发布视图">
      <button :class="{ active: tab === 'feedback' }" @click="tab = 'feedback'">反馈审核</button>
      <button :class="{ active: tab === 'manifests' }" @click="tab = 'manifests'">难例清单</button>
      <button :class="{ active: tab === 'releases' }" @click="tab = 'releases'">模型发布</button>
    </div>

    <template v-if="tab === 'feedback'">
      <section class="panel"><div class="panel-header"><h2>提交反馈</h2></div><div class="panel-body"><div class="form-grid">
        <label><span>问题类型</span><select v-model="feedbackForm.kind"><option value="false_positive">误检</option><option value="false_negative">漏检</option><option value="wrong_attribute">属性错误</option><option value="wrong_identity">身份匹配错误</option><option value="ocr_correction">文字更正</option></select></label>
        <label><span>已完成运行</span><select v-model="feedbackForm.run_id" @change="selectRun"><option value="">请选择</option><option v-for="item in runs" :key="item.run_id" :value="item.run_id">{{ item.run_id }}</option></select></label>
        <label><span>结果模型</span><select v-model="selectedModelKey" :disabled="!traceModels.length" @change="selectModel"><option value="">请选择</option><option v-for="item in traceModels" :key="item.model_id + item.version" :value="`${item.model_id}@${item.version}`">{{ item.model_id }} · {{ item.version }}</option></select></label>
        <label class="span-2"><span>更正内容（JSON）</span><textarea v-model="feedbackForm.correction"></textarea></label>
      </div><div class="checks"><label><input v-model="feedbackForm.authorized_for_training" type="checkbox" />已获训练授权</label><label><input v-model="feedbackForm.deidentified" type="checkbox" />已完成脱敏</label></div><button class="button primary" :disabled="!feedbackForm.run_id || !feedbackForm.model_id" @click="submitFeedback"><Plus :size="16" />提交反馈</button></div></section>
      <section class="panel spaced"><div class="panel-header"><h2>反馈队列</h2><span class="badge">{{ feedback.length }}</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>类型</th><th>运行</th><th>模型</th><th>合规</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in feedback" :key="item.feedback_id"><td><strong>{{ labelFeedbackKind(item.kind) }}</strong><div class="mono muted">{{ item.feedback_id }}</div></td><td class="mono">{{ item.run_id }}</td><td>{{ item.model_id }}<div class="mono muted">{{ item.model_version }}</div></td><td>{{ item.authorized_for_training ? '已授权' : '未授权' }} · {{ item.deidentified ? '已脱敏' : '未脱敏' }}</td><td><span class="badge" :class="item.status">{{ labelFeedbackStatus(item.status) }}</span></td><td><div v-if="item.status === 'pending'" class="row-actions"><button class="icon-button" title="批准反馈" :disabled="!item.authorized_for_training || !item.deidentified" @click="review(item, 'approved')"><Check :size="15" /></button><button class="icon-button danger-icon" title="拒绝反馈" @click="review(item, 'rejected')"><X :size="15" /></button></div></td></tr></tbody></table><div v-if="!feedback.length" class="empty">暂无反馈</div></div></section>
    </template>

    <template v-else-if="tab === 'manifests'">
      <section class="panel"><div class="panel-header"><h2>生成难例清单</h2></div><div class="panel-body"><div class="form-grid"><label><span>数据集标识</span><input v-model="manifestForm.dataset_id" /></label><label><span>版本</span><input v-model="manifestForm.version" /></label><label><span>标签规范</span><input v-model="manifestForm.label_schema" /></label><label><span>数据用途</span><select v-model="manifestForm.split"><option value="train">训练</option><option value="validation">验证</option><option value="test">测试</option></select></label></div><div class="selection-list"><label v-for="item in approvedFeedback" :key="item.feedback_id"><input v-model="selectedFeedback" type="checkbox" :value="item.feedback_id" /><span>{{ labelFeedbackKind(item.kind) }} · {{ item.run_id }}</span></label><p v-if="!approvedFeedback.length" class="muted">没有可导出的已批准反馈</p></div><button class="button primary" :disabled="!manifestForm.dataset_id || !selectedFeedback.length" @click="createManifest"><Plus :size="16" />生成清单</button></div></section>
      <section class="panel spaced"><div class="panel-header"><h2>版本化清单</h2><span class="badge">{{ manifests.length }}</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>数据集</th><th>版本</th><th>条目</th><th>SHA-256</th><th>创建时间</th></tr></thead><tbody><tr v-for="item in manifests" :key="item.manifest_id"><td><strong>{{ item.dataset_id }}</strong><div class="mono muted">{{ item.manifest_id }}</div></td><td class="mono">{{ item.version }}</td><td>{{ item.items.length }}</td><td class="mono">{{ item.sha256.slice(0, 16) }}…</td><td>{{ new Date(item.created_at * 1000).toLocaleString() }}</td></tr></tbody></table><div v-if="!manifests.length" class="empty">暂无难例清单</div></div></section>
    </template>

    <template v-else>
      <section class="panel"><div class="panel-header"><h2>登记候选版本</h2></div><div class="panel-body"><div class="form-grid"><label><span>已登记模型包</span><select v-model="releaseForm.package_key"><option value="">请选择</option><option v-for="item in models" :key="item.model_id + item.version" :value="`${item.model_id}@${item.version}`">{{ item.model_id }} · {{ item.version }}</option></select></label><label><span>证据引用（每行一个）</span><textarea v-model="releaseForm.evidence_refs"></textarea></label></div><button class="button primary" :disabled="!selectedPackage" @click="createRelease"><Plus :size="16" />登记候选版本</button></div></section>
      <section class="panel spaced"><div class="panel-header"><h2>发布版本</h2><span class="badge">{{ releases.length }}</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>模型</th><th>版本</th><th>状态</th><th>证据</th><th>操作</th></tr></thead><tbody><tr v-for="item in releases" :key="item.model_id + item.version"><td><strong>{{ item.model_id }}</strong></td><td class="mono">{{ item.version }}</td><td><span class="badge" :class="item.status">{{ labelModelReleaseStatus(item.status) }}</span></td><td><details v-if="item.evidence_refs.length"><summary>{{ item.evidence_refs.length }} 项</summary><div v-for="reference in item.evidence_refs" :key="reference" class="mono evidence-ref">{{ reference }}</div></details><span v-else class="muted">未登记</span></td><td><div class="row-actions"><button v-if="nextStatus(item)" class="button compact" :disabled="item.status === 'candidate' && !item.evidence_refs.length" :title="item.status === 'candidate' && !item.evidence_refs.length ? '登记证据后才能验证' : ''" @click="transition(item)">{{ labelModelReleaseStatus(nextStatus(item) || '') }}</button><button v-if="item.status === 'retired'" class="icon-button" title="回滚到此版本" @click="rollback(item)"><RotateCcw :size="15" /></button></div></td></tr></tbody></table><div v-if="!releases.length" class="empty">暂无发布版本</div></div></section>
      <section class="panel spaced"><div class="panel-header"><h2>部署事件</h2><History :size="16" /></div><div class="table-scroll"><table class="data-table"><thead><tr><th>操作</th><th>模型版本</th><th>状态变化</th><th>原因</th><th>时间</th></tr></thead><tbody><tr v-for="item in events" :key="item.event_id"><td>{{ labelDeploymentAction(item.action) }}</td><td>{{ item.model_id }}<div class="mono muted">{{ item.version }}</div></td><td>{{ item.from_status ? labelModelReleaseStatus(item.from_status) : '无' }} → {{ labelModelReleaseStatus(item.to_status) }}</td><td>{{ item.reason }}</td><td>{{ new Date(item.created_at * 1000).toLocaleString() }}</td></tr></tbody></table><div v-if="!events.length" class="empty">暂无部署事件</div></div></section>
    </template>
  </section>
</template>

<style scoped>
.segmented { display: inline-flex; margin-bottom: 14px; border: 1px solid var(--line); border-radius: 5px; overflow: hidden; background: #fff; }.segmented button { min-width: 112px; height: 34px; border: 0; border-right: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; }.segmented button:last-child { border-right: 0; }.segmented button.active { background: var(--teal-soft); color: var(--teal); font-weight: 700; }.spaced { margin-top: 14px; }.checks, .row-actions { display: flex; align-items: center; gap: 10px; }.checks { margin: 12px 0; }.checks label, .selection-list label { display: flex; align-items: center; gap: 7px; }.selection-list { max-height: 220px; overflow: auto; margin: 12px 0; padding: 10px; border: 1px solid var(--line); }.selection-list label { min-height: 32px; }.selection-list input, .checks input { width: 15px; min-height: 15px; }.compact { height: 30px; padding: 0 9px; font-size: 12px; }.danger-icon { color: var(--coral); }.evidence-ref { max-width: 320px; overflow-wrap: anywhere; margin-top: 5px; } textarea { min-height: 72px; } @media (max-width: 650px) { .segmented { display: grid; grid-template-columns: 1fr; width: 100%; }.segmented button { border-right: 0; border-bottom: 1px solid var(--line); }.segmented button:last-child { border-bottom: 0; } }
</style>
