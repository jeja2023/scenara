<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import { labelRuntime } from "../labels";

interface Status { version: string; profile: string; state_backend: string; object_backend: string; queue_backend: string; production_models_required: boolean; auth_required: boolean }
const status = ref<Status | null>(null);
const error = ref("");
async function refresh(): Promise<void> { try { status.value = await api<Status>("/api/v1/system/status"); } catch (caught) { error.value = caught instanceof Error ? caught.message : String(caught); } }
onMounted(refresh);
</script>

<template><section class="page"><div class="page-header"><div><h1>运维</h1><p>运行后端与生产门禁状态。</p></div><button class="button secondary" @click="refresh">刷新</button></div><p v-if="error" class="callout error">{{ error }}</p><div v-if="status" class="stats"><div class="stat teal"><span>配置档</span><strong>{{ labelRuntime(status.profile) }}</strong><small>Scenara {{ status.version }}</small></div><div class="stat"><span>状态存储</span><strong>{{ labelRuntime(status.state_backend) }}</strong><small>唯一事实源</small></div><div class="stat"><span>对象存储</span><strong>{{ labelRuntime(status.object_backend) }}</strong><small>媒体与结果文档</small></div><div class="stat green"><span>队列</span><strong>{{ labelRuntime(status.queue_backend) }}</strong><small>执行投递</small></div></div><section class="panel"><div class="panel-header"><h2>门禁</h2></div><div class="panel-body checks"><div><span>接口认证</span><strong :class="status?.auth_required ? 'ok' : 'warn'">{{ status?.auth_required ? "开启" : "开发关闭" }}</strong></div><div><span>生产模型强制</span><strong :class="status?.production_models_required ? 'ok' : 'warn'">{{ status?.production_models_required ? "开启" : "开发关闭" }}</strong></div><div><span>审计持久化</span><strong class="warn">数据结构已建立</strong></div><div><span>备份恢复证据</span><strong class="warn">待验证</strong></div></div></section></section></template>

<style scoped>.checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; padding: 0; background: var(--line); }.checks div { display: flex; justify-content: space-between; padding: 15px; background: #fff; font-size: 13px; }.ok { color: var(--green); }.warn { color: var(--amber); }</style>
