<script setup lang="ts">
import { Eye, RefreshCw } from "@lucide/vue";
import { RouterLink } from "vue-router";
import DataTable from "../../components/DataTable.vue";
import type { Domain, Run, TableColumn } from "../../types";

const columns: TableColumn<Run>[] = [
  { key: "run_id", label: "任务 ID", class: "mono truncate" },
  { key: "pipeline", label: "流水线", class: "truncate" },
  { key: "asset_source", label: "资产 / 来源", class: "mono truncate" },
  { key: "status", label: "状态" },
  { key: "created_at", label: "提交时间", class: "muted" },
  { key: "actions", label: "操作", width: "80px" },
];

defineProps<{
  domain: Domain;
  domainLabel: string;
  formatRunDate: (value: number) => string;
  items: Run[];
  labelPipeline: (pipelineId: string) => string;
  labelRunStatus: (status: Run["status"]) => string;
  loading: boolean;
}>();

const emit = defineEmits<{
  detail: [run: Run];
  refresh: [];
}>();
</script>

<template>
  <section class="panel history-panel">
    <div class="panel-header">
      <div class="history-title-group">
        <h2>最近运行</h2>
        <p>{{ domainLabel }} 最近运行记录</p>
      </div>
      <div class="toolbar compact history-toolbar">
        <button
          class="button secondary"
          :disabled="loading"
          @click="emit('refresh')"
        >
          <RefreshCw :size="14" :class="{ spin: loading }" />刷新
        </button>
        <RouterLink
          class="button secondary"
          :to="{ path: '/runs', query: { domain } }"
        >
          查看全部
        </RouterLink>
      </div>
    </div>
    <DataTable
      :columns="columns"
      :items="items"
      :loading="loading"
      loading-text="正在加载历史运行..."
      :empty-text="`暂无 ${domainLabel} 历史运行记录`"
    >
      <template #pipeline="{ row }">
        <strong>{{ labelPipeline(row.pipeline.pipeline_id) }}</strong>
        <small v-if="row.pipeline.version" class="muted">
          · {{ row.pipeline.version }}</small
        >
      </template>
      <template #asset_source="{ row }">
        {{ row.asset_id || row.source_id || "-" }}
      </template>
      <template #status="{ row }">
        <span class="badge" :class="row.status">{{
          labelRunStatus(row.status)
        }}</span>
      </template>
      <template #created_at="{ row }">
        {{ formatRunDate(row.created_at) }}
      </template>
      <template #actions="{ row }">
        <button
          class="button secondary history-detail-btn"
          title="查看此任务解析结果与回看"
          @click="emit('detail', row)"
        >
          <Eye :size="13" />详情
        </button>
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.history-panel {
  margin-top: 14px;
}
.history-panel .history-title-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.history-panel .history-title-group h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text, #17211f);
  white-space: nowrap;
}
.history-panel .history-title-group p,
.history-panel .panel-header p {
  margin: 0;
  color: var(--muted, #64716d);
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
}
.history-toolbar {
  display: flex !important;
  flex-direction: row !important;
  align-items: center !important;
  flex-wrap: nowrap !important;
  gap: 8px !important;
  margin-left: auto;
}
.history-detail-btn {
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  font-size: 12px;
}
.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
