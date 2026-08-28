<script setup lang="ts">
import { Check, ShieldCheck } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";
import DataTable from "../components/DataTable.vue";
import type { TableColumn } from "../types";

type RecordMap = {
  record_id: string;
  period_started_at: number;
  [key: string]: string | number | boolean;
};

const lifecycleColumns: TableColumn<RecordMap>[] = [
  { key: "project_id", label: "项目标识", width: "160px" },
  { key: "action", label: "申请动作", width: "140px" },
  { key: "reason", label: "原因说明" },
  { key: "status", label: "审批状态", width: "110px" },
  { key: "operations", label: "操作", align: "right", headerAlign: "right", width: "100px" },
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

const lifecycleForm = reactive({
  project_id: "default",
  action: "disable",
  reason: "",
});
const retentionForm = reactive({
  retention_days: 365,
  export_approval_required: true,
  enabled: true,
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
  await mutate(async () => {
    await api("/api/v1/platform/projects/lifecycle-requests", {
      method: "POST",
      body: JSON.stringify(lifecycleForm),
    });
    lifecycleForm.reason = "";
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
          comment: approved ? "approved in Console" : "rejected in Console",
        }),
      },
    ).then(() => undefined),
  );
}

async function saveRetention(): Promise<void> {
  await mutate(() =>
    api("/api/v1/platform/audit/retention", {
      method: "PUT",
      body: JSON.stringify(retentionForm),
    }).then(() => undefined),
  );
}

async function probe(
  path: string,
  target: RecordMap | RecordMap[],
): Promise<void> {
  const item = Array.isArray(target) ? target[0] : target;
  if (!item) return;
  await mutate(() =>
    api(`/api/v1/${path}/${encodeURIComponent(String(item.record_id))}/probe`, {
      method: "POST",
    }).then(() => undefined),
  );
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

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="governance-grid">
      <!-- 1. 项目生命周期 -->
      <section class="panel lifecycle-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>项目生命周期申请</h2>
            <span class="badge">{{ lifecycle.length }}</span>
          </div>
        </div>
        <div class="panel-body">
          <div class="form-grid">
            <label class="form-field">
              <span class="field-label">目标项目</span>
              <input v-model="lifecycleForm.project_id" class="field-input" placeholder="如 default" />
            </label>
            <label class="form-field">
              <span class="field-label">生命周期动作</span>
              <select v-model="lifecycleForm.action" class="field-input">
                <option value="disable">停用 (disable)</option>
                <option value="restore">恢复 (restore)</option>
                <option value="delete">删除 (delete)</option>
              </select>
            </label>
            <label class="form-field span-2">
              <span class="field-label">申请原因</span>
              <input v-model="lifecycleForm.reason" class="field-input" placeholder="请填写项目生命周期变更原因" />
            </label>
            <div class="form-action-row">
              <button
                class="button primary submit-btn"
                :disabled="saving || !lifecycleForm.reason"
                @click="requestLifecycle"
              >
                <ShieldCheck :size="14" />提交审批
              </button>
            </div>
          </div>
        </div>

        <DataTable
          :columns="lifecycleColumns"
          :items="lifecycle"
          :loading="loading"
          table-class="governance-table"
          wrapper-class="governance-table-wrapper"
          empty-text="暂无待审批的生命周期记录"
        >
          <!-- 1. 项目 -->
          <template #project_id="{ row }">
            <span class="single-line-text mono bold">{{ row.project_id }}</span>
          </template>

          <!-- 2. 动作 -->
          <template #action="{ row }">
            <span class="single-line-text">{{ labelAction(row.action) }}</span>
          </template>

          <!-- 3. 原因 -->
          <template #reason="{ row }">
            <span class="single-line-text muted-text" :title="String(row.reason || '')">{{ row.reason || '-' }}</span>
          </template>

          <!-- 4. 状态 -->
          <template #status="{ row }">
            <span class="badge status-badge" :class="row.status === 'approved' ? 'active' : row.status === 'pending' ? 'warn-badge' : 'error-badge'">
              <span class="status-dot" :class="row.status === 'approved' ? 'dot-active' : row.status === 'pending' ? 'dot-warn' : 'dot-error'" />
              {{ row.status === 'approved' ? '已批准' : row.status === 'pending' ? '待审批' : '已拒绝' }}
            </span>
          </template>

          <!-- 5. 操作 -->
          <template #operations="{ row }">
            <button
              v-if="row.status === 'pending'"
              class="button secondary table-btn success-btn"
              :disabled="saving"
              @click="decide(row, true)"
            >
              <Check :size="12" />批准
            </button>
            <span v-else class="muted-text">-</span>
          </template>
        </DataTable>
      </section>

      <!-- 2. 审计保留策略 -->
      <section class="panel retention-panel">
        <div class="panel-header">
          <h2>审计保留策略</h2>
        </div>
        <div class="panel-body form-grid-retention">
          <label class="form-field">
            <span class="field-label">保留天数</span>
            <input
              v-model.number="retentionForm.retention_days"
              type="number"
              min="1"
              class="field-input number-input"
            />
          </label>
          <label class="checkbox-label">
            <input
              v-model="retentionForm.enabled"
              type="checkbox"
              class="checkbox-input"
            />启用自动清理策略
          </label>
          <div class="retention-actions">
            <button
              class="button primary submit-btn"
              :disabled="saving"
              @click="saveRetention"
            >
              保存策略
            </button>
            <span v-if="retention" class="muted-text retention-current">
              当前配置：{{ retention.retention_days }} 天
            </span>
          </div>
        </div>
      </section>

      <!-- 3. 外部适配器健康 -->
      <section class="panel adapter-panel">
        <div class="panel-header">
          <h2>外部适配器运行健康</h2>
        </div>
        <div class="adapter-list">
          <div v-for="item in identityProviders" :key="item.record_id" class="adapter-item">
            <div class="adapter-info">
              <span class="adapter-category">身份认证</span>
              <strong class="adapter-title">{{ item.display_name }}</strong>
            </div>
            <span class="badge status-badge active">
              <span class="status-dot dot-active" />
              {{ item.last_health || '正常' }}
            </span>
            <button
              class="button secondary probe-btn"
              :disabled="saving"
              @click="probe('platform/identity-providers', item)"
            >
              探测
            </button>
          </div>
          <div v-for="item in annotationProviders" :key="item.record_id" class="adapter-item">
            <div class="adapter-info">
              <span class="adapter-category">数据标注</span>
              <strong class="adapter-title">{{ item.name }}</strong>
            </div>
            <span class="badge status-badge active">
              <span class="status-dot dot-active" />
              {{ item.last_health || '正常' }}
            </span>
            <button
              class="button secondary probe-btn"
              :disabled="saving"
              @click="probe('data/annotation-providers', item)"
            >
              探测
            </button>
          </div>
          <div v-for="item in indexBackends" :key="item.record_id" class="adapter-item">
            <div class="adapter-info">
              <span class="adapter-category">向量索引</span>
              <strong class="adapter-title">{{ item.name }}</strong>
            </div>
            <span class="badge status-badge active">
              <span class="status-dot dot-active" />
              {{ item.health || '正常' }}
            </span>
            <button
              class="button secondary probe-btn"
              :disabled="saving"
              @click="probe('search/index-backends', item)"
            >
              探测
            </button>
          </div>
          <div v-for="item in rerankers" :key="item.record_id" class="adapter-item">
            <div class="adapter-info">
              <span class="adapter-category">检索重排</span>
              <strong class="adapter-title">{{ item.name }}</strong>
            </div>
            <span class="badge status-badge active">
              <span class="status-dot dot-active" />
              {{ item.health || '正常' }}
            </span>
            <button
              class="button secondary probe-btn"
              :disabled="saving"
              @click="probe('search/rerankers', item)"
            >
              探测
            </button>
          </div>
          <p
            v-if="
              !identityProviders.length &&
              !annotationProviders.length &&
              !indexBackends.length &&
              !rerankers.length
            "
            class="empty-tip"
          >
            暂未配置外部适配器
          </p>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.governance-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, 1fr);
}

.lifecycle-panel,
.adapter-panel {
  grid-column: span 2;
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
  grid-template-columns: 180px 180px 1fr auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 12px;
}

.span-2 {
  grid-column: span 1;
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
  white-space: nowrap;
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

.submit-btn {
  height: 28px;
  padding: 0 12px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 审计保留表单 */
.form-grid-retention {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.number-input {
  width: 100px;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--graphite, #17211f);
  cursor: pointer;
  margin-top: 16px;
}

.checkbox-input {
  cursor: pointer;
}

.retention-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
}

.retention-current {
  font-size: 11px;
  color: var(--muted, #64716d);
}

/* 适配器健康列表 */
.adapter-list {
  display: grid;
  gap: 6px;
}

.adapter-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #fafbfb;
  gap: 12px;
}

.adapter-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.adapter-category {
  font-size: 11px;
  color: var(--muted, #64716d);
  background: #eef2f1;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}

.adapter-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.probe-btn {
  height: 22px;
  padding: 0 8px;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.empty-tip {
  font-size: 11.5px;
  color: var(--muted, #64716d);
  padding: 12px;
  text-align: center;
}

/* 全局 28px 标准表格样式 */
:deep(.governance-table td),
:deep(.governance-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  line-height: 1.3;
}

:deep(.governance-table tr) {
  height: 28px;
}

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

.muted-text {
  color: var(--muted, #64716d);
  font-size: 11px;
}

:deep(.governance-table .badge),
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

.table-btn {
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

.error-badge {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.warn-badge {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

@media (max-width: 900px) {
  .governance-grid {
    grid-template-columns: 1fr;
  }
  .lifecycle-panel,
  .adapter-panel {
    grid-column: auto;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
