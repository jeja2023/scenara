<script setup lang="ts">
import {
  Check,
  CheckCircle2,
  Clock,
  FileCheck,
  FileClock,
  FileSpreadsheet,
  Filter,
  History,
  Layers,
  MessageSquare,
  MessageSquarePlus,
  Plus,
  RefreshCw,
  Rocket,
  RotateCcw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
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
  { key: "kind", label: "问题类型", width: "140px" },
  { key: "run_id", label: "运行标识", class: "mono", width: "160px" },
  { key: "model", label: "关联模型", width: "200px" },
  { key: "compliance", label: "合规状态", width: "150px" },
  { key: "status", label: "审核状态", width: "110px", align: "center", headerAlign: "center" },
  { key: "actions", label: "审批操作", width: "120px", align: "right", headerAlign: "right" },
];

const manifestColumns: TableColumn<HardSampleManifest>[] = [
  { key: "dataset", label: "数据集标识", width: "180px" },
  { key: "version", label: "版本", class: "mono", width: "100px" },
  { key: "split", label: "数据用途", width: "110px" },
  { key: "items", label: "样本条目数", width: "110px" },
  { key: "sha256", label: "校验指纹 (SHA256)", class: "mono", width: "180px" },
  { key: "created_at", label: "生成时间" },
];

const releaseColumns: TableColumn<ModelRelease>[] = [
  { key: "model_id", label: "模型名称", width: "220px" },
  { key: "version", label: "版本", class: "mono", width: "100px" },
  { key: "status", label: "准入状态", width: "120px", align: "center", headerAlign: "center" },
  { key: "evidence_refs", label: "详情引用", width: "160px" },
  { key: "actions", label: "准入流转 / 回滚", width: "160px", align: "right", headerAlign: "right" },
];

const eventColumns: TableColumn<ModelDeploymentEvent>[] = [
  { key: "action", label: "操作动作", width: "130px" },
  { key: "model_version", label: "模型与版本", width: "220px" },
  { key: "status_change", label: "状态迁移", width: "190px" },
  { key: "reason", label: "迁移原因说明", width: "200px" },
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
const saving = ref(false);
const error = ref("");
const successMessage = ref("");

// 搜索与过滤
const feedbackKindFilter = ref<string>("all");
const feedbackStatusFilter = ref<string>("all");
const feedbackSearchQuery = ref("");

const manifestSplitFilter = ref<string>("all");
const manifestSearchQuery = ref("");

const releaseStatusFilter = ref<string>("all");
const releaseSearchQuery = ref("");

// 弹窗控制
const showFeedbackModal = ref(false);
const showManifestModal = ref(false);
const showReleaseModal = ref(false);

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

// 计算与过滤
const pendingFeedbackCount = computed(
  () => feedback.value.filter((item) => item.status === "pending").length,
);

const approvedFeedback = computed(() =>
  feedback.value.filter((item) => item.status === "approved"),
);

const totalManifestItems = computed(() =>
  manifests.value.reduce((acc, m) => acc + (m.items ? m.items.length : 0), 0),
);

const activeReleasesCount = computed(
  () => releases.value.filter((r) => r.status === "active").length,
);

const selectedPackage = computed(() =>
  models.value.find(
    (item) => `${item.model_id}@${item.version}` === releaseForm.package_key,
  ),
);

const filteredFeedback = computed(() => {
  return feedback.value.filter((item) => {
    if (
      feedbackKindFilter.value !== "all" &&
      item.kind !== feedbackKindFilter.value
    ) {
      return false;
    }
    if (
      feedbackStatusFilter.value !== "all" &&
      item.status !== feedbackStatusFilter.value
    ) {
      return false;
    }
    if (feedbackSearchQuery.value.trim()) {
      const q = feedbackSearchQuery.value.trim().toLowerCase();
      const matchRun = String(item.run_id || "").toLowerCase().includes(q);
      const matchModel = String(item.model_id || "").toLowerCase().includes(q);
      return matchRun || matchModel;
    }
    return true;
  });
});

const filteredManifests = computed(() => {
  return manifests.value.filter((item) => {
    if (
      manifestSplitFilter.value !== "all" &&
      item.split !== manifestSplitFilter.value
    ) {
      return false;
    }
    if (manifestSearchQuery.value.trim()) {
      const q = manifestSearchQuery.value.trim().toLowerCase();
      const matchId = String(item.dataset_id || "").toLowerCase().includes(q);
      const matchSha = String(item.sha256 || "").toLowerCase().includes(q);
      return matchId || matchSha;
    }
    return true;
  });
});

const filteredReleases = computed(() => {
  return releases.value.filter((item) => {
    if (
      releaseStatusFilter.value !== "all" &&
      item.status !== releaseStatusFilter.value
    ) {
      return false;
    }
    if (releaseSearchQuery.value.trim()) {
      const q = releaseSearchQuery.value.trim().toLowerCase();
      const matchModel = String(item.model_id || "").toLowerCase().includes(q);
      const matchVersion = String(item.version || "").toLowerCase().includes(q);
      return matchModel || matchVersion;
    }
    return true;
  });
});

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

function notifySuccess(msg: string): void {
  successMessage.value = msg;
  setTimeout(() => {
    successMessage.value = "";
  }, 3500);
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
  saving.value = true;
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
    showFeedbackModal.value = false;
    notifySuccess("更正反馈已成功提交至审核队列");
    await refresh();
  } catch (caught) {
    showError(caught);
  } finally {
    saving.value = false;
  }
}

async function review(
  item: FeedbackRecord,
  status: "approved" | "rejected",
): Promise<void> {
  saving.value = true;
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
    notifySuccess(status === "approved" ? "反馈已核验批准" : "反馈已拒绝");
    await refresh();
  } catch (caught) {
    showError(caught);
  } finally {
    saving.value = false;
  }
}

function toggleSelectAllFeedback(): void {
  if (selectedFeedback.value.length === approvedFeedback.value.length) {
    selectedFeedback.value = [];
  } else {
    selectedFeedback.value = approvedFeedback.value.map((f) => f.feedback_id);
  }
}

async function createManifest(): Promise<void> {
  saving.value = true;
  try {
    await api<HardSampleManifest>("/api/v1/hard-sample-manifests", {
      method: "POST",
      body: JSON.stringify({
        ...manifestForm,
        feedback_ids: selectedFeedback.value,
      }),
    });
    selectedFeedback.value = [];
    showManifestModal.value = false;
    notifySuccess("版本化难例清单已成功生成");
    await refresh();
  } catch (caught) {
    showError(caught);
  } finally {
    saving.value = false;
  }
}

async function createRelease(): Promise<void> {
  const model = selectedPackage.value;
  if (!model) return;
  saving.value = true;
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
    showReleaseModal.value = false;
    notifySuccess("模型候选版本已登记成功");
    await refresh();
  } catch (caught) {
    showError(caught);
  } finally {
    saving.value = false;
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
  saving.value = true;
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
    notifySuccess(`模型已推进至 ${labelModelReleaseStatus(status)} 阶段`);
    await refresh();
  } catch (caught) {
    showError(caught);
  } finally {
    saving.value = false;
  }
}

async function rollback(item: ModelRelease): Promise<void> {
  saving.value = true;
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
    notifySuccess(`已受控回滚至版本 v${item.version}`);
    await refresh();
  } catch (caught) {
    showError(caught);
  } finally {
    saving.value = false;
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
  <section class="page feedback-page">
    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-if="successMessage" class="success-banner">{{ successMessage }}</p>

    <!-- 1. 顶部统一统计卡片 -->
    <section class="stats">
      <article class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">待审核反馈</span>
          <div class="stat-icon-badge">
            <MessageSquarePlus :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ pendingFeedbackCount }}</strong>
        <small class="stat-desc">共 {{ feedback.length }} 条问题与更正反馈</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">难例数据集</span>
          <div class="stat-icon-badge">
            <FileSpreadsheet :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ manifests.length }} 份</strong>
        <small class="stat-desc">已入库 {{ totalManifestItems }} 条训练样本</small>
      </article>

      <article class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">活跃发布版本</span>
          <div class="stat-icon-badge">
            <Rocket :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ activeReleasesCount }} 个</strong>
        <small class="stat-desc">全周期准入 {{ releases.length }} 个版本</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">受控部署事件</span>
          <div class="stat-icon-badge">
            <History :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ events.length }} 次</strong>
        <small class="stat-desc">阶段流转与回滚审计事件</small>
      </article>
    </section>

    <!-- 2. 分段 Tab 切换栏 -->
    <div class="tabs-header-bar">
      <nav class="domain-tabs feedback-tabs" aria-label="反馈与发布模块">
        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: tab === 'feedback' }"
          @click="tab = 'feedback'"
        >
          <MessageSquare :size="13" />
          <span>反馈审核队列</span>
          <span class="tab-badge">{{ feedback.length }}</span>
        </button>

        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: tab === 'manifests' }"
          @click="tab = 'manifests'"
        >
          <FileSpreadsheet :size="13" />
          <span>版本化难例清单</span>
          <span class="tab-badge">{{ manifests.length }}</span>
        </button>

        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: tab === 'releases' }"
          @click="tab = 'releases'"
        >
          <Rocket :size="13" />
          <span>模型发布与准入</span>
          <span class="tab-badge">{{ releases.length }}</span>
        </button>
      </nav>
    </div>

    <!-- ==================== 子视图 1：反馈审核 ==================== -->
    <div v-if="tab === 'feedback'" class="tab-content">
      <!-- 过滤与操作栏 -->
      <div class="filter-controls">
        <div class="filter-left">
          <label class="filter-item">
            <Filter :size="12" class="filter-icon" />
            <span class="filter-label">问题类型:</span>
            <select v-model="feedbackKindFilter" class="filter-select">
              <option value="all">全部类型 (All)</option>
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

          <label class="filter-item">
            <span class="filter-label">审核状态:</span>
            <select v-model="feedbackStatusFilter" class="filter-select">
              <option value="all">全部状态</option>
              <option value="pending">待审核 (Pending)</option>
              <option value="approved">已批准 (Approved)</option>
              <option value="rejected">已拒绝 (Rejected)</option>
            </select>
          </label>

          <div class="search-box search-lg">
            <Search :size="13" class="search-icon" />
            <input
              v-model="feedbackSearchQuery"
              placeholder="搜索运行标识或模型..."
              class="search-input"
            />
          </div>

          <span class="badge count-badge">共 {{ filteredFeedback.length }} 条记录</span>
        </div>

        <div class="filter-right">
          <button
            class="button secondary tiny-btn"
            :disabled="loading"
            @click="refresh"
          >
            <RefreshCw :size="12" :class="{ spinning: loading }" />
            <span>刷新</span>
          </button>
          <button
            class="button primary tiny-btn"
            @click="showFeedbackModal = true"
          >
            <Plus :size="13" />
            <span>提交更正反馈</span>
          </button>
        </div>
      </div>

      <!-- 反馈表格面板 -->
      <section class="panel table-panel">
        <DataTable
          :columns="feedbackColumns"
          :items="filteredFeedback"
          :page-size="feedbackPageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无匹配的更正反馈数据"
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
              <small class="mono text-muted">v{{ row.model_version }}</small>
            </span>
          </template>

          <!-- 4. 合规 -->
          <template #compliance="{ row }">
            <div class="compliance-pills">
              <span
                class="badge mini-pill"
                :class="row.authorized_for_training ? 'pill-success' : 'pill-muted'"
              >
                {{ row.authorized_for_training ? '已获训练授权' : '未授权' }}
              </span>
              <span
                class="badge mini-pill"
                :class="row.deidentified ? 'pill-success' : 'pill-muted'"
              >
                {{ row.deidentified ? '已完成脱敏' : '未脱敏' }}
              </span>
            </div>
          </template>

          <!-- 5. 状态 -->
          <template #status="{ row }">
            <span
              class="badge status-badge"
              :class="row.status === 'approved' ? 'active' : row.status === 'rejected' ? 'error-badge' : 'warn-badge'"
            >
              <span
                class="status-dot"
                :class="row.status === 'approved' ? 'dot-active' : row.status === 'rejected' ? 'dot-error' : 'dot-warn'"
              />
              {{ labelFeedbackStatus(row.status) }}
            </span>
          </template>

          <!-- 6. 操作 -->
          <template #actions="{ row }">
            <div v-if="row.status === 'pending'" class="table-actions-row">
              <button
                class="button primary tiny-btn table-approve-btn"
                title="批准该反馈（需已授权并脱敏）"
                :disabled="saving || !row.authorized_for_training || !row.deidentified"
                @click="review(row, 'approved')"
              >
                <Check :size="11" />批准
              </button>
              <button
                class="button danger tiny-btn table-reject-btn"
                title="拒绝该反馈"
                :disabled="saving"
                @click="review(row, 'rejected')"
              >
                <X :size="11" />拒绝
              </button>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </DataTable>
      </section>
    </div>

    <!-- ==================== 子视图 2：难例清单 ==================== -->
    <div v-if="tab === 'manifests'" class="tab-content">
      <!-- 过滤与操作栏 -->
      <div class="filter-controls">
        <div class="filter-left">
          <label class="filter-item">
            <Filter :size="12" class="filter-icon" />
            <span class="filter-label">数据用途:</span>
            <select v-model="manifestSplitFilter" class="filter-select">
              <option value="all">全部用途 (All)</option>
              <option value="train">训练 (Train)</option>
              <option value="validation">验证 (Validation)</option>
              <option value="test">测试 (Test)</option>
            </select>
          </label>

          <div class="search-box search-lg">
            <Search :size="13" class="search-icon" />
            <input
              v-model="manifestSearchQuery"
              placeholder="搜索数据集标识或指纹..."
              class="search-input"
            />
          </div>

          <span class="badge count-badge">共 {{ filteredManifests.length }} 份清单</span>
        </div>

        <div class="filter-right">
          <button
            class="button secondary tiny-btn"
            :disabled="loading"
            @click="refresh"
          >
            <RefreshCw :size="12" :class="{ spinning: loading }" />
            <span>刷新</span>
          </button>
          <button
            class="button primary tiny-btn"
            @click="showManifestModal = true"
          >
            <Plus :size="13" />
            <span>生成难例清单</span>
          </button>
        </div>
      </div>

      <!-- 难例清单数据表格 -->
      <section class="panel table-panel">
        <DataTable
          :columns="manifestColumns"
          :items="filteredManifests"
          :page-size="manifestPageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无版本化难例清单数据"
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

          <!-- 3. 数据用途 -->
          <template #split="{ row }">
            <span class="badge split-badge" :class="`split-${row.split || 'train'}`">
              {{ row.split === 'train' ? '训练集' : row.split === 'validation' ? '验证集' : '测试集' }}
            </span>
          </template>

          <!-- 4. 条目 -->
          <template #items="{ row }">
            <span class="bold">{{ row.items ? row.items.length : 0 }} 条样本</span>
          </template>

          <!-- 5. SHA256 -->
          <template #sha256="{ row }">
            <span class="mono sha-text" :title="row.sha256">{{ row.sha256 ? row.sha256.slice(0, 18) + '…' : '-' }}</span>
          </template>

          <!-- 6. 创建时间 -->
          <template #created_at="{ row }">
            <span class="mono time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </DataTable>
      </section>
    </div>

    <!-- ==================== 子视图 3：模型发布与准入 ==================== -->
    <div v-if="tab === 'releases'" class="tab-content releases-layout">
      <!-- 过滤与操作栏 -->
      <div class="filter-controls">
        <div class="filter-left">
          <label class="filter-item">
            <Filter :size="12" class="filter-icon" />
            <span class="filter-label">准入状态:</span>
            <select v-model="releaseStatusFilter" class="filter-select">
              <option value="all">全部状态 (All)</option>
              <option value="candidate">候选版本 (Candidate)</option>
              <option value="validated">验证中 (Validated)</option>
              <option value="approved">已批准 (Approved)</option>
              <option value="active">已生效上线 (Active)</option>
              <option value="retired">已退役下线 (Retired)</option>
            </select>
          </label>

          <div class="search-box search-lg">
            <Search :size="13" class="search-icon" />
            <input
              v-model="releaseSearchQuery"
              placeholder="搜索模型名称或版本..."
              class="search-input"
            />
          </div>

          <span class="badge count-badge">共 {{ filteredReleases.length }} 个版本</span>
        </div>

        <div class="filter-right">
          <button
            class="button secondary tiny-btn"
            :disabled="loading"
            @click="refresh"
          >
            <RefreshCw :size="12" :class="{ spinning: loading }" />
            <span>刷新</span>
          </button>
          <button
            class="button primary tiny-btn"
            @click="showReleaseModal = true"
          >
            <Plus :size="13" />
            <span>登记候选版本</span>
          </button>
        </div>
      </div>

      <!-- 1. 发布版本数据表格 -->
      <section class="panel table-panel">
        <div class="panel-header">
          <div class="header-left">
            <Rocket :size="14" class="header-icon" />
            <h3>模型版本准入全生命周期清单</h3>
            <span class="badge count-badge">{{ filteredReleases.length }}</span>
          </div>
        </div>
        <DataTable
          :columns="releaseColumns"
          :items="filteredReleases"
          :page-size="releasePageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无模型发布版本记录"
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
            <span
              class="badge status-badge"
              :class="row.status === 'active' ? 'active' : row.status === 'retired' ? 'error-badge' : 'warn-badge'"
            >
              <span
                class="status-dot"
                :class="row.status === 'active' ? 'dot-active' : row.status === 'retired' ? 'dot-error' : 'dot-warn'"
              />
              {{ labelModelReleaseStatus(row.status) }}
            </span>
          </template>

          <!-- 4. 证据引用 -->
          <template #evidence_refs="{ row }">
            <span
              v-if="row.evidence_refs && row.evidence_refs.length"
              class="single-line-text mono evidence-badge"
              :title="row.evidence_refs.join('\n')"
            >
              {{ row.evidence_refs.length }} 项证据
            </span>
            <span v-else class="text-muted">未关联证据</span>
          </template>

          <!-- 5. 操作 -->
          <template #actions="{ row }">
            <div class="table-actions-row">
              <button
                v-if="nextStatus(row)"
                class="button primary tiny-btn advance-btn"
                :disabled="saving || (row.status === 'candidate' && (!row.evidence_refs || !row.evidence_refs.length))"
                :title="row.status === 'candidate' && (!row.evidence_refs || !row.evidence_refs.length) ? '必须关联评估证据后方可推进' : ''"
                @click="transition(row)"
              >
                推进至 {{ labelModelReleaseStatus(nextStatus(row) || "") }}
              </button>
              <button
                v-if="row.status === 'retired'"
                class="button secondary tiny-btn rollback-btn"
                title="受控回滚至此版本"
                :disabled="saving"
                @click="rollback(row)"
              >
                <RotateCcw :size="11" />回滚
              </button>
            </div>
          </template>
        </DataTable>
      </section>

      <!-- 2. 部署审计事件历史表格 -->
      <section class="panel table-panel">
        <div class="panel-header">
          <div class="header-left">
            <History :size="14" class="header-icon" />
            <h3>模型部署与状态流转审计日志</h3>
            <span class="badge count-badge">{{ events.length }}</span>
          </div>
        </div>
        <DataTable
          :columns="eventColumns"
          :items="events"
          :page-size="eventPageSize"
          :page-size-options="[10, 20, 50]"
          table-class="feedback-table"
          wrapper-class="feedback-table-wrapper"
          empty-text="暂无部署审计事件"
        >
          <!-- 1. 操作 -->
          <template #action="{ row }">
            <span class="badge action-tag">{{ labelDeploymentAction(row.action) }}</span>
          </template>

          <!-- 2. 模型版本 -->
          <template #model_version="{ row }">
            <span class="single-line-text" :title="`${row.model_id} (v${row.version})`">
              <strong>{{ labelModelName(row.model_id) }}</strong>
              <span class="mono text-muted"> · v{{ row.version }}</span>
            </span>
          </template>

          <!-- 3. 状态变化 -->
          <template #status_change="{ row }">
            <span class="single-line-text status-transition-text">
              <span class="muted">{{ row.from_status ? labelModelReleaseStatus(row.from_status) : "初始创建" }}</span>
              <span class="arrow-sep">→</span>
              <strong class="highlight-status">{{ labelModelReleaseStatus(row.to_status) }}</strong>
            </span>
          </template>

          <!-- 4. 原因 -->
          <template #reason="{ row }">
            <span class="single-line-text text-muted" :title="row.reason">{{ labelSystemReason(row.reason) }}</span>
          </template>

          <!-- 5. 时间 -->
          <template #created_at="{ row }">
            <span class="mono time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </DataTable>
      </section>
    </div>

    <!-- ==================== 模态弹窗 1：提交更正反馈 ==================== -->
    <div
      v-if="showFeedbackModal"
      class="modal-overlay"
      @click.self="showFeedbackModal = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <MessageSquarePlus :size="17" class="modal-title-icon" />
            <div>
              <h3>提交运行更正反馈</h3>
              <p>针对已完成分析任务提交模型识别更正与脱敏训练授权</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="submitFeedback">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label">问题类型 <em class="required">*</em></span>
                <select v-model="feedbackForm.kind" class="field-input">
                  <option value="false_positive">误检 (False Positive)</option>
                  <option value="false_negative">漏检 (False Negative)</option>
                  <option value="wrong_attribute">属性错误 (Wrong Attribute)</option>
                  <option value="wrong_identity">身份匹配错误 (Wrong Identity)</option>
                  <option value="ocr_correction">文字更正 (OCR Correction)</option>
                  <option value="action_correction">动作更正 (Action Correction)</option>
                  <option value="temporal_correction">时序区间更正</option>
                  <option value="style_correction">服装风格更正</option>
                  <option value="character_correction">角色更正</option>
                  <option value="accessory_correction">配饰更正</option>
                </select>
              </label>

              <label class="form-field">
                <span class="field-label">关联已完成运行 (Run) <em class="required">*</em></span>
                <select
                  v-model="feedbackForm.run_id"
                  class="field-input mono"
                  required
                  @change="selectRun"
                >
                  <option value="">请选择历史运行记录</option>
                  <option
                    v-for="item in runs"
                    :key="item.run_id"
                    :value="item.run_id"
                  >
                    {{ item.run_id }}
                  </option>
                </select>
              </label>
            </div>

            <label class="form-field" style="margin-top: 10px;">
              <span class="field-label">关联分析模型 <em class="required">*</em></span>
              <select
                v-model="selectedModelKey"
                class="field-input"
                :disabled="!traceModels.length"
                required
                @change="selectModel"
              >
                <option value="">{{ traceModels.length ? '请选择关联模型' : '请先选择上方运行记录' }}</option>
                <option
                  v-for="item in traceModels"
                  :key="item.model_id + item.version"
                  :value="`${item.model_id}@${item.version}`"
                >
                  {{ labelModelName(item.model_id) }} (v{{ item.version }})
                </option>
              </select>
            </label>

            <label class="form-field" style="margin-top: 10px;">
              <span class="field-label">更正详情内容 (JSON 结构体) <em class="required">*</em></span>
              <textarea
                v-model="feedbackForm.correction"
                placeholder="{ &quot;expected_label&quot;: &quot;...&quot; }"
                class="field-input field-textarea mono"
                rows="3"
                required
              ></textarea>
            </label>

            <div class="switches-box" style="margin-top: 12px;">
              <label class="switch-item">
                <input
                  v-model="feedbackForm.authorized_for_training"
                  type="checkbox"
                  class="switch-checkbox"
                />
                <div class="switch-text-box">
                  <strong>已获数据二次训练授权</strong>
                  <p>确认该样本已取得业务方合规授权，可用于后续算法增量重训练与微调。</p>
                </div>
              </label>
              <label class="switch-item">
                <input
                  v-model="feedbackForm.deidentified"
                  type="checkbox"
                  class="switch-checkbox"
                />
                <div class="switch-text-box">
                  <strong>已完成敏感隐私脱敏</strong>
                  <p>确认人脸、车牌等敏感个人隐私信息已被遮蔽或脱敏清洗。</p>
                </div>
              </label>
            </div>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showFeedbackModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="saving || !feedbackForm.run_id || !feedbackForm.model_id"
            >
              <Plus :size="13" />确认提交反馈
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 2：生成难例清单 ==================== -->
    <div
      v-if="showManifestModal"
      class="modal-overlay"
      @click.self="showManifestModal = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <FileSpreadsheet :size="17" class="modal-title-icon" />
            <div>
              <h3>生成版本化难例清单</h3>
              <p>将已审核批准且完成脱敏的纠错反馈样本打包为结构化数据集清单</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createManifest">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label">数据集标识 <em class="required">*</em></span>
                <input
                  v-model="manifestForm.dataset_id"
                  placeholder="如 hard_samples_2026"
                  class="field-input mono"
                  required
                />
              </label>

              <label class="form-field">
                <span class="field-label">版本号 <em class="required">*</em></span>
                <input
                  v-model="manifestForm.version"
                  placeholder="1.0.0"
                  class="field-input mono"
                  required
                />
              </label>
            </div>

            <div class="form-grid-2col" style="margin-top: 10px;">
              <label class="form-field">
                <span class="field-label">标签规范协议 <em class="required">*</em></span>
                <input
                  v-model="manifestForm.label_schema"
                  class="field-input mono"
                  required
                />
              </label>

              <label class="form-field">
                <span class="field-label">数据用途 (Split) <em class="required">*</em></span>
                <select v-model="manifestForm.split" class="field-input">
                  <option value="train">训练集 (Train)</option>
                  <option value="validation">验证集 (Validation)</option>
                  <option value="test">测试集 (Test)</option>
                </select>
              </label>
            </div>

            <div class="manifest-selection-panel" style="margin-top: 12px;">
              <div class="manifest-selection-header">
                <strong>选择纳入清单的已批准反馈条目：</strong>
                <button
                  type="button"
                  class="button secondary tiny-btn select-toggle-btn"
                  :disabled="!approvedFeedback.length"
                  @click="toggleSelectAllFeedback"
                >
                  {{ selectedFeedback.length === approvedFeedback.length && approvedFeedback.length > 0 ? '取消全选' : '全部选择' }}
                </button>
              </div>

              <div v-if="approvedFeedback.length" class="selection-scroll-list">
                <label
                  v-for="item in approvedFeedback"
                  :key="item.feedback_id"
                  class="manifest-checkbox-row"
                >
                  <input
                    v-model="selectedFeedback"
                    type="checkbox"
                    class="checkbox-input"
                    :value="item.feedback_id"
                  />
                  <span class="badge mini-pill pill-success">{{ labelFeedbackKind(item.kind) }}</span>
                  <span class="mono">{{ item.run_id }}</span>
                  <span class="text-muted">· {{ labelModelName(item.model_id) }}</span>
                </label>
              </div>
              <div v-else class="empty-selection-tip">
                暂无可纳入导出的已批准反馈（需先在反馈队列中审核批准并授权）
              </div>
            </div>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showManifestModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="saving || !manifestForm.dataset_id || !selectedFeedback.length"
            >
              <Plus :size="13" />生成难例清单 (已选 {{ selectedFeedback.length }} 条)
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 3：登记候选版本 ==================== -->
    <div
      v-if="showReleaseModal"
      class="modal-overlay"
      @click.self="showReleaseModal = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <Rocket :size="17" class="modal-title-icon" />
            <div>
              <h3>登记模型候选版本</h3>
              <p>向准入治理中心登记新模型制品包并关联评测合规证据</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createRelease">
          <div class="modal-body">
            <label class="form-field">
              <span class="field-label">已登记模型制品包 <em class="required">*</em></span>
              <select v-model="releaseForm.package_key" class="field-input" required>
                <option value="">请选择要准入的模型包</option>
                <option
                  v-for="item in models"
                  :key="item.model_id + item.version"
                  :value="`${item.model_id}@${item.version}`"
                >
                  {{ labelModelName(item.model_id) }} (v{{ item.version }}) · {{ item.sha256 ? item.sha256.slice(0, 10) : '' }}
                </option>
              </select>
            </label>

            <label class="form-field" style="margin-top: 10px;">
              <span class="field-label">证据引用 URI (每行一条)</span>
              <textarea
                v-model="releaseForm.evidence_refs"
                placeholder="例如: s3://evidence/eval_report_v1.json"
                class="field-input field-textarea mono"
                rows="3"
              ></textarea>
              <small class="field-hint">候选版本需提供评测报告或基准测试证据 URI 后方可推进至验证与批准状态。</small>
            </label>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showReleaseModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="saving || !selectedPackage"
            >
              <Plus :size="13" />确认登记候选版本
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.feedback-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.error-banner {
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

.success-banner {
  padding: 8px 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

/* 顶部统计卡片 */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 2px;
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat {
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  transition: all 0.15s ease;
}

.stat:hover {
  transform: translateY(-1px);
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.04);
}

.stat-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.stat-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.stat-icon-badge {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat.teal .stat-icon-badge {
  background: #f0fdfa;
  color: var(--color-accent, #087682);
  border: 1px solid #ccfbf1;
}

.stat.green .stat-icon-badge {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #dcfce7;
}

.stat.amber .stat-icon-badge {
  background: #fffbeb;
  color: #d97706;
  border: 1px solid #fef3c7;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  line-height: 1.2;
  margin: 2px 0 1px;
}

.stat-desc {
  font-size: 10.5px;
  color: #8c9b97;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 分段 Tab 导航 */
.tabs-header-bar {
  display: flex;
  align-items: center;
}

.feedback-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
  flex-wrap: wrap;
}

.domain-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
  font-size: 10.5px;
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 5px;
  border-radius: 999px;
}

.domain-tab-btn.active .tab-badge {
  background: rgba(8, 118, 130, 0.15);
  color: var(--color-accent-hover, #065e67);
}

/* 过滤工具栏 */
.filter-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 6px 12px;
  flex-wrap: wrap;
}

.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--muted, #64716d);
}

.filter-icon {
  color: var(--muted, #64716d);
}

.filter-label {
  font-weight: 500;
  white-space: nowrap;
}

.filter-select {
  height: 28px;
  padding: 0 8px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  cursor: pointer;
}
.filter-select:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.count-badge {
  background: #edf2f0;
  color: #45534f;
  font-size: 11px;
  padding: 3px 7px;
  border-radius: 4px;
}

/* 面板通用 */
.panel {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  color: var(--color-accent, #087682);
}

.panel-header h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

/* 数据表格深度规范 */
:deep(.feedback-table td),
:deep(.feedback-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  font-size: 11.5px;
}

:deep(.feedback-table th) {
  background: #fafbfb;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.single-line-text {
  display: inline-block;
  white-space: nowrap;
  line-height: 20px;
  font-size: 11.5px;
}

.bold {
  font-weight: 600;
}

.compliance-pills {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mini-pill {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}
.pill-success {
  background: #dcfce7;
  color: #166534;
}
.pill-muted {
  background: #f1f5f4;
  color: #8c9b97;
}

.split-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
}
.split-badge.split-train {
  background: #e0f2fe;
  color: #0369a1;
}
.split-badge.split-validation {
  background: #fef3c7;
  color: #92400e;
}
.split-badge.split-test {
  background: #f3e8ff;
  color: #7e22ce;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10.5px;
}
.status-badge.active {
  background: #dcfce7;
  color: #166534;
}
.status-badge.warn-badge {
  background: #fef3c7;
  color: #92400e;
}
.status-badge.error-badge {
  background: #fee2e2;
  color: #991b1b;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.dot-active {
  background: #16a34a;
}
.dot-warn {
  background: #d97706;
}
.dot-error {
  background: #dc2626;
}

.table-actions-row {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.table-approve-btn {
  background: #16a34a;
  border-color: #16a34a;
  height: 20px !important;
  font-size: 10.5px;
}
.table-approve-btn:hover:not(:disabled) {
  background: #15803d;
}

.table-reject-btn {
  background: #dc2626;
  border-color: #dc2626;
  height: 20px !important;
  font-size: 10.5px;
}
.table-reject-btn:hover:not(:disabled) {
  background: #b91c1c;
}

.advance-btn {
  height: 20px !important;
  font-size: 10.5px;
}

.rollback-btn {
  height: 20px !important;
  font-size: 10.5px;
  color: #d97706;
}

.evidence-badge {
  color: var(--color-accent-hover, #065e67);
}

.action-tag {
  background: #eef2f1;
  color: #2c3e38;
  font-size: 10.5px;
  padding: 1px 5px;
  border-radius: 3px;
}

.status-transition-text {
  font-size: 11px;
}

.highlight-status {
  color: var(--color-accent-hover, #065e67);
}

.arrow-sep {
  margin: 0 4px;
  color: #a0afa9;
}

.sha-text {
  color: var(--graphite, #17211f);
}

.time-text {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.text-muted {
  color: var(--muted, #64716d);
}

.muted {
  color: var(--muted, #64716d);
}

.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}

.releases-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

/* 模态弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 26, 24, 0.45);
  display: grid;
  place-items: center;
  z-index: 1000;
  padding: 16px;
}

.modal-dialog {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  box-shadow: 0 20px 50px rgba(15, 23, 21, 0.22);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-dialog-md {
  width: min(640px, 95vw);
}

.modal-dialog-lg {
  width: min(720px, 95vw);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.modal-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title-icon {
  color: var(--color-accent, #087682);
}

.modal-title-box h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.modal-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.modal-body {
  padding: 16px 18px;
}

.form-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.required {
  color: #dc2626;
  font-style: normal;
}

.field-input {
  height: 28px;
  padding: 0 8px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  box-sizing: border-box;
  width: 100%;
}
.field-input:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.field-textarea {
  height: auto;
  padding: 6px 8px;
  line-height: 1.4;
  resize: vertical;
}

.field-hint {
  font-size: 11px;
  color: var(--muted, #64716d);
  margin-top: 2px;
}

.switches-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
}

.switch-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  cursor: pointer;
}

.switch-checkbox {
  margin-top: 3px;
  accent-color: var(--color-accent, #087682);
}

.switch-text-box strong {
  display: block;
  font-size: 11.5px;
  color: var(--graphite, #17211f);
}

.switch-text-box p {
  margin: 1px 0 0;
  font-size: 10.5px;
  color: var(--muted, #64716d);
  line-height: 1.3;
}

.manifest-selection-panel {
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 10px 12px;
}

.manifest-selection-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 11.5px;
  color: var(--graphite, #17211f);
}

.select-toggle-btn {
  height: 22px !important;
  padding: 0 8px !important;
  font-size: 11px !important;
}

.selection-scroll-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 160px;
  overflow-y: auto;
}

.manifest-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  cursor: pointer;
  padding: 3px 6px;
  border-radius: 4px;
}
.manifest-checkbox-row:hover {
  background: #ffffff;
}

.empty-selection-tip {
  font-size: 11px;
  color: var(--muted, #64716d);
  padding: 8px 0;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}
</style>
