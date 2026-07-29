<script setup lang="ts">
import { reactive } from "vue";
import { loadConnection, saveConnection, type ConnectionSettings } from "../api";
const form = reactive<ConnectionSettings>(loadConnection());
function apply(): void { saveConnection({ ...form, apiBase: form.apiBase.replace(/\/$/, "") }); window.location.reload(); }
</script>

<template><section class="page"><div class="page-header"><div><h1>接入</h1><p>API、SDK 与项目上下文。</p></div></div><div class="two-column"><section class="panel"><div class="panel-header"><h2>浏览器连接</h2></div><div class="panel-body"><div class="form-grid"><label class="span-2"><span>API 地址</span><input v-model="form.apiBase" placeholder="同源" /></label><label><span>租户</span><input v-model="form.tenantId" /></label><label><span>项目</span><input v-model="form.projectId" /></label><label class="span-2"><span>Bearer Token</span><input v-model="form.token" type="password" autocomplete="off" /></label></div><button class="button primary apply" @click="apply">应用</button></div></section><section class="panel"><div class="panel-header"><h2>公共接口</h2></div><div class="panel-body endpoints"><code>POST /api/v1/media/assets</code><code>POST /api/v1/runs</code><code>GET /api/v1/runs/{id}/events</code><code>GET /api/v1/runs/{id}/result</code><code>POST /api/v1/parse/image</code></div></section></div></section></template>

<style scoped>.apply { margin-top: 16px; }.endpoints { display: grid; gap: 10px; }.endpoints code { padding: 10px; background: #f2f4f3; border: 1px solid var(--line); border-radius: 4px; }</style>
