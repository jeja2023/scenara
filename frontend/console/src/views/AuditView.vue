<script setup lang="ts">
import { ChevronLeft, ChevronRight, Download, Filter, RotateCcw, Search } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, apiBlob, userFacingError } from "../api";
import type { AuditEvent } from "../types";

const events = ref<AuditEvent[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref("");
const offset = ref(0);
const PAGE_SIZE = 50;
const filters = reactive({
  action: "",
  resource_type: "",
  principal_id: "",
  outcome: "",
});

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
      `/api/v1/audit/events?${query()}`,
    );
    events.value = page.items;
    total.value = page.total;
    if (page.items.length === 0 && offset.value > 0) {
      offset.value = Math.max(0, total.value - PAGE_SIZE);
      const retry = await api<{ items: AuditEvent[]; total: number }>(
        `/api/v1/audit/events?${query()}`,
      );
      events.value = retry.items;
      total.value = retry.total;
    }
  } catch (caught) {
    error.value = userFacingError(caught, "审计记录加载失败");
  } finally {
    loading.value = false;
  }
}

async function exportAudit(format: "json" | "csv"): Promise<void> {
  try {
    const blob = await apiBlob(
      `/api/v1/audit/export?format=${format}&${query()}`,
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `scenara-audit.${format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (caught) {
    error.value = userFacingError(caught, "审计导出失败");
  }
}

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false });
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel filter-panel">
      <div class="panel-header">
        <h2>审计日志筛选</h2>
        <button class="button secondary" @click="resetFilters">
          <RotateCcw :size="14" />重置条件
        </button>
      </div>
      <div class="panel-body">
        <div class="filter-grid">
          <label
            ><span>操作名称</span
            ><input
              v-model="filters.action"
              placeholder="例如 dataset.create"
              @keyup.enter="refresh"
          /></label>
          <label
            ><span>资源类型</span
            ><input
              v-model="filters.resource_type"
              placeholder="例如 dataset"
              @keyup.enter="refresh"
          /></label>
          <label
            ><span>操作主体</span
            ><input
              v-model="filters.principal_id"
              placeholder="用户或服务账号"
              @keyup.enter="refresh"
          /></label>
          <label
            ><span>执行结果</span
            ><select v-model="filters.outcome" @change="refresh">
              <option value="">全部结果</option>
              <option value="success">成功</option>
              <option value="failure">失败</option>
            </select></label
          >
          <div class="filter-actions">
            <button class="button primary filter-submit" @click="refresh">
              <Search :size="16" />查询记录
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <div class="header-title">
          <h2>事件记录</h2>
          <span class="badge">共 {{ total }} 条</span>
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
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>时间</th>
              <th>操作</th>
              <th>资源</th>
              <th>主体</th>
              <th>结果</th>
              <th>证据</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="7" class="empty">正在加载审计记录…</td>
            </tr>
            <tr v-for="(event, index) in events" :key="event.event_id">
              <td class="muted">{{ offset + index + 1 }}</td>
              <td>{{ formatTime(event.created_at) }}</td>
              <td>
                <strong>{{ event.action }}</strong
                ><small>{{ event.event_id }}</small>
              </td>
              <td>
                {{ event.resource_type
                }}<small>{{ event.resource_id || "-" }}</small>
              </td>
              <td>{{ event.principal_id }}</td>
              <td>
                <span :class="['outcome', event.outcome]">{{
                  event.outcome === "success" ? "成功" : event.outcome
                }}</span>
              </td>
              <td>
                <code>{{ JSON.stringify(event.evidence) }}</code>
              </td>
            </tr>
            <tr v-if="!loading && !events.length">
              <td colspan="7" class="empty">没有匹配的审计事件</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="total > 0" class="pagination">
        <span class="pagination-info">
          显示第 <strong>{{ offset + 1 }}-{{ Math.min(total, offset + PAGE_SIZE) }}</strong> 条，共 <strong>{{ total }}</strong> 条记录
        </span>
        <div class="pagination-controls">
          <button
            class="pagination-btn"
            :disabled="offset === 0 || loading"
            @click="goToPage(offset - PAGE_SIZE)"
          >
            <ChevronLeft :size="14" />上一页
          </button>
          <span class="pagination-page-indicator">{{ Math.floor(offset / PAGE_SIZE) + 1 }} / {{ Math.max(1, Math.ceil(total / PAGE_SIZE)) }}</span>
          <button
            class="pagination-btn"
            :disabled="offset + PAGE_SIZE >= total || loading"
            @click="goToPage(offset + PAGE_SIZE)"
          >
            下一页<ChevronRight :size="14" />
          </button>
        </div>
      </div>
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
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  border: 1px solid var(--line, #e2e8e6);
  padding: 10px 12px;
  text-align: left;
  vertical-align: middle;
  white-space: nowrap;
}
th {
  color: var(--muted, #64716d);
  font-weight: 600;
  font-size: 11.5px;
  background: #fafbfb;
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
