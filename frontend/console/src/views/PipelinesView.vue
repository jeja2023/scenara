<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import {
  labelDomain,
  labelOperator,
  labelPipeline,
  labelPipelineStatus,
} from "../labels";
import DataTable from "../components/DataTable.vue";
import type { Pipeline, TableColumn } from "../types";

const rows = ref<Pipeline[]>([]);
const loading = ref(false);
const error = ref("");

const columns: TableColumn<Pipeline>[] = [
  { key: "pipeline", label: "流水线" },
  { key: "version", label: "版本", class: "mono" },
  { key: "domain", label: "领域" },
  { key: "status", label: "状态" },
  { key: "nodes", label: "节点" },
  { key: "pausable", label: "暂停" },
];

async function refresh(): Promise<void> {
  loading.value = true;
  try {
    rows.value = await api<Pipeline[]>("/api/v1/pipelines");
  } catch (caught) {
    error.value = userFacingError(caught, "流水线加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}
onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <section class="panel">
      <DataTable
        :columns="columns"
        :items="rows"
        :loading="loading"
        empty-text="暂无流水线"
      >
        <template #pipeline="{ row }">
          <strong>{{ labelPipeline(row.pipeline_id) }}</strong>
        </template>
        <template #domain="{ row }">
          {{ labelDomain(row.domain) }}
        </template>
        <template #status="{ row }">
          <span class="badge" :class="row.status">{{
            labelPipelineStatus(row.status)
          }}</span>
        </template>
        <template #nodes="{ row }">
          {{
            row.nodes
              .map((node: any) => labelOperator(node.operator_id))
              .join(" → ")
          }}
        </template>
        <template #pausable="{ row }">
          {{ row.pausable ? "支持" : "不支持" }}
        </template>
      </DataTable>
    </section>
  </section>
</template>
