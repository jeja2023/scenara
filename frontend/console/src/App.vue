<script setup lang="ts">
import { Menu, RefreshCw, Settings, X } from "@lucide/vue";
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";

import { api, loadConnection, saveConnection, type ConnectionSettings } from "./api";
import brandMark from "./assets/scenara-mark.svg";
import { routes } from "./router";

const route = useRoute();
const mobileOpen = ref(false);
const settingsOpen = ref(false);
const connectionState = ref<"checking" | "online" | "offline">("checking");
const draft = reactive<ConnectionSettings>(loadConnection());
const navigation = computed(() => {
  const groups = new Map<string, typeof routes>();
  for (const item of routes.filter((entry) => typeof entry.meta?.section === "string")) {
    const section = String(item.meta?.section);
    groups.set(section, [...(groups.get(section) ?? []), item]);
  }
  return groups;
});

async function checkConnection(): Promise<void> {
  connectionState.value = "checking";
  try { await api<{ status: string }>("/healthz"); connectionState.value = "online"; }
  catch { connectionState.value = "offline"; }
}

function openSettings(): void {
  Object.assign(draft, loadConnection());
  settingsOpen.value = true;
  void nextTick(() => document.querySelector<HTMLInputElement>("#api-base")?.focus());
}

function applySettings(): void {
  saveConnection({ ...draft, apiBase: draft.apiBase.replace(/\/$/, "") });
  settingsOpen.value = false;
  void checkConnection();
}

onMounted(checkConnection);
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <button class="icon-button mobile-menu" title="打开导航" @click="mobileOpen = true"><Menu :size="19" /></button>
      <div class="mobile-brand"><img :src="brandMark" alt="" /><strong>Scenara</strong></div>
      <div class="topbar-context">
        <span class="context-product">统一视觉解析平台</span>
        <span class="context-separator"></span>
        <strong>{{ route.meta.title }}</strong>
      </div>
      <div class="topbar-actions">
        <button class="connection" :class="connectionState" @click="checkConnection">
          <span></span>{{ connectionState === "online" ? "已连接" : connectionState === "offline" ? "未连接" : "检查中" }}
        </button>
        <button class="icon-button" title="连接设置" @click="openSettings"><Settings :size="18" /></button>
      </div>
    </header>

    <aside class="sidebar" :class="{ open: mobileOpen }">
      <div class="brand">
        <img :src="brandMark" alt="" />
        <div><strong>Scenara</strong><span>景析</span></div>
        <button class="icon-button sidebar-close" title="关闭导航" @click="mobileOpen = false"><X :size="19" /></button>
      </div>
      <nav aria-label="主导航">
        <section v-for="[section, items] in navigation" :key="section">
          <p>{{ section }}</p>
          <RouterLink v-for="item in items" :key="item.path" :to="item.path" @click="mobileOpen = false">
            <component :is="item.meta?.icon" :size="17" />
            <span>{{ item.meta?.title }}</span>
          </RouterLink>
        </section>
      </nav>
      <div class="sidebar-footer"><span>0.1 development</span><i></i><span>API v1</span></div>
    </aside>
    <button v-if="mobileOpen" class="nav-scrim" aria-label="关闭导航" @click="mobileOpen = false"></button>

    <main id="main-content" class="main-content" tabindex="-1"><RouterView /></main>

    <dialog :open="settingsOpen" class="modal" @close="settingsOpen = false">
      <form method="dialog" @submit.prevent="applySettings">
        <div class="modal-header"><div><h2>连接设置</h2><p>当前浏览器会话</p></div><button class="icon-button" title="关闭" @click="settingsOpen = false"><X :size="18" /></button></div>
        <div class="form-grid">
          <label class="span-2"><span>API 地址</span><input id="api-base" v-model="draft.apiBase" placeholder="同源" /></label>
          <label><span>租户</span><input v-model="draft.tenantId" required /></label>
          <label><span>项目</span><input v-model="draft.projectId" required /></label>
          <label class="span-2"><span>Bearer Token</span><input v-model="draft.token" type="password" autocomplete="off" /></label>
        </div>
        <div class="modal-actions"><button type="button" class="button secondary" @click="checkConnection"><RefreshCw :size="16" />测试</button><button class="button primary" type="submit">应用</button></div>
      </form>
    </dialog>
  </div>
</template>
