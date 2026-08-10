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
import type { Pipeline } from "../types";

const rows = ref<Pipeline[]>([]);
const loading = ref(false);
const error = ref("");
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
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>流水线</th>
              <th>版本</th>
              <th>领域</th>
              <th>状态</th>
              <th>节点</th>
              <th>暂停</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in rows"
              :key="row.pipeline_id + row.version"
            >
              <td class="muted">{{ index + 1 }}</td>
              <td>
                <strong>{{ labelPipeline(row.pipeline_id) }}</strong>
                <div class="mono muted">{{ row.pipeline_id }}</div>
              </td>
              <td class="mono">{{ row.version }}</td>
              <td>{{ labelDomain(row.domain) }}</td>
              <td>
                <span class="badge" :class="row.status">{{
                  labelPipelineStatus(row.status)
                }}</span>
              </td>
              <td>
                {{
                  row.nodes
                    .map((node) => labelOperator(node.operator_id))
                    .join(" → ")
                }}
              </td>
              <td>{{ row.pausable ? "支持" : "不支持" }}</td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="7" class="empty">暂无流水线</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
