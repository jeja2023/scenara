<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, userFacingError } from "../api";
import { labelDomain, labelOperator, labelPipeline, labelPipelineStatus } from "../labels";
import type { Pipeline } from "../types";

const rows = ref<Pipeline[]>([]);
const error = ref("");
async function refresh(): Promise<void> {
  try { rows.value = await api<Pipeline[]>("/api/v1/pipelines"); }
  catch (caught) { error.value = userFacingError(caught, "流水线加载失败，请稍后重试"); }
}
onMounted(refresh);
</script>

<template><section class="page"><div class="page-header"><div><h1>流水线</h1><p>不可变版本与构建期注册拓扑。</p></div><button class="button secondary" @click="refresh">刷新</button></div><p v-if="error" class="callout error">{{ error }}</p><section class="panel"><div class="table-scroll"><table class="data-table"><thead><tr><th>流水线</th><th>版本</th><th>领域</th><th>状态</th><th>节点</th><th>暂停</th></tr></thead><tbody><tr v-for="row in rows" :key="row.pipeline_id + row.version"><td><strong>{{ labelPipeline(row.pipeline_id) }}</strong><div class="mono muted">{{ row.pipeline_id }}</div></td><td class="mono">{{ row.version }}</td><td>{{ labelDomain(row.domain) }}</td><td><span class="badge" :class="row.status">{{ labelPipelineStatus(row.status) }}</span></td><td>{{ row.nodes.map((node) => labelOperator(node.operator_id)).join(" → ") }}</td><td>{{ row.pausable ? "支持" : "不支持" }}</td></tr></tbody></table><div v-if="!rows.length" class="empty">暂无流水线</div></div></section></section></template>
