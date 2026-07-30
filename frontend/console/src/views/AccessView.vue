<script setup lang="ts">
import { BellPlus, RefreshCw, Trash2 } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { api, loadConnection, saveConnection, type ConnectionSettings } from "../api";
import { labelDeliveryStatus, labelEventType } from "../labels";
import type { WebhookDelivery, WebhookSubscription } from "../types";

const form = reactive<ConnectionSettings>(loadConnection());
const subscriptions = ref<WebhookSubscription[]>([]);
const deliveries = ref<WebhookDelivery[]>([]);
const error = ref("");
const loading = ref(false);
const hook = reactive({ name: "", url: "", secret: "", event_types: ["result.available"] as string[] });
const eventOptions = ["result.available", "run.completed", "run.failed", "run.cancelled"];

function apply(): void { saveConnection({ ...form, apiBase: form.apiBase.replace(/\/$/, "") }); window.location.reload(); }

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    [subscriptions.value, deliveries.value] = await Promise.all([
      api<WebhookSubscription[]>("/api/v1/webhooks/subscriptions"),
      api<WebhookDelivery[]>("/api/v1/webhooks/deliveries?limit=50"),
    ]);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught);
  } finally {
    loading.value = false;
  }
}

async function createHook(): Promise<void> {
  await api<WebhookSubscription>("/api/v1/webhooks/subscriptions", {
    method: "POST",
    body: JSON.stringify(hook),
  });
  hook.name = "";
  hook.url = "";
  hook.secret = "";
  hook.event_types = ["result.available"];
  await refresh();
}

async function removeHook(endpointId: string): Promise<void> {
  await api<void>(`/api/v1/webhooks/subscriptions/${encodeURIComponent(endpointId)}`, { method: "DELETE" });
  await refresh();
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header"><div><h1>接入</h1><p>项目连接与事件通知。</p></div><button class="button secondary" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新</button></div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="two-column">
      <section class="panel"><div class="panel-header"><h2>浏览器连接</h2></div><div class="panel-body"><div class="form-grid"><label class="span-2"><span>接口地址</span><input v-model="form.apiBase" placeholder="同源" /></label><label><span>租户</span><input v-model="form.tenantId" /></label><label><span>项目</span><input v-model="form.projectId" /></label><label class="span-2"><span>访问令牌</span><input v-model="form.token" type="password" autocomplete="off" /></label></div><button class="button primary apply" @click="apply">应用</button></div></section>
      <section class="panel"><div class="panel-header"><h2>事件回调订阅</h2></div><div class="panel-body"><div class="form-grid"><label><span>名称</span><input v-model="hook.name" /></label><label><span>HTTPS 地址</span><input v-model="hook.url" type="url" /></label><label class="span-2"><span>签名密钥</span><input v-model="hook.secret" type="password" autocomplete="new-password" /></label></div><div class="event-options"><label v-for="event in eventOptions" :key="event"><input v-model="hook.event_types" type="checkbox" :value="event" />{{ labelEventType(event) }}</label></div><button class="button primary" :disabled="!hook.name || !hook.url || hook.secret.length < 16 || !hook.event_types.length" @click="createHook"><BellPlus :size="16" />添加</button></div></section>
    </div>
    <section class="panel access-panel"><div class="panel-header"><h2>订阅</h2><span class="badge">{{ subscriptions.length }}</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>名称</th><th>地址</th><th>事件</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="item in subscriptions" :key="item.endpoint_id"><td><strong>{{ item.name }}</strong><div class="mono muted">{{ item.endpoint_id }}</div></td><td class="truncate">{{ item.url }}</td><td>{{ item.event_types.map(labelEventType).join(" · ") }}</td><td><span class="badge" :class="item.enabled ? 'active' : ''">{{ item.enabled ? "启用" : "停用" }}</span></td><td><button class="icon-button danger-icon" title="删除订阅" :aria-label="`删除 ${item.name}`" @click="removeHook(item.endpoint_id)"><Trash2 :size="15" /></button></td></tr></tbody></table><div v-if="!subscriptions.length" class="empty">没有事件回调订阅</div></div></section>
    <section class="panel access-panel"><div class="panel-header"><h2>最近投递</h2><span class="badge">{{ deliveries.length }}</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>事件</th><th>订阅</th><th>状态</th><th>尝试</th><th>HTTP</th><th>更新时间</th></tr></thead><tbody><tr v-for="item in deliveries" :key="item.delivery_id"><td><strong>{{ labelEventType(item.event_type) }}</strong><div class="mono muted">{{ item.event_id }}</div></td><td class="mono">{{ item.endpoint_id }}</td><td><span class="badge" :class="item.status === 'delivered' ? 'completed' : item.status === 'dead_letter' ? 'failed' : 'queued'">{{ labelDeliveryStatus(item.status) }}</span></td><td>{{ item.attempts }}</td><td>{{ item.status_code ?? "—" }}</td><td>{{ new Date(item.updated_at * 1000).toLocaleString() }}</td></tr></tbody></table><div v-if="!deliveries.length" class="empty">没有投递记录</div></div></section>
  </section>
</template>

<style scoped>.apply { margin-top: 16px; }.access-panel { margin-top: 16px; }.event-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px 12px; margin: 14px 0; }.event-options label { display: flex; align-items: center; gap: 7px; font-family: "SFMono-Regular", Consolas, monospace; font-size: 11px; }.event-options input { width: 15px; min-height: 15px; }.danger-icon { color: var(--coral); }@media (max-width: 560px) { .event-options { grid-template-columns: 1fr; } }</style>
