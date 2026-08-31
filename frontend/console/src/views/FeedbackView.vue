<script setup lang="ts">
import {
  Check,
  FileSpreadsheet,
  History,
  MessageSquare,
  Plus,
  Rocket,
  RotateCcw,
  X,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";
import {
  labelDeploymentAction,
  labelFeedbackKind,
  labelFeedbackStatus,
  labelModelName,
  labelModelReleaseStatus,
  labelSystemReason,
} from "../labels";
import DataTable from "../components/DataTable.vue";
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
  TableColumn,
} from "../types";

type Tab = "feedback" | "manifests" | "releases";

const feedbackColumns: TableColumn<FeedbackRecord>[] = [
  { key: "kind", label: "问题类型", width: "150px" },
  { key: "run_id", label: "运行标识", class: "mono", width: "160px" },
  { key: "model", label: "关联模型", width: "200px" },
  { key: "compliance", label: "合规状态", width: "150px" },
  { key: "status", label: "审核状态", width: "110px" },
  { key: "actions", label: "操作", width: "90px" },
];

const manifestColumns: TableColumn<HardSampleManifest>[] = [
  { key: "dataset", label: "数据集", width: "180px" },
  { key: "version", label: "版本", class: "mono", width: "100px" },
  { key: "items", label: "条目数", width: "90px" },
  { key: "sha256", label: "校验指纹 (SHA256)", class: "mono", width: "180px" },
  { key: "created_at", label: "生成时间" },
];

const releaseColumns: TableColumn<ModelRelease>[] = [
  { key: "model_id", label: "模型名称", width: "220px" },
  { key: "version", label: "版本", class: "mono", width: "100px" },
  { key: "status", label: "准入状态", width: "110px" },
  { key: "evidence_refs", label: "证据引用", width: "160px" },
  { key: "actions", label: "操作", width: "120px" },
];

const eventColumns: TableColumn<ModelDeploymentEvent>[] = [
  { key: "action", label: "操作", width: "130px" },
  { key: "model_version", label: "模型与版本", width: "220px" },
  { key: "status_change", label: "状态迁移", width: "180px" },
  { key: "reason", label: "迁移原因", width: "180px" },
  { key: "created_at", label: "记录时间" },
];

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

const feedbackPageSize = ref(10);
const manifestPageSize = ref(10);
const releasePageSize = ref(10);
const eventPageSize = ref(10);

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

const approvedFeedback = computed(() =>
  feedback.value.filter((item) => item.status === "approved"),
);
const selectedPackage = computed(() =>
  models.value.find(
    (item) => `${item.model_id}@${item.version}` === releaseForm.package_key,
  ),
);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [
      feedbackRows,
      manifestRows,
      releaseRows,
      eventRows,
      modelRows,
      runPage,
    ] = await Promise.all([
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
  error.value = userFacingError(caught, "操作失败，请检查输入后重试");
}

async function selectRun(): Promise<void> {
  traceModels.value = [];
  selectedModelKey.value = "";
  feedbackForm.model_id = "";
  feedbackForm.model_version = "";
  if (!feedbackForm.run_id) return;
  try {
    const page = await api<ResultPage>(
      `/api/v1/runs/${encodeURIComponent(feedbackForm.run_id)}/result?unit_limit=1`,
    );
    traceModels.value = page.result.models;
  } catch (caught) {
    showError(caught);
  }
}

function selectModel(): void {
  const model = traceModels.value.find(
    (item) => `${item.model_id}@${item.version}` === selectedModelKey.value,
  );
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
        correction: JSON.parse(feedbackForm.correction) as Record<
          string,
          unknown
        >,
      }),
    });
    Object.assign(feedbackForm, {
      run_id: "",
      model_id: "",
      model_version: "",
      correction: "{}",
      authorized_for_training: false,
      deidentified: false,
    });
    selectedModelKey.value = "";
    traceModels.value = [];
    await refresh();
  } catch (caught) {
    showError(caught);
  }
}

async function review(
  item: FeedbackRecord,
  status: "approved" | "rejected",
): Promise<void> {
  try {
    await api<FeedbackRecord>(
      `/api/v1/feedback/${encodeURIComponent(item.feedback_id)}/review`,
      {
        method: "POST",
        body: JSON.stringify({
          status,
          notes:
            status === "approved"
              ? "已核验授权与脱敏状态"
              : "不符合训练数据要求",
        }),
      },
    );
    await refresh();
  } catch (caught) {
    showError(caught);
  }
}

async function createManifest(): Promise<void> {
  try {
    await api<HardSampleManifest>("/api/v1/hard-sample-manifests", {
      method: "POST",
      body: JSON.stringify({
        ...manifestForm,
        feedback_ids: selectedFeedback.value,
      }),
    });
    selectedFeedback.value = [];
    await refresh();
  } catch (caught) {
    showError(caught);
  }
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
        evidence_refs: releaseForm.evidence_refs
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    });
    releaseForm.package_key = "";
    releaseForm.evidence_refs = "";
    await refresh();
  } catch (caught) {
    showError(caught);
  }
}

function nextStatus(item: ModelRelease): ModelRelease["status"] | null {
  return (
    {
      candidate: "validated",
      validated: "approved",
      approved: "active",
      active: "retired",
      retired: null,
    } as const
  )[item.status];
}

async function transition(item: ModelRelease): Promise<void> {
  const status = nextStatus(item);
  if (!status) return;
  try {
    await api<ModelRelease>(
      `/api/v1/model-releases/${encodeURIComponent(item.model_id)}/versions/${encodeURIComponent(item.version)}/transition`,
      {
        method: "POST",
        body: JSON.stringify({
          status,
          reason: `控制台迁移至${labelModelReleaseStatus(status)}`,
        }),
      },
    );
    await refresh();
  } catch (caught) {
    showError(caught);
  }
}

async function rollback(item: ModelRelease): Promise<void> {
  try {
    await api<ModelRelease>(
      `/api/v1/model-releases/${encodeURIComponent(item.model_id)}/rollback`,
      {
        method: "POST",
        body: JSON.stringify({
          target_version: item.version,
          reason: "控制台执行受控回滚",
        }),
      },
    );
    await refresh();
  } catch (caught) {
    showError(caught);
  }
}

function formatTime(epoch: number): string {
  if (!epoch) return "-";
  const d = new Date(epoch * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const year = d.getFullYear();
  const month = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const hours = pad(d.getHours());
  const minutes = pad(d.getMinutes());
  const seconds = pad(d.getSeconds());
  return `${year}/${month}/${day} ${hours}:${minutes}:${seconds}`;
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <!-- 顶部统一 Tab 切换栏 -->
    <div class="tabs-header-bar">
      <div class="domain-tabs">
        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: tab === 'feedback' }"
          @click="tab = 'feedback'"
        >
          <MessageSquare :size="13" />
          <span>反馈审核</span>
          <span class="tab-badge">{{ feedback.length }}</span>
        </button>
        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: tab === 'manifests' }"
          @click="tab = 'manifests'"
        >
          <FileSpreadsheet :size="13" />
          <span>难例清单</span>
          <span class="tab-badge">{{ manifests.length }}</span>
        </button>
        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: tab === 'releases' }"
          @click="tab = 'releases'"
        >
          <Rocket :size="13" />
          <span>模型发布</span>
          <span class="tab-badge">{{ releases.length }}</span>
        </button>
      </div>
    </div>

    <!-- 子视图 1：反馈审核 -->
    <template v-if="tab === 'feedback'">
      <!-- 提交反馈表单面板 -->
      <section class="panel form-panel">
        <div class="panel-header">
          <h2>提交运行更正反馈</h2>
        </div>
        <div class="panel-body">
          <div class="form-grid">
            <label class="form-field">
              <span class="field-label">问题类型</span>
              <select v-model="feedbackForm.kind" class="field-input">
                <option value="false_positive">误检</option>
                <option value="false_negative">漏检</option>
                <option value="wrong_attribute">属性错误</option>
                <option value="wrong_identity">身份匹配错误</option>
                <option value="ocr_correction">文字更正</option>
                <option value="action_correction">动作更正</option>
                <option value="temporal_correction">时序区间更正</option>
                <option value="style_correction">服装风格更正</option>
                <option value="character_correction">角色更正</option>
                <option value="accessory_correction">配饰更正</option>
              </select>
            </label>
            <label class="form-field">
              <span class="field-label">已完成运行</span>
              <select v-model="feedbackForm.run_id" class="field-input" @change="selectRun">
                <option value="">请选择运行记录</option>
                <option
                  v-for="item in runs"
                  :key="item.run_id"
                  :value="item.run_id"
                >
                  {{ item.run_id }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="field-label">关联结果模型</span>
              <select
                v-model="selectedModelKey"
                class="field-input"
                :disabled="!traceModels.length"
                @change="selectModel"
              >
                <option value="">请选择模型</option>
                <option
                  v-for="item in traceModels"
                  :key="item.model_id + item.version"
                  :value="`${item.model_id}@${item.version}`"
                >
                  {{ labelModelName(item.model_id) }} (v{{ item.version }})
                </option>
              </select>
            </label>
            <label class="form-field span-3">
              <span class="field-label">更正内容 (JSON)</span>
              <textarea v-model="feedbackForm.correction" class="field-textarea"></textarea>
            </label>
          </div>
          <div class="form-footer">
            <div class="checks">
              <label class="checkbox-label">
                <input
                  v-model="feedbackForm.authorized_for_training"
                  type="checkbox"
                  class="checkbox-input"
                />已获训练授权
              </label>
              <label class="checkbox-label">
                <input
                  v-model="feedbackForm.deidentified"
                  type="checkbox"
                  class="checkbox-input"
                />已完成脱敏
              </label>
            </div>
            <button
              class="button primary submit-btn"
              :disabled="!feedbackForm.run_id || !feedbackForm.model_id"
              @click="submitFeedback"
            >
              <Plus :size="14" />提交反馈
            </button>
          </div>
        </div>
      </section>

      <!-- 反馈队列数据表格 -->
      <section class="panel table-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>反馈审核队列</h2>
            <span class="badge">{{ feedback.length }}</span>
          </div>
        </div>
        <DataTable
          :columns="feedbackColumns"
          :items="feedback"
          :page-size="feedbackPageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无反馈数据"
        >
          <!-- 1. 类型 -->
          <template #kind="{ row }">
            <span class="single-line-text bold" :title="`ID: ${row.feedback_id}`">
              {{ labelFeedbackKind(row.kind) }}
            </span>
          </template>

          <!-- 2. 运行 -->
          <template #run_id="{ row }">
            <span class="single-line-text mono" :title="row.run_id">{{ row.run_id }}</span>
          </template>

          <!-- 3. 模型 -->
          <template #model="{ row }">
            <span class="single-line-text" :title="`${row.model_id} (v${row.model_version})`">
              {{ labelModelName(row.model_id) }}
            </span>
          </template>

          <!-- 4. 合规 -->
          <template #compliance="{ row }">
            <span class="single-line-text compliance-text">
              <span :class="row.authorized_for_training ? 'text-success' : 'text-muted'">{{ row.authorized_for_training ? '已授权' : '未授权' }}</span>
              <span class="dot-sep">·</span>
              <span :class="row.deidentified ? 'text-success' : 'text-muted'">{{ row.deidentified ? '已脱敏' : '未脱敏' }}</span>
            </span>
          </template>

          <!-- 5. 状态 -->
          <template #status="{ row }">
            <span class="badge status-badge" :class="row.status === 'approved' ? 'active' : row.status === 'rejected' ? 'error-badge' : ''">
              <span class="status-dot" :class="row.status === 'approved' ? 'dot-active' : row.status === 'rejected' ? 'dot-error' : 'dot-dev'" />
              {{ labelFeedbackStatus(row.status) }}
            </span>
          </template>

          <!-- 6. 操作 -->
          <template #actions="{ row }">
            <div v-if="row.status === 'pending'" class="row-actions">
              <button
                class="icon-button success-btn"
                title="批准反馈"
                :disabled="!row.authorized_for_training || !row.deidentified"
                @click="review(row, 'approved')"
              >
                <Check :size="13" />
              </button>
              <button
                class="icon-button danger-btn"
                title="拒绝反馈"
                @click="review(row, 'rejected')"
              >
                <X :size="13" />
              </button>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </DataTable>
      </section>
    </template>

    <!-- 子视图 2：难例清单 -->
    <template v-else-if="tab === 'manifests'">
      <!-- 生成难例清单表单 -->
      <section class="panel form-panel">
        <div class="panel-header">
          <h2>生成难例清单</h2>
        </div>
        <div class="panel-body">
          <div class="form-grid-4">
            <label class="form-field">
              <span class="field-label">数据集标识</span>
              <input v-model="manifestForm.dataset_id" class="field-input" placeholder="如 hard_samples_2026" />
            </label>
            <label class="form-field">
              <span class="field-label">版本号</span>
              <input v-model="manifestForm.version" class="field-input" placeholder="1.0.0" />
            </label>
            <label class="form-field">
              <span class="field-label">标签规范</span>
              <input v-model="manifestForm.label_schema" class="field-input" />
            </label>
            <label class="form-field">
              <span class="field-label">数据用途</span>
              <select v-model="manifestForm.split" class="field-input">
                <option value="train">训练 (train)</option>
                <option value="validation">验证 (validation)</option>
                <option value="test">测试 (test)</option>
              </select>
            </label>
          </div>
          <div class="manifest-selection-box">
            <div class="selection-title">选择要纳入的已批准反馈条目：</div>
            <div v-if="approvedFeedback.length" class="selection-list">
              <label v-for="item in approvedFeedback" :key="item.feedback_id" class="manifest-item-label">
                <input
                  v-model="selectedFeedback"
                  type="checkbox"
                  class="checkbox-input"
                  :value="item.feedback_id"
                />
                <span class="single-line-text">{{ labelFeedbackKind(item.kind) }} · {{ item.run_id }}</span>
              </label>
            </div>
            <p v-else class="text-muted empty-tip">暂无已批准且可导出的反馈数据</p>
          </div>
          <div class="form-footer">
            <button
              class="button primary submit-btn"
              :disabled="!manifestForm.dataset_id || !selectedFeedback.length"
              @click="createManifest"
            >
              <Plus :size="14" />生成难例清单 ({{ selectedFeedback.length }})
            </button>
          </div>
        </div>
      </section>

      <!-- 难例清单数据表格 -->
      <section class="panel table-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>版本化难例清单</h2>
            <span class="badge">{{ manifests.length }}</span>
          </div>
        </div>
        <DataTable
          :columns="manifestColumns"
          :items="manifests"
          :page-size="manifestPageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无难例清单"
        >
          <!-- 1. 数据集 -->
          <template #dataset="{ row }">
            <span class="single-line-text bold" :title="`ID: ${row.manifest_id}`">
              {{ row.dataset_id }}
            </span>
          </template>

          <!-- 2. 版本 -->
          <template #version="{ row }">
            <span class="mono">v{{ row.version }}</span>
          </template>

          <!-- 3. 条目 -->
          <template #items="{ row }">
            <span>{{ row.items.length }} 条</span>
          </template>

          <!-- 4. SHA256 -->
          <template #sha256="{ row }">
            <span class="mono" :title="row.sha256">{{ row.sha256.slice(0, 16) }}…</span>
          </template>

          <!-- 5. 创建时间 -->
          <template #created_at="{ row }">
            <span class="mono time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </DataTable>
      </section>
    </template>

    <!-- 子视图 3：模型发布 -->
    <template v-else>
      <!-- 登记候选版本表单 -->
      <section class="panel form-panel">
        <div class="panel-header">
          <h2>登记模型候选版本</h2>
        </div>
        <div class="panel-body">
          <div class="form-grid-2">
            <label class="form-field">
              <span class="field-label">已登记模型包</span>
              <select v-model="releaseForm.package_key" class="field-input">
                <option value="">请选择模型包</option>
                <option
                  v-for="item in models"
                  :key="item.model_id + item.version"
                  :value="`${item.model_id}@${item.version}`"
                >
                  {{ labelModelName(item.model_id) }} (v{{ item.version }})
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="field-label">证据引用 (每行一条)</span>
              <textarea v-model="releaseForm.evidence_refs" class="field-textarea" placeholder="如 s3://evidence/eval_report_v1.json"></textarea>
            </label>
          </div>
          <div class="form-footer">
            <button
              class="button primary submit-btn"
              :disabled="!selectedPackage"
              @click="createRelease"
            >
              <Plus :size="14" />登记候选版本
            </button>
          </div>
        </div>
      </section>

      <!-- 发布版本数据表格 -->
      <section class="panel table-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>发布版本列表</h2>
            <span class="badge">{{ releases.length }}</span>
          </div>
        </div>
        <DataTable
          :columns="releaseColumns"
          :items="releases"
          :page-size="releasePageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无发布版本"
        >
          <!-- 1. 模型 -->
          <template #model_id="{ row }">
            <span class="single-line-text bold" :title="row.model_id">{{ labelModelName(row.model_id) }}</span>
          </template>

          <!-- 2. 版本 -->
          <template #version="{ row }">
            <span class="mono">v{{ row.version }}</span>
          </template>

          <!-- 3. 状态 -->
          <template #status="{ row }">
            <span class="badge status-badge" :class="row.status === 'active' ? 'active' : row.status === 'retired' ? 'warn-badge' : ''">
              <span class="status-dot" :class="row.status === 'active' ? 'dot-active' : row.status === 'retired' ? 'dot-warn' : 'dot-dev'" />
              {{ labelModelReleaseStatus(row.status) }}
            </span>
          </template>

          <!-- 4. 证据引用 -->
          <template #evidence_refs="{ row }">
            <span v-if="row.evidence_refs.length" class="single-line-text mono" :title="row.evidence_refs.join('\n')">
              {{ row.evidence_refs.length }} 项证据
            </span>
            <span v-else class="text-muted">未登记</span>
          </template>

          <!-- 5. 操作 -->
          <template #actions="{ row }">
            <div class="row-actions">
              <button
                v-if="nextStatus(row)"
                class="button secondary table-action-btn"
                :disabled="row.status === 'candidate' && !row.evidence_refs.length"
                :title="row.status === 'candidate' && !row.evidence_refs.length ? '登记证据后才能验证' : ''"
                @click="transition(row)"
              >
                推进至{{ labelModelReleaseStatus(nextStatus(row) || "") }}
              </button>
              <button
                v-if="row.status === 'retired'"
                class="icon-button table-action-btn"
                title="回滚到此版本"
                @click="rollback(row)"
              >
                <RotateCcw :size="12" />
              </button>
            </div>
          </template>
        </DataTable>
      </section>

      <!-- 部署事件历史数据表格 -->
      <section class="panel table-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>部署审计事件</h2>
            <span class="badge">{{ events.length }}</span>
          </div>
          <History :size="14" class="text-muted" />
        </div>
        <DataTable
          :columns="eventColumns"
          :items="events"
          :page-size="eventPageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无部署事件"
        >
          <!-- 1. 操作 -->
          <template #action="{ row }">
            <span class="single-line-text bold">{{ labelDeploymentAction(row.action) }}</span>
          </template>

          <!-- 2. 模型版本 -->
          <template #model_version="{ row }">
            <span class="single-line-text" :title="`${row.model_id} (v${row.version})`">
              {{ labelModelName(row.model_id) }} · <span class="mono">v{{ row.version }}</span>
            </span>
          </template>

          <!-- 3. 状态变化 -->
          <template #status_change="{ row }">
            <span class="single-line-text">
              {{ row.from_status ? labelModelReleaseStatus(row.from_status) : "无" }}
              <span class="arrow-sep">→</span>
              <strong>{{ labelModelReleaseStatus(row.to_status) }}</strong>
            </span>
          </template>

          <!-- 4. 原因 -->
          <template #reason="{ row }">
            <span class="single-line-text text-muted">{{ labelSystemReason(row.reason) }}</span>
          </template>

          <!-- 5. 时间 -->
          <template #created_at="{ row }">
            <span class="mono time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </DataTable>
      </section>
    </template>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 顶部统一样式的分类 Tabs 导航条 */
.tabs-header-bar {
  display: flex;
  align-items: center;
  margin-bottom: 2px;
}

.domain-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
}

.domain-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.domain-tab-btn:hover {
  color: var(--graphite, #17211f);
  background: rgba(255, 255, 255, 0.6);
}

.domain-tab-btn.active {
  color: var(--color-accent-hover, #065e67);
  background: var(--color-accent-soft, #e4f1f1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 16px;
  min-width: 16px;
  padding: 0 4px;
  border-radius: 10px;
  font-size: 10.5px;
  background: rgba(0, 0, 0, 0.06);
  color: inherit;
}

/* 表单面板通用样式 */
.form-panel {
  padding: 12px 14px;
  background: #ffffff;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-header h2 {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin: 0;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 10px;
}

.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 12px;
  margin-bottom: 10px;
}

.form-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 10px;
}

.span-3 {
  grid-column: span 3;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.field-input {
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
  transition: all 0.15s ease;
}

.field-input:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.field-textarea {
  height: 60px;
  padding: 6px 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  font-family: var(--font-mono, monospace);
  outline: none;
  box-sizing: border-box;
  resize: vertical;
  transition: all 0.15s ease;
}

.field-textarea:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.form-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  flex-wrap: wrap;
  gap: 10px;
}

.checks {
  display: flex;
  align-items: center;
  gap: 14px;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--graphite, #17211f);
  cursor: pointer;
}

.checkbox-input {
  cursor: pointer;
}

.submit-btn {
  height: 28px;
  padding: 0 12px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 难例选择列表 */
.manifest-selection-box {
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  padding: 8px 10px;
  margin-bottom: 10px;
}

.selection-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin-bottom: 6px;
}

.selection-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  max-height: 120px;
  overflow-y: auto;
}

.manifest-item-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  cursor: pointer;
}

.empty-tip {
  font-size: 11px;
  margin: 4px 0;
}

/* 表格面板与锁定最小高度 */
.table-panel {
  background: #ffffff;
}

:deep(.feedback-table-wrapper .table-scroll) {
  min-height: 310px;
}

/* 严格对齐全局统一的 28px 表格行高与 3px 8px 紧凑内边距 */
:deep(.feedback-table td),
:deep(.feedback-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  line-height: 1.3;
}

:deep(.feedback-table tr) {
  height: 28px;
}

/* 单元格单行文字样式 */
.single-line-text {
  display: inline-block;
  white-space: nowrap;
  line-height: 20px;
  font-size: 11.5px;
}

.bold {
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.compliance-text {
  font-size: 11px;
}

.text-success {
  color: #0b7557;
  font-weight: 500;
}

.text-muted {
  color: var(--muted, #64716d);
}

.dot-sep {
  margin: 0 3px;
  opacity: 0.5;
}

.arrow-sep {
  margin: 0 4px;
  color: var(--muted, #64716d);
}

.time-text {
  font-size: 11px;
  color: var(--muted, #64716d);
}

/* 行内按钮与状态徽章：严格限制高度绝不撑大表格 */
.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

:deep(.feedback-table .badge),
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 10.5px;
  white-space: nowrap;
}

:deep(.feedback-table .button),
:deep(.feedback-table .icon-button),
.table-action-btn {
  height: 20px !important;
  min-height: 20px !important;
  padding: 0 6px !important;
  font-size: 10.5px !important;
  line-height: 1 !important;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.success-btn {
  color: #0b7557;
}

.success-btn:hover:not(:disabled) {
  background: rgba(11, 117, 87, 0.1);
}

.danger-btn {
  color: #ef4444;
}

.danger-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.dot-active {
  background: #22c55e;
  box-shadow: 0 0 5px rgba(34, 197, 94, 0.6);
}

.dot-error {
  background: #ef4444;
  box-shadow: 0 0 5px rgba(239, 68, 68, 0.6);
}

.dot-warn {
  background: #f59e0b;
}

.dot-dev {
  background: #38bdf8;
}

.error-badge {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.warn-badge {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

@media (max-width: 800px) {
  .form-grid,
  .form-grid-4,
  .form-grid-2 {
    grid-template-columns: 1fr;
  }
  .span-3 {
    grid-column: auto;
  }
}
</style>
