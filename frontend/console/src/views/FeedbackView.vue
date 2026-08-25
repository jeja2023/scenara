<script setup lang="ts">
import { Check, History, Plus, RotateCcw, X } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";
import {
  labelDeploymentAction,
  labelFeedbackKind,
  labelFeedbackStatus,
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
  { key: "kind", label: "类型" },
  { key: "run_id", label: "运行", class: "mono" },
  { key: "model", label: "模型" },
  { key: "compliance", label: "合规" },
  { key: "status", label: "状态" },
  { key: "actions", label: "操作" },
];

const manifestColumns: TableColumn<HardSampleManifest>[] = [
  { key: "dataset", label: "数据集" },
  { key: "version", label: "版本", class: "mono" },
  { key: "items", label: "条目" },
  { key: "sha256", label: "SHA-256", class: "mono" },
  { key: "created_at", label: "创建时间" },
];

const releaseColumns: TableColumn<ModelRelease>[] = [
  { key: "model_id", label: "模型" },
  { key: "version", label: "版本", class: "mono" },
  { key: "status", label: "状态" },
  { key: "evidence_refs", label: "证据" },
  { key: "actions", label: "操作" },
];

const eventColumns: TableColumn<ModelDeploymentEvent>[] = [
  { key: "action", label: "操作" },
  { key: "model_version", label: "模型版本" },
  { key: "status_change", label: "状态变化" },
  { key: "reason", label: "原因" },
  { key: "created_at", label: "时间" },
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

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="segmented" role="tablist" aria-label="反馈与发布视图">
      <button :class="{ active: tab === 'feedback' }" @click="tab = 'feedback'">
        反馈审核
      </button>
      <button
        :class="{ active: tab === 'manifests' }"
        @click="tab = 'manifests'"
      >
        难例清单
      </button>
      <button :class="{ active: tab === 'releases' }" @click="tab = 'releases'">
        模型发布
      </button>
    </div>

    <template v-if="tab === 'feedback'">
      <section class="panel">
        <div class="panel-header"><h2>提交反馈</h2></div>
        <div class="panel-body">
          <div class="form-grid">
            <label
              ><span>问题类型</span
              ><select v-model="feedbackForm.kind">
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
              </select></label
            >
            <label
              ><span>已完成运行</span
              ><select v-model="feedbackForm.run_id" @change="selectRun">
                <option value="">请选择</option>
                <option
                  v-for="item in runs"
                  :key="item.run_id"
                  :value="item.run_id"
                >
                  {{ item.run_id }}
                </option>
              </select></label
            >
            <label
              ><span>结果模型</span
              ><select
                v-model="selectedModelKey"
                :disabled="!traceModels.length"
                @change="selectModel"
              >
                <option value="">请选择</option>
                <option
                  v-for="item in traceModels"
                  :key="item.model_id + item.version"
                  :value="`${item.model_id}@${item.version}`"
                >
                  {{ item.model_id }} · {{ item.version }}
                </option>
              </select></label
            >
            <label class="span-2"
              ><span>更正内容（JSON）</span
              ><textarea v-model="feedbackForm.correction"></textarea>
            </label>
          </div>
          <div class="checks">
            <label
              ><input
                v-model="feedbackForm.authorized_for_training"
                type="checkbox"
              />已获训练授权</label
            ><label
              ><input
                v-model="feedbackForm.deidentified"
                type="checkbox"
              />已完成脱敏</label
            >
          </div>
          <button
            class="button primary"
            :disabled="!feedbackForm.run_id || !feedbackForm.model_id"
            @click="submitFeedback"
          >
            <Plus :size="16" />提交反馈
          </button>
        </div>
      </section>
      <section class="panel spaced">
        <div class="panel-header">
          <h2>反馈队列</h2>
          <span class="badge">{{ feedback.length }}</span>
        </div>
        <DataTable
          :columns="feedbackColumns"
          :items="feedback"
          empty-text="暂无反馈"
        >
          <template #kind="{ row }">
            <strong>{{ labelFeedbackKind(row.kind) }}</strong>
            <div class="mono muted">{{ row.feedback_id }}</div>
          </template>
          <template #model="{ row }">
            {{ row.model_id }}
            <div class="mono muted">{{ row.model_version }}</div>
          </template>
          <template #compliance="{ row }">
            {{ row.authorized_for_training ? "已授权" : "未授权" }} ·
            {{ row.deidentified ? "已脱敏" : "未脱敏" }}
          </template>
          <template #status="{ row }">
            <span class="badge" :class="row.status">{{
              labelFeedbackStatus(row.status)
            }}</span>
          </template>
          <template #actions="{ row }">
            <div v-if="row.status === 'pending'" class="row-actions">
              <button
                class="icon-button"
                title="批准反馈"
                :disabled="
                  !row.authorized_for_training || !row.deidentified
                "
                @click="review(row, 'approved')"
              >
                <Check :size="15" />
              </button>
              <button
                class="icon-button danger-icon"
                title="拒绝反馈"
                @click="review(row, 'rejected')"
              >
                <X :size="15" />
              </button>
            </div>
          </template>
        </DataTable>
      </section>
    </template>

    <template v-else-if="tab === 'manifests'">
      <section class="panel">
        <div class="panel-header"><h2>生成难例清单</h2></div>
        <div class="panel-body">
          <div class="form-grid">
            <label
              ><span>数据集标识</span
              ><input v-model="manifestForm.dataset_id" /></label
            ><label
              ><span>版本</span><input v-model="manifestForm.version" /></label
            ><label
              ><span>标签规范</span
              ><input v-model="manifestForm.label_schema" /></label
            ><label
              ><span>数据用途</span
              ><select v-model="manifestForm.split">
                <option value="train">训练</option>
                <option value="validation">验证</option>
                <option value="test">测试</option>
              </select></label
            >
          </div>
          <div class="selection-list">
            <label v-for="item in approvedFeedback" :key="item.feedback_id"
              ><input
                v-model="selectedFeedback"
                type="checkbox"
                :value="item.feedback_id"
              /><span
                >{{ labelFeedbackKind(item.kind) }} · {{ item.run_id }}</span
              ></label
            >
            <p v-if="!approvedFeedback.length" class="muted">
              没有可导出的已批准反馈
            </p>
          </div>
          <button
            class="button primary"
            :disabled="!manifestForm.dataset_id || !selectedFeedback.length"
            @click="createManifest"
          >
            <Plus :size="16" />生成清单
          </button>
        </div>
      </section>
      <section class="panel spaced">
        <div class="panel-header">
          <h2>版本化清单</h2>
          <span class="badge">{{ manifests.length }}</span>
        </div>
        <DataTable
          :columns="manifestColumns"
          :items="manifests"
          empty-text="暂无难例清单"
        >
          <template #dataset="{ row }">
            <strong>{{ row.dataset_id }}</strong>
            <div class="mono muted">{{ row.manifest_id }}</div>
          </template>
          <template #items="{ row }">
            {{ row.items.length }}
          </template>
          <template #sha256="{ row }">
            <span class="mono">{{ row.sha256.slice(0, 16) }}…</span>
          </template>
          <template #created_at="{ row }">
            {{ new Date(row.created_at * 1000).toLocaleString() }}
          </template>
        </DataTable>
      </section>
    </template>

    <template v-else>
      <section class="panel">
        <div class="panel-header"><h2>登记候选版本</h2></div>
        <div class="panel-body">
          <div class="form-grid">
            <label
              ><span>已登记模型包</span
              ><select v-model="releaseForm.package_key">
                <option value="">请选择</option>
                <option
                  v-for="item in models"
                  :key="item.model_id + item.version"
                  :value="`${item.model_id}@${item.version}`"
                >
                  {{ item.model_id }} · {{ item.version }}
                </option>
              </select></label
            ><label
              ><span>证据引用（每行一个）</span
              ><textarea v-model="releaseForm.evidence_refs"></textarea>
            </label>
          </div>
          <button
            class="button primary"
            :disabled="!selectedPackage"
            @click="createRelease"
          >
            <Plus :size="16" />登记候选版本
          </button>
        </div>
      </section>
      <section class="panel spaced">
        <div class="panel-header">
          <h2>发布版本</h2>
          <span class="badge">{{ releases.length }}</span>
        </div>
        <DataTable
          :columns="releaseColumns"
          :items="releases"
          empty-text="暂无发布版本"
        >
          <template #model_id="{ row }">
            <strong>{{ row.model_id }}</strong>
          </template>
          <template #status="{ row }">
            <span class="badge" :class="row.status">{{
              labelModelReleaseStatus(row.status)
            }}</span>
          </template>
          <template #evidence_refs="{ row }">
            <details v-if="row.evidence_refs.length">
              <summary>{{ row.evidence_refs.length }} 项</summary>
              <div
                v-for="reference in row.evidence_refs"
                :key="reference"
                class="mono evidence-ref"
              >
                {{ reference }}
              </div>
            </details>
            <span v-else class="muted">未登记</span>
          </template>
          <template #actions="{ row }">
            <div class="row-actions">
              <button
                v-if="nextStatus(row)"
                class="button secondary"
                :disabled="
                  row.status === 'candidate' &&
                  !row.evidence_refs.length
                "
                :title="
                  row.status === 'candidate' &&
                  !row.evidence_refs.length
                    ? '登记证据后才能验证'
                    : ''
                "
                @click="transition(row)"
              >
                {{
                  labelModelReleaseStatus(nextStatus(row) || "")
                }}
              </button>
              <button
                v-if="row.status === 'retired'"
                class="icon-button"
                title="回滚到此版本"
                @click="rollback(row)"
              >
                <RotateCcw :size="15" />
              </button>
            </div>
          </template>
        </DataTable>
      </section>
      <section class="panel spaced">
        <div class="panel-header">
          <h2>部署事件</h2>
          <History :size="16" />
        </div>
        <DataTable
          :columns="eventColumns"
          :items="events"
          empty-text="暂无部署事件"
        >
          <template #action="{ row }">
            {{ labelDeploymentAction(row.action) }}
          </template>
          <template #model_version="{ row }">
            {{ row.model_id }}
            <div class="mono muted">{{ row.version }}</div>
          </template>
          <template #status_change="{ row }">
            {{
              row.from_status
                ? labelModelReleaseStatus(row.from_status)
                : "无"
            }}
            → {{ labelModelReleaseStatus(row.to_status) }}
          </template>
          <template #reason="{ row }">
            {{ labelSystemReason(row.reason) }}
          </template>
          <template #created_at="{ row }">
            {{ new Date(row.created_at * 1000).toLocaleString() }}
          </template>
        </DataTable>
      </section>
    </template>
  </section>
</template>

<style scoped>
.segmented {
  display: inline-flex;
  margin-bottom: 14px;
  border: 1px solid var(--line);
  border-radius: 5px;
  overflow: hidden;
  background: #fff;
}
.segmented button {
  min-width: 112px;
  height: 34px;
  border: 0;
  border-right: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.segmented button:last-child {
  border-right: 0;
}
.segmented button.active {
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 700;
}
.checks {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
}
.row-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.danger-icon {
  color: var(--coral);
}
.evidence-ref {
  max-width: 320px;
  overflow-wrap: anywhere;
  margin-top: 5px;
}
textarea {
  min-height: 72px;
}
@media (max-width: 650px) {
  .segmented {
    display: grid;
    grid-template-columns: 1fr;
    width: 100%;
  }
  .segmented button {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .segmented button:last-child {
    border-bottom: 0;
  }
}
</style>
