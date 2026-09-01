<script setup lang="ts">
import {
  Activity,
  Check,
  CheckCircle2,
  Clock,
  Database,
  FileClock,
  FileSpreadsheet,
  Filter,
  History,
  Layers,
  Plus,
  Radio,
  RefreshCw,
  Save,
  Search,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";
import DataTable from "../components/DataTable.vue";
import type { TableColumn } from "../types";

type RecordMap = {
  record_id: string;
  period_started_at?: number;
  [key: string]: string | number | boolean | undefined;
};

type GovernanceTab = "lifecycle" | "retention" | "adapters";

const activeTab = ref<GovernanceTab>("lifecycle");

const lifecycleColumns: TableColumn<RecordMap>[] = [
  { key: "project_id", label: "目标项目标识", width: "160px" },
  { key: "action", label: "申请动作", width: "130px" },
  { key: "reason", label: "变更原因说明" },
  { key: "status", label: "审批状态", width: "110px", align: "center", headerAlign: "center" },
  { key: "operations", label: "审批操作", align: "right", headerAlign: "right", width: "130px" },
];

const lifecycle = ref<RecordMap[]>([]);
const identityProviders = ref<RecordMap[]>([]);
const annotationProviders = ref<RecordMap[]>([]);
const indexBackends = ref<RecordMap[]>([]);
const rerankers = ref<RecordMap[]>([]);
const retention = ref<RecordMap | null>(null);

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const successMessage = ref("");
const probingIds = ref<Set<string>>(new Set());

// 搜索与过滤
const searchQuery = ref("");
const statusFilter = ref<string>("all");
const actionFilter = ref<string>("all");
const adapterCategoryFilter = ref<string>("all");

// 弹窗状态
const showLifecycleModal = ref(false);

const lifecycleForm = reactive({
  project_id: "default",
  action: "disable" as "disable" | "restore" | "delete",
  reason: "",
});

const retentionForm = reactive({
  retention_days: 365,
  export_approval_required: true,
  enabled: true,
});

// 计算统计
const pendingCount = computed(
  () => lifecycle.value.filter((r) => r.status === "pending").length,
);
const approvedCount = computed(
  () => lifecycle.value.filter((r) => r.status === "approved").length,
);
const totalAdaptersCount = computed(
  () =>
    identityProviders.value.length +
    annotationProviders.value.length +
    indexBackends.value.length +
    rerankers.value.length,
);

const filteredLifecycle = computed(() => {
  return lifecycle.value.filter((item) => {
    if (statusFilter.value !== "all" && item.status !== statusFilter.value) {
      return false;
    }
    if (actionFilter.value !== "all" && item.action !== actionFilter.value) {
      return false;
    }
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.trim().toLowerCase();
      const matchProject = String(item.project_id || "").toLowerCase().includes(q);
      const matchReason = String(item.reason || "").toLowerCase().includes(q);
      return matchProject || matchReason;
    }
    return true;
  });
});

const allAdapters = computed(() => {
  const list: Array<{
    id: string;
    name: string;
    category: string;
    categoryLabel: string;
    typeLabel: string;
    health: string;
    raw: RecordMap;
    probePath: string;
  }> = [];

  identityProviders.value.forEach((item) => {
    list.push({
      id: String(item.record_id || item.id || "idp"),
      name: String(item.display_name || item.name || "身份认证服务"),
      category: "idp",
      categoryLabel: "身份认证",
      typeLabel: "OIDC / OAuth2 / SAML",
      health: String(item.last_health || "正常"),
      raw: item,
      probePath: "platform/identity-providers",
    });
  });

  annotationProviders.value.forEach((item) => {
    list.push({
      id: String(item.record_id || item.id || "annotator"),
      name: String(item.name || "数据标注引擎"),
      category: "annotation",
      categoryLabel: "数据标注",
      typeLabel: "CVAT / Label Studio",
      health: String(item.last_health || "正常"),
      raw: item,
      probePath: "data/annotation-providers",
    });
  });

  indexBackends.value.forEach((item) => {
    list.push({
      id: String(item.record_id || item.id || "index"),
      name: String(item.name || "向量特征库"),
      category: "index",
      categoryLabel: "向量特征库",
      typeLabel: "Qdrant / Milvus / ES",
      health: String(item.health || "正常"),
      raw: item,
      probePath: "search/index-backends",
    });
  });

  rerankers.value.forEach((item) => {
    list.push({
      id: String(item.record_id || item.id || "reranker"),
      name: String(item.name || "多模态检索重排"),
      category: "reranker",
      categoryLabel: "检索重排",
      typeLabel: "BGE / Cross-Encoder",
      health: String(item.health || "正常"),
      raw: item,
      probePath: "search/rerankers",
    });
  });

  if (adapterCategoryFilter.value === "all") return list;
  return list.filter((a) => a.category === adapterCategoryFilter.value);
});

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [requests, policy, adapters, indexes, rerank] = await Promise.all([
      api<RecordMap[]>("/api/v1/platform/projects/lifecycle-requests"),
      api<RecordMap>("/api/v1/platform/audit/retention"),
      api<RecordMap[]>("/api/v1/platform/identity-providers"),
      api<RecordMap[]>("/api/v1/search/index-backends"),
      api<RecordMap[]>("/api/v1/search/rerankers"),
    ]);
    lifecycle.value = requests;
    retention.value = policy;
    Object.assign(retentionForm, policy);
    identityProviders.value = adapters;
    indexBackends.value = indexes;
    rerankers.value = rerank;
    annotationProviders.value = await api<RecordMap[]>(
      "/api/v1/data/annotation-providers",
    );
  } catch (caught) {
    error.value = userFacingError(caught, "平台治理数据加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function mutate(action: () => Promise<void>): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    await action();
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "操作失败，请检查后重试");
  } finally {
    saving.value = false;
  }
}

async function requestLifecycle(): Promise<void> {
  if (!lifecycleForm.reason.trim()) return;
  await mutate(async () => {
    await api("/api/v1/platform/projects/lifecycle-requests", {
      method: "POST",
      body: JSON.stringify({
        project_id: lifecycleForm.project_id.trim(),
        action: lifecycleForm.action,
        reason: lifecycleForm.reason.trim(),
      }),
    });
    lifecycleForm.reason = "";
    showLifecycleModal.value = false;
  });
}

async function decide(request: RecordMap, approved: boolean): Promise<void> {
  await mutate(() =>
    api(
      `/api/v1/platform/projects/lifecycle-requests/${encodeURIComponent(String(request.record_id))}/decide`,
      {
        method: "POST",
        body: JSON.stringify({
          approved,
          comment: approved ? "控制台人工批准" : "控制台人工拒绝",
        }),
      },
    ).then(() => undefined),
  );
}

async function saveRetention(): Promise<void> {
  await mutate(async () => {
    await api("/api/v1/platform/audit/retention", {
      method: "PUT",
      body: JSON.stringify(retentionForm),
    });
    successMessage.value = "审计保留策略已成功保存并立即生效";
    setTimeout(() => {
      successMessage.value = "";
    }, 4000);
  });
}

async function probeAdapter(path: string, item: RecordMap): Promise<void> {
  const probeKey = String(item.record_id || path);
  probingIds.value.add(probeKey);
  error.value = "";
  try {
    await api(`/api/v1/${path}/${encodeURIComponent(String(item.record_id))}/probe`, {
      method: "POST",
    });
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "适配器健康探测异常");
  } finally {
    probingIds.value.delete(probeKey);
  }
}

async function probeAll(): Promise<void> {
  const tasks: Promise<void>[] = [];
  identityProviders.value.forEach((item) =>
    tasks.push(probeAdapter("platform/identity-providers", item)),
  );
  annotationProviders.value.forEach((item) =>
    tasks.push(probeAdapter("data/annotation-providers", item)),
  );
  indexBackends.value.forEach((item) =>
    tasks.push(probeAdapter("search/index-backends", item)),
  );
  rerankers.value.forEach((item) =>
    tasks.push(probeAdapter("search/rerankers", item)),
  );
  await Promise.allSettled(tasks);
}

function labelAction(action: unknown): string {
  switch (action) {
    case "disable":
      return "停用项目";
    case "restore":
      return "恢复项目";
    case "delete":
      return "删除项目";
    default:
      return String(action || "-");
  }
}

function actionBadgeClass(action: unknown): string {
  switch (action) {
    case "disable":
      return "action-disable";
    case "restore":
      return "action-restore";
    case "delete":
      return "action-delete";
    default:
      return "";
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page governance-page">
    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-if="successMessage" class="success-banner">{{ successMessage }}</p>

    <!-- 1. 顶部数据统计卡片 -->
    <section class="stats">
      <article class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">待审批申请</span>
          <div class="stat-icon-badge">
            <FileClock :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ pendingCount }}</strong>
        <small class="stat-desc">共 {{ lifecycle.length }} 项生命周期变更</small>
      </article>

      <article class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">已批准生效</span>
          <div class="stat-icon-badge">
            <CheckCircle2 :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ approvedCount }}</strong>
        <small class="stat-desc">项目停用 / 恢复 / 删除已就绪</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">审计日志保留</span>
          <div class="stat-icon-badge">
            <History :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ retentionForm.retention_days }} 天</strong>
        <small class="stat-desc">{{ retentionForm.enabled ? "自动归档与轮转已生效" : "自动轮转已暂停" }}</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">外部适配引擎</span>
          <div class="stat-icon-badge">
            <ShieldCheck :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ totalAdaptersCount }} 个</strong>
        <small class="stat-desc">认证、标注、向量库与重排服务</small>
      </article>
    </section>

    <!-- 2. 分段 Tab 导航 -->
    <div class="tabs-header-bar">
      <nav class="domain-tabs governance-tabs" aria-label="资源与安全模块">
        <button
          class="domain-tab-btn"
          :class="{ active: activeTab === 'lifecycle' }"
          @click="activeTab = 'lifecycle'"
        >
          <FileSpreadsheet :size="13" />
          <span>项目生命周期</span>
          <span class="tab-badge">{{ lifecycle.length }}</span>
        </button>

        <button
          class="domain-tab-btn"
          :class="{ active: activeTab === 'retention' }"
          @click="activeTab = 'retention'"
        >
          <ShieldCheck :size="13" />
          <span>审计保留与合规策略</span>
        </button>

        <button
          class="domain-tab-btn"
          :class="{ active: activeTab === 'adapters' }"
          @click="activeTab = 'adapters'"
        >
          <Layers :size="13" />
          <span>外部适配器运行健康</span>
          <span class="tab-badge">{{ totalAdaptersCount }}</span>
        </button>
      </nav>
    </div>

    <!-- ==================== Tab 1: 项目生命周期 ==================== -->
    <div v-if="activeTab === 'lifecycle'" class="tab-content">
      <!-- 过滤与操作工具栏 -->
      <div class="filter-controls">
        <div class="filter-left">
          <label class="filter-item">
            <Filter :size="12" class="filter-icon" />
            <span class="filter-label">审批状态:</span>
            <select v-model="statusFilter" class="filter-select">
              <option value="all">全部状态 (All)</option>
              <option value="pending">待审批 (Pending)</option>
              <option value="approved">已批准 (Approved)</option>
              <option value="rejected">已拒绝 (Rejected)</option>
            </select>
          </label>

          <label class="filter-item">
            <span class="filter-label">动作:</span>
            <select v-model="actionFilter" class="filter-select">
              <option value="all">全部动作</option>
              <option value="disable">停用项目 (Disable)</option>
              <option value="restore">恢复项目 (Restore)</option>
              <option value="delete">删除项目 (Delete)</option>
            </select>
          </label>

          <div class="search-box search-lg">
            <Search :size="13" class="search-icon" />
            <input
              v-model="searchQuery"
              placeholder="搜索项目标识或申请原因..."
              class="search-input"
            />
          </div>

          <span class="badge count-badge">共 {{ lifecycle.length }} 条记录</span>
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
            @click="showLifecycleModal = true"
          >
            <Plus :size="13" />
            <span>新建生命周期申请</span>
          </button>
        </div>
      </div>

      <!-- 生命周期数据表格 -->
      <section class="panel table-panel">
        <DataTable
          :columns="lifecycleColumns"
          :items="filteredLifecycle"
          :loading="loading"
          table-class="governance-table"
          wrapper-class="governance-table-wrapper"
          empty-text="暂无符合条件的生命周期申请记录"
        >
          <!-- 1. 项目 -->
          <template #project_id="{ row }">
            <span class="single-line-text mono bold">{{ row.project_id }}</span>
          </template>

          <!-- 2. 动作 -->
          <template #action="{ row }">
            <span class="badge action-badge" :class="actionBadgeClass(row.action)">
              {{ labelAction(row.action) }}
            </span>
          </template>

          <!-- 3. 原因 -->
          <template #reason="{ row }">
            <span
              class="single-line-text reason-text"
              :title="String(row.reason || '')"
            >
              {{ row.reason || '-' }}
            </span>
          </template>

          <!-- 4. 状态 -->
          <template #status="{ row }">
            <span
              class="badge status-badge"
              :class="row.status === 'approved' ? 'active' : row.status === 'pending' ? 'warn-badge' : 'error-badge'"
            >
              <span
                class="status-dot"
                :class="row.status === 'approved' ? 'dot-active' : row.status === 'pending' ? 'dot-warn' : 'dot-error'"
              />
              {{ row.status === 'approved' ? '已批准' : row.status === 'pending' ? '待审批' : '已拒绝' }}
            </span>
          </template>

          <!-- 5. 操作 -->
          <template #operations="{ row }">
            <div v-if="row.status === 'pending'" class="table-actions-row">
              <button
                class="button primary tiny-btn table-approve-btn"
                :disabled="saving"
                title="批准该生命周期申请"
                @click="decide(row, true)"
              >
                <Check :size="11" />批准
              </button>
              <button
                class="button danger tiny-btn table-reject-btn"
                :disabled="saving"
                title="拒绝申请"
                @click="decide(row, false)"
              >
                <X :size="11" />拒绝
              </button>
            </div>
            <span v-else class="muted-text">-</span>
          </template>
        </DataTable>
      </section>
    </div>

    <!-- ==================== Tab 2: 审计保留与合规策略 ==================== -->
    <div v-if="activeTab === 'retention'" class="tab-content retention-layout-grid">
      <!-- 左侧：策略配置卡片 -->
      <section class="panel retention-config-card">
        <div class="panel-header">
          <div class="panel-title-box">
            <History :size="15" class="header-icon" />
            <div>
              <h3>审计日志数据生命周期配置</h3>
              <p>设置全局审计事件与合规证据归档的最短保留周期与自动化维护策略</p>
            </div>
          </div>
        </div>

        <form class="retention-form-body" @submit.prevent="saveRetention">
          <div class="form-field">
            <span class="field-label">日志保留天数 (Retention Days) <em class="required">*</em></span>
            <div class="retention-input-row">
              <input
                v-model.number="retentionForm.retention_days"
                type="number"
                min="1"
                max="3650"
                class="field-input retention-days-input mono"
                required
              />
              <span class="unit-text">天</span>

              <!-- 快捷天数标签 -->
              <div class="quick-days-pills">
                <button
                  type="button"
                  class="quick-pill"
                  :class="{ selected: retentionForm.retention_days === 90 }"
                  @click="retentionForm.retention_days = 90"
                >
                  90 天 (季度)
                </button>
                <button
                  type="button"
                  class="quick-pill"
                  :class="{ selected: retentionForm.retention_days === 180 }"
                  @click="retentionForm.retention_days = 180"
                >
                  180 天 (半年)
                </button>
                <button
                  type="button"
                  class="quick-pill"
                  :class="{ selected: retentionForm.retention_days === 365 }"
                  @click="retentionForm.retention_days = 365"
                >
                  365 天 (1年)
                </button>
                <button
                  type="button"
                  class="quick-pill"
                  :class="{ selected: retentionForm.retention_days === 730 }"
                  @click="retentionForm.retention_days = 730"
                >
                  730 天 (2年)
                </button>
              </div>
            </div>
            <small class="field-hint">建议根据行业合规（如等保三级、GDPR）要求设置不低于 180 天的保留期。</small>
          </div>

          <div class="switches-list">
            <label class="switch-item">
              <input
                v-model="retentionForm.enabled"
                type="checkbox"
                class="switch-checkbox"
              />
              <div class="switch-text-box">
                <strong>启用审计日志自动清理与轮转</strong>
                <p>系统将在每日凌晨闲时自动归档并清理超出保留天数的历史审计事件，保持数据库轻量高效。</p>
              </div>
            </label>

            <label class="switch-item">
              <input
                v-model="retentionForm.export_approval_required"
                type="checkbox"
                class="switch-checkbox"
              />
              <div class="switch-text-box">
                <strong>审计日志导出要求合规审批 (Export Approval)</strong>
                <p>开启后，导出审计归档或证据包需经平台管理员/安全主管审核批准后方可下载。</p>
              </div>
            </label>
          </div>

          <div class="form-actions-bar">
            <button
              type="submit"
              class="button primary tiny-btn save-policy-btn"
              :disabled="saving"
            >
              <Save :size="13" />
              <span>保存保留策略</span>
            </button>
            <span v-if="retention" class="current-config-pill">
              当前运行配置：{{ retention.retention_days }} 天 · {{ retention.enabled ? '自动清理生效中' : '自动清理未启用' }}
            </span>
          </div>
        </form>
      </section>

      <!-- 右侧：合规规范与准则说明 -->
      <section class="panel compliance-guide-card">
        <div class="panel-header">
          <div class="panel-title-box">
            <Shield :size="15" class="header-icon" />
            <div>
              <h3>安全与合规要求指引</h3>
              <p>企业级平台审计日志保存规范说明</p>
            </div>
          </div>
        </div>

        <div class="compliance-body">
          <div class="guide-item">
            <strong class="guide-title">等保 2.0 / 等保三级要求</strong>
            <p>《网络安全法》第二十一条规定：采取监测、记录网络运行状态、网络安全事件的技术措施，并按照规定留存相关的网络日志不少于<strong>六个月（180天）</strong>。</p>
          </div>

          <div class="guide-item">
            <strong class="guide-title">不可篡改与只读保护</strong>
            <p>所有审计事件写入即不可变更（Append-Only），系统自动生成不可变流水号与 SHA256 签名，保障司法证据效力。</p>
          </div>

          <div class="guide-item">
            <strong class="guide-title">多租户生命周期隔离</strong>
            <p>项目生命周期的变更（停用、恢复、销毁）全程记录于审计中心，支持随时导出合规归档证据包。</p>
          </div>
        </div>
      </section>
    </div>

    <!-- ==================== Tab 3: 外部适配器运行健康 ==================== -->
    <div v-if="activeTab === 'adapters'" class="tab-content">
      <!-- 过滤与探测工具栏 -->
      <div class="filter-controls">
        <div class="filter-left">
          <label class="filter-item">
            <Filter :size="12" class="filter-icon" />
            <span class="filter-label">服务类别:</span>
            <select v-model="adapterCategoryFilter" class="filter-select">
              <option value="all">全部类别 (All)</option>
              <option value="idp">身份认证服务 (IdP)</option>
              <option value="annotation">数据标注引擎 (Annotator)</option>
              <option value="index">向量特征库 (Vector Index)</option>
              <option value="reranker">检索重排服务 (Reranker)</option>
            </select>
          </label>

          <span class="badge count-badge">共 {{ allAdapters.length }} 个外部引擎适配器</span>
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
            :disabled="saving"
            @click="probeAll"
          >
            <Activity :size="13" />
            <span>一键全量探测</span>
          </button>
        </div>
      </div>

      <!-- 适配器卡片网格 -->
      <div class="adapters-cards-grid">
        <article
          v-for="adapter in allAdapters"
          :key="adapter.id"
          class="panel adapter-card-item"
        >
          <div class="adapter-card-top">
            <div class="adapter-header-info">
              <span class="badge category-tag" :class="adapter.category">
                {{ adapter.categoryLabel }}
              </span>
              <strong class="adapter-display-name">{{ adapter.name }}</strong>
            </div>

            <span class="badge status-badge active">
              <span class="status-dot dot-active" />
              {{ adapter.health || "正常 (Healthy)" }}
            </span>
          </div>

          <div class="adapter-card-body">
            <div class="adapter-meta-row">
              <span class="meta-label">驱动协议:</span>
              <span class="meta-value">{{ adapter.typeLabel }}</span>
            </div>
            <div class="adapter-meta-row">
              <span class="meta-label">适配标识:</span>
              <span class="meta-value mono muted">{{ adapter.id }}</span>
            </div>
          </div>

          <div class="adapter-card-footer">
            <span class="health-status-hint">
              <Radio :size="12" class="status-icon" />
              <span>状态正常</span>
            </span>

            <button
              class="button secondary tiny-btn probe-action-btn"
              :disabled="probingIds.has(String(adapter.raw.record_id || adapter.probePath))"
              @click="probeAdapter(adapter.probePath, adapter.raw)"
            >
              <RefreshCw
                :size="11"
                :class="{ spinning: probingIds.has(String(adapter.raw.record_id || adapter.probePath)) }"
              />
              <span>立即探测</span>
            </button>
          </div>
        </article>

        <div v-if="!allAdapters.length" class="panel empty-state">
          <Layers :size="36" class="empty-icon" />
          <p>当前筛选条件下暂无外部适配器配置</p>
        </div>
      </div>
    </div>

    <!-- ==================== 新建生命周期申请模态弹窗 ==================== -->
    <div
      v-if="showLifecycleModal"
      class="modal-overlay"
      @click.self="showLifecycleModal = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <ShieldAlert :size="17" class="modal-title-icon" />
            <div>
              <h3>提交项目生命周期申请</h3>
              <p>提交项目停用、恢复或删除变更申请，进入平台合规安全审批流程</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="requestLifecycle">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label">目标项目标识 <em class="required">*</em></span>
                <input
                  v-model="lifecycleForm.project_id"
                  placeholder="例如: default / smart-campus"
                  class="field-input mono"
                  required
                  autofocus
                />
              </label>

              <label class="form-field">
                <span class="field-label">生命周期动作 <em class="required">*</em></span>
                <select v-model="lifecycleForm.action" class="field-input">
                  <option value="disable">停用项目 (暂停API访问与调度)</option>
                  <option value="restore">恢复项目 (重新激活已停用项目)</option>
                  <option value="delete">删除项目 (申请彻底销毁项目资产)</option>
                </select>
              </label>
            </div>

            <label class="form-field" style="margin-top: 12px;">
              <span class="field-label">变更原因说明 <em class="required">*</em></span>
              <textarea
                v-model="lifecycleForm.reason"
                placeholder="请详细描述本次项目生命周期变更的业务背景、合规依据与影响范围..."
                class="field-input field-textarea"
                rows="3"
                required
              ></textarea>
            </label>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showLifecycleModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="saving || !lifecycleForm.reason.trim()"
            >
              <Plus :size="13" />确认提交审批
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.governance-page {
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

.governance-tabs {
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

/* 过滤控制栏 */
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
  padding: 10px 14px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.panel-title-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  color: var(--color-accent, #087682);
}

.panel-title-box h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.panel-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
}

/* 数据表格深度规范 */
:deep(.governance-table td),
:deep(.governance-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  font-size: 11.5px;
}

:deep(.governance-table th) {
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

.reason-text {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--graphite, #17211f);
}

.bold {
  font-weight: 600;
}

.action-badge {
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 3px;
}
.action-badge.action-disable {
  background: #fef3c7;
  color: #92400e;
}
.action-badge.action-restore {
  background: #dcfce7;
  color: #166534;
}
.action-badge.action-delete {
  background: #fee2e2;
  color: #991b1b;
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
.table-approve-btn:hover {
  background: #15803d;
}

.table-reject-btn {
  background: #dc2626;
  border-color: #dc2626;
  height: 20px !important;
  font-size: 10.5px;
}
.table-reject-btn:hover {
  background: #b91c1c;
}

.muted-text {
  color: var(--muted, #64716d);
  font-size: 11px;
}

/* Tab 2 审计保留布局 */
.retention-layout-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 12px;
}

@media (max-width: 900px) {
  .retention-layout-grid {
    grid-template-columns: 1fr;
  }
}

.retention-form-body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.retention-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.retention-days-input {
  width: 100px !important;
  text-align: center;
}

.unit-text {
  font-size: 12px;
  color: var(--graphite, #17211f);
  font-weight: 500;
}

.quick-days-pills {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
}

.quick-pill {
  padding: 3px 8px;
  font-size: 11px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  cursor: pointer;
  transition: all 0.15s ease;
}

.quick-pill:hover {
  background: #ffffff;
  border-color: var(--line-strong, #b7c2bd);
}

.quick-pill.selected {
  background: var(--color-accent-soft, #e4f1f1);
  color: var(--color-accent-hover, #065e67);
  border-color: var(--color-accent, #087682);
  font-weight: 600;
}

.field-hint {
  font-size: 11px;
  color: var(--muted, #64716d);
  margin-top: 4px;
}

.switches-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
}

.switch-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
}

.switch-checkbox {
  margin-top: 3px;
  accent-color: var(--color-accent, #087682);
  cursor: pointer;
}

.switch-text-box strong {
  display: block;
  font-size: 12px;
  color: var(--graphite, #17211f);
}

.switch-text-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.35;
}

.form-actions-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.current-config-pill {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.compliance-body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.guide-item {
  border-left: 2px solid var(--color-accent, #087682);
  padding-left: 10px;
}

.guide-title {
  font-size: 12px;
  color: var(--graphite, #17211f);
  display: block;
}

.guide-item p {
  margin: 3px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.45;
}

/* Tab 3 适配器网格 */
.adapters-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

.adapter-card-item {
  display: flex;
  flex-direction: column;
  padding: 12px;
  gap: 8px;
  transition: all 0.15s ease;
}

.adapter-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.adapter-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.adapter-header-info {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
}

.category-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #eef2f1;
  color: #2c3e38;
}

.adapter-display-name {
  font-size: 12.5px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.adapter-card-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  padding: 6px 8px;
}

.adapter-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.meta-label {
  color: var(--muted, #64716d);
  flex-shrink: 0;
}

.meta-value {
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.adapter-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 4px;
}

.health-status-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #166534;
}

.status-icon {
  color: #16a34a;
}

.probe-action-btn {
  height: 22px;
  padding: 0 8px;
  font-size: 11px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  gap: 8px;
  color: var(--muted, #64716d);
  text-align: center;
  grid-column: 1 / -1;
}

.empty-icon {
  color: #b7c2bd;
}

.empty-state p {
  margin: 0;
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}

.muted {
  color: var(--muted, #64716d);
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
  width: min(640px, 95vw);
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
