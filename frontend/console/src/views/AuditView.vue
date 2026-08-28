<script setup lang="ts">
import { Download, RotateCcw, Search } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, apiBlob, userFacingError } from "../api";
import DataTable from "../components/DataTable.vue";
import type { AuditEvent, TableColumn } from "../types";

const events = ref<AuditEvent[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref("");
const offset = ref(0);
const PAGE_SIZE = 20;

const filters = reactive({
  action: "",
  resource_type: "",
  principal_id: "",
  outcome: "",
});

const columns: TableColumn<AuditEvent>[] = [
  { key: "created_at", label: "时间", width: "160px" },
  { key: "action", label: "操作", width: "200px" },
  { key: "resource", label: "资源", width: "160px" },
  { key: "principal_id", label: "主体", width: "120px" },
  { key: "outcome", label: "结果", width: "100px" },
  { key: "evidence", label: "证据" },
];

function resetFilters(): void {
  filters.action = "";
  filters.resource_type = "";
  filters.principal_id = "";
  filters.outcome = "";
  offset.value = 0;
  void refresh();
}

function query(): string {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset.value),
  });
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  return params.toString();
}

function goToPage(nextOffset: number): void {
  offset.value = Math.max(0, nextOffset);
  void refresh();
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const page = await api<{ items: AuditEvent[]; total: number }>(
      "/api/v1/audit/events?" + query(),
    );
    events.value = page.items;
    total.value = page.total;
  } catch (caught) {
    error.value = userFacingError(caught, "审计日志加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function exportAudit(format: "csv" | "json"): Promise<void> {
  try {
    const blob = await apiBlob(
      `/api/v1/audit/export?format=${format}&${query()}`,
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-${Date.now()}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (caught) {
    error.value = userFacingError(caught, "导出失败，请稍后重试");
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

function formatEvidence(evidence: Record<string, unknown> | null | undefined): string {
  if (!evidence || Object.keys(evidence).length === 0) return "-";
  return JSON.stringify(evidence);
}

function outcomeLabel(outcome: string): string {
  switch (outcome) {
    case "success":
      return "成功";
    case "failure":
      return "失败";
    case "denied":
      return "拒绝";
    default:
      return outcome || "-";
  }
}

function outcomeClass(outcome: string): string {
  if (outcome === "success") return "active";
  if (outcome === "failure") return "error-badge";
  if (outcome === "denied") return "warn-badge";
  return "";
}

function outcomeDotClass(outcome: string): string {
  if (outcome === "success") return "dot-active";
  if (outcome === "failure") return "dot-error";
  if (outcome === "denied") return "dot-warn";
  return "dot-dev";
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <!-- 合并排列的精简过滤栏 -->
    <div class="panel filters-panel">
      <div class="filter-toolbar">
        <div class="filter-item">
          <span class="filter-label">动作</span>
          <input
            v-model="filters.action"
            type="text"
            class="filter-input"
            placeholder="如 run.completed"
            @keyup.enter="refresh"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">资源类型</span>
          <input
            v-model="filters.resource_type"
            type="text"
            class="filter-input"
            placeholder="如 run / media"
            @keyup.enter="refresh"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">主体</span>
          <input
            v-model="filters.principal_id"
            type="text"
            class="filter-input"
            placeholder="如 sys:runtime"
            @keyup.enter="refresh"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">结果</span>
          <select v-model="filters.outcome" class="filter-select" @change="refresh">
            <option value="">全部</option>
            <option value="success">成功</option>
            <option value="failure">失败</option>
            <option value="denied">拒绝</option>
          </select>
        </div>
        <div class="filter-actions">
          <button class="button primary filter-btn" @click="refresh">
            <Search :size="13" />查询
          </button>
          <button class="button secondary filter-btn" @click="resetFilters">
            <RotateCcw :size="13" />重置
          </button>
        </div>
      </div>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <!-- 审计事件数据面板 -->
    <section class="panel audit-panel">
      <div class="panel-header">
        <div class="header-title">
          <h2>审计事件</h2>
          <span class="badge">{{ total }}</span>
        </div>
        <div class="header-actions">
          <button class="button secondary export-btn" @click="exportAudit('csv')">
            <Download :size="13" />导出 CSV
          </button>
          <button class="button secondary export-btn" @click="exportAudit('json')">
            <Download :size="13" />导出 JSON
          </button>
        </div>
      </div>

      <DataTable
        :columns="columns"
        :items="events"
        :loading="loading"
        :total="total"
        :offset="offset"
        :page-size="PAGE_SIZE"
        :page-size-options="[10, 20, 50, 100]"
        :index-offset="offset"
        table-class="audit-table"
        wrapper-class="audit-table-wrapper"
        empty-text="没有匹配的审计事件"
        loading-text="正在加载审计记录…"
        @page-change="goToPage"
      >
        <!-- 1. 时间 -->
        <template #created_at="{ row }">
          <span class="mono time-text">{{ formatTime(row.created_at) }}</span>
        </template>

        <!-- 2. 操作 -->
        <template #action="{ row }">
          <span class="single-line-text action-name" :title="`ID: ${row.event_id}`">
            {{ row.action }}
          </span>
        </template>

        <!-- 3. 资源 -->
        <template #resource="{ row }">
          <span
            class="single-line-text resource-name"
            :title="row.resource_id ? `资源ID: ${row.resource_id}` : undefined"
          >
            {{ row.resource_type }}
          </span>
        </template>

        <!-- 4. 主体 -->
        <template #principal_id="{ row }">
          <span class="single-line-text mono principal-name">{{ row.principal_id || '-' }}</span>
        </template>

        <!-- 5. 结果 -->
        <template #outcome="{ row }">
          <span class="badge status-badge" :class="outcomeClass(row.outcome)">
            <span class="status-dot" :class="outcomeDotClass(row.outcome)" />
            {{ outcomeLabel(row.outcome) }}
          </span>
        </template>

        <!-- 6. 证据 -->
        <template #evidence="{ row }">
          <span
            class="evidence-text mono"
            :title="JSON.stringify(row.evidence, null, 2)"
          >
            {{ formatEvidence(row.evidence) }}
          </span>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 紧凑横向合并排列的搜索过滤栏 */
.filters-panel {
  padding: 10px 14px;
  background: #ffffff;
}

.filter-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.filter-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.filter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.filter-input {
  height: 28px;
  line-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  width: 140px;
  outline: none;
  box-sizing: border-box;
  transition: all 0.15s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}

.filter-input:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.filter-input::placeholder {
  color: #94a3b8;
  font-size: 11px;
}

.filter-select {
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
  min-width: 85px;
  cursor: pointer;
  transition: all 0.15s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}

.filter-select:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.filter-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.filter-btn {
  height: 28px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 头部样式 */
.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-header h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.export-btn {
  height: 28px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 锁定表格容器最小高度防止跳动 */
:deep(.audit-table-wrapper .table-scroll) {
  min-height: 440px;
}

/* 单行表格单元格样式（绝对不换行） */
:deep(.audit-table td),
:deep(.audit-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 8px 12px;
  height: 38px;
  box-sizing: border-box;
}

.time-text {
  font-size: 11.5px;
  color: var(--muted, #64716d);
  white-space: nowrap;
}

.action-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.resource-name {
  font-size: 12px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.principal-name {
  font-size: 11.5px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.evidence-text {
  display: block;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  white-space: nowrap;
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

@media (max-width: 900px) {
  .filter-toolbar {
    gap: 8px;
  }
  .filter-input {
    width: 110px;
  }
  .filter-actions {
    margin-left: 0;
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
