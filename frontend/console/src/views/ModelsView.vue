<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import type { DomainManifest } from "../types";

const domains = ref<DomainManifest[]>([]);
const error = ref("");
onMounted(async () => { try { domains.value = await api<DomainManifest[]>("/api/v1/domains"); } catch (caught) { error.value = caught instanceof Error ? caught.message : String(caught); } });
</script>

<template><section class="page"><div class="page-header"><div><h1>模型</h1><p>模型包必须包含来源、许可证、摘要、模型卡和回归样例。</p></div></div><p v-if="error" class="callout error">{{ error }}</p><p class="callout">当前版本不允许通过控制台上传模型或执行代码。模型包由离线交付流程安装，运行结果记录实际模型来源。</p><section class="panel model-panel"><div class="panel-header"><h2>领域能力声明</h2></div><div class="table-scroll"><table class="data-table"><thead><tr><th>领域</th><th>能力</th><th>契约版本</th><th>注册状态</th><th>模型就绪</th></tr></thead><tbody><tr v-for="domain in domains" :key="domain.domain_id"><td><strong>{{ domain.display_name }}</strong></td><td>{{ domain.capabilities.join(" · ") }}</td><td class="mono">{{ domain.schema_version }}</td><td><span class="badge active">build-time</span></td><td><span class="badge">由 Run 证据确认</span></td></tr></tbody></table></div></section></section></template>

<style scoped>.model-panel { margin-top: 14px; }</style>
