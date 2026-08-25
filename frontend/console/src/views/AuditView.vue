<script setup lang="ts">
import { Download, Filter, RotateCcw, Search } from "@lucide/vue";
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
  { key: "created_at", label: "时间" },
  { key: "action", label: "操作" },
  { key: "resource", label: "资源" },
  { key: "principal_id", label: "主体" },
  { key: "outcome", label: "结果" },
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
  for (const [key, value] of Object.entries(filters))
    if (value.trim()) params.set(key, value.trim());
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
  return new Date(epoch * 1000).toLocaleString();
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <div class="panel filters">
      <div class="filters-grid">
        <label
          ><span>动作</span
          ><input
            v-model="filters.action"
            placeholder="如 run.completed"
            @keyup.enter="refresh"
        /></label>
        <label
          ><span>资源类型</span
          ><input
            v-model="filters.resource_type"
            placeholder="如 run"
            @keyup.enter="refresh"
        /></label>
        <label
          ><span>主体</span
          ><input
            v-model="filters.principal_id"
            placeholder="如 sys:runtime"
            @keyup.enter="refresh"
        /></label>
        <label
          ><span>结果</span
          ><select v-model="filters.outcome" @change="refresh">
            <option value="">全部</option>
            <option value="success">成功</option>
            <option value="failure">失败</option>
            <option value="denied">拒绝</option>
          </select></label
        >
      </div>
      <div class="filter-actions">
        <button class="button primary" @click="refresh">
          <Search :size="15" />查询
        </button>
        <button class="button secondary" @click="resetFilters">
          <RotateCcw :size="15" />重置
        </button>
      </div>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <section class="panel">
      <div class="panel-header">
        <div class="header-title">
          <h2>审计事件</h2>
          <span class="badge">{{ total }}</span>
        </div>
        <div class="header-actions">
          <button class="button secondary" @click="exportAudit('csv')">
            <Download :size="15" />导出 CSV
          </button>
          <button class="button secondary" @click="exportAudit('json')">
            <Download :size="15" />导出 JSON
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
        :index-offset="offset"
        empty-text="没有匹配的审计事件"
        loading-text="正在加载审计记录…"
        @page-change="goToPage"
      >
        <template #created_at="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
        <template #action="{ row }">
          <strong>{{ row.action }}</strong>
          <small class="mono">{{ row.event_id }}</small>
        </template>
        <template #resource="{ row }">
          {{ row.resource_type }}
          <small class="mono">{{ row.resource_id || "-" }}</small>
        </template>
        <template #outcome="{ row }">
          <span :class="['outcome', row.outcome]">{{
            row.outcome === "success" ? "成功" : row.outcome
          }}</span>
        </template>
        <template #evidence="{ row }">
          <code>{{ JSON.stringify(row.evidence) }}</code>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.filter-panel {
  margin-bottom: 16px;
}
.filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) 110px;
  gap: 14px;
  align-items: end;
}
.filter-actions {
  display: flex;
  align-items: flex-end;
}
.filter-submit {
  width: 100%;
  height: 36px;
}
label {
  display: grid;
  gap: 6px;
  color: #45534f;
  font-size: 12px;
  font-weight: 650;
}
.table-wrap {
  overflow-x: auto;
}
.panel-header h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text, #17211f);
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
td strong,
td small {
  display: block;
}
td small {
  color: var(--muted, #64716d);
  margin-top: 2px;
  font-size: 11px;
}
code {
  display: block;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
  font-size: 11px;
  color: #526066;
}
.outcome {
  color: var(--muted, #64716d);
  font-size: 11.5px;
}
.outcome.success {
  color: #0b7557;
  font-weight: 600;
}
.muted {
  color: var(--muted, #64716d);
  font-size: 11px;
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 28px;
}
@media (max-width: 900px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .filter-submit {
    width: 100%;
  }
}
</style>
