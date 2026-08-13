<script setup lang="ts">
import { LogOut, Menu, RefreshCw, Settings, X } from "@lucide/vue";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";

import { isSignedIn, signOut } from "./auth";
import {
  api,
  connectionTokenIsPersistent,
  loadConnection,
  saveConnection,
  type ConnectionSettings,
} from "./api";
import brandMark from "./assets/scenara-mark.svg";
import {
  labelDomain,
  labelDomainDescription,
  labelDomainDisplayName,
} from "./labels";
import { routes } from "./router";
import type { DomainManifest } from "./types";

const route = useRoute();
const router = useRouter();
const isAuthRoute = computed(() => route.meta.layout === "auth");
const mobileOpen = ref(false);
const settingsOpen = ref(false);
const connectionState = ref<"checking" | "online" | "offline">("checking");
const draft = reactive<ConnectionSettings>(loadConnection());
const domainManifests = ref<DomainManifest[]>([]);
const navigation = computed(() => {
  const groups = new Map<string, typeof routes>();
  for (const item of routes.filter(
    (entry) =>
      !entry.meta?.hideFromNavigation &&
      typeof entry.meta?.section === "string",
  )) {
    const section = String(item.meta?.section);
    groups.set(section, [...(groups.get(section) ?? []), item]);
  }
  return groups;
});

async function loadDomainNavigation(): Promise<void> {
  try {
    domainManifests.value = await api<DomainManifest[]>("/api/v1/domains");
  } catch {
    domainManifests.value = [];
  }
}

async function checkConnection(): Promise<void> {
  connectionState.value = "checking";
  try {
    await api<{ status: string }>("/healthz");
    connectionState.value = "online";
  } catch {
    connectionState.value = "offline";
  }
}

function openSettings(): void {
  Object.assign(draft, loadConnection());
  settingsOpen.value = true;
  void nextTick(() =>
    document.querySelector<HTMLInputElement>("#api-base")?.focus(),
  );
}

function applySettings(): void {
  saveConnection(
    { ...draft, apiBase: draft.apiBase.replace(/\/$/, "") },
    { persistAuth: connectionTokenIsPersistent() },
  );
  settingsOpen.value = false;
  void checkConnection();
}

function logout(): void {
  signOut();
  mobileOpen.value = false;
  settingsOpen.value = false;
  void router.replace({ name: "login" });
}

function handleAuthExpired(): void {
  signOut();
  if (route.name !== "login") void router.replace({ name: "login" });
}

function checkAuthStatus(): void {
  if (!isAuthRoute.value && !isSignedIn()) {
    handleAuthExpired();
  }
}

let authTimer: number | null = null;

onMounted(() => {
  window.addEventListener("scenara:auth-expired", handleAuthExpired);
  window.addEventListener("focus", checkAuthStatus);
  authTimer = window.setInterval(checkAuthStatus, 10000);
});
onBeforeUnmount(() => {
  window.removeEventListener("scenara:auth-expired", handleAuthExpired);
  window.removeEventListener("focus", checkAuthStatus);
  if (authTimer !== null) window.clearInterval(authTimer);
});

watch(
  isAuthRoute,
  (authRoute) => {
    if (!authRoute) {
      void checkConnection();
      void loadDomainNavigation();
    }
  },
  { immediate: true },
);
const isRefreshing = ref(false);

function triggerRefresh(): void {
  if (isRefreshing.value) return;
  isRefreshing.value = true;
  window.dispatchEvent(new CustomEvent("scenara:refresh"));
  setTimeout(() => {
    isRefreshing.value = false;
  }, 600);
}

const pageTitle = computed(() => {
  const currentDomain = (route.params.domain ||
    route.query.domain ||
    (route.name === "portrait-parse"
      ? "portrait"
      : route.name === "ocr-parse"
        ? "ocr"
        : "")) as string;

  if (route.path.startsWith("/parse") && currentDomain) {
    if (currentDomain === "portrait") return "人像解析";
    if (currentDomain === "ocr") return "OCR 文档解析";
    const manifest = domainManifests.value.find(
      (d) => d.domain_id === currentDomain,
    );
    const domainName = manifest
      ? labelDomainDisplayName(manifest.domain_id, manifest.display_name)
      : labelDomain(currentDomain);
    return domainName.endsWith("解析") ? domainName : `${domainName}解析`;
  }

  return (route.meta?.title as string) ?? "";
});

const pageDescription = computed(() => {
  const currentDomain = (route.params.domain ||
    route.query.domain ||
    (route.name === "portrait-parse"
      ? "portrait"
      : route.name === "ocr-parse"
        ? "ocr"
        : "")) as string;

  if (route.path.startsWith("/parse") && currentDomain) {
    if (currentDomain === "portrait")
      return "检测人员并分析人像相关的视觉特征。";
    if (currentDomain === "ocr")
      return "识别并分析文档中的文字、结构和关键信息。";
    const manifest = domainManifests.value.find(
      (d) => d.domain_id === currentDomain,
    );
    if (manifest) {
      return labelDomainDescription(manifest.domain_id, manifest.description);
    }
  }

  return (route.meta?.description as string) ?? "";
});
</script>

<template>
  <RouterView v-if="isAuthRoute" />
  <div v-else class="shell">
    <header class="topbar">
      <button
        class="icon-button mobile-menu"
        title="打开导航"
        @click="mobileOpen = true"
      >
        <Menu :size="19" />
      </button>
      <div class="mobile-brand">
        <img :src="brandMark" alt="" /><strong>Scenara</strong>
      </div>
      <div class="topbar-context">
        <span class="context-product">视觉 AI 中枢平台</span>
        <span class="context-separator"></span>
        <strong class="context-title">{{ pageTitle }}</strong>
        <span
          v-if="pageDescription"
          class="context-description"
          :title="pageDescription"
        >
          {{ pageDescription }}
        </span>
      </div>
      <div class="topbar-actions">
        <button
          class="icon-button"
          title="刷新"
          :disabled="isRefreshing"
          @click="triggerRefresh"
        >
          <RefreshCw :size="18" :class="{ spin: isRefreshing }" />
        </button>
        <button
          class="connection"
          :class="connectionState"
          @click="checkConnection"
        >
          <span></span
          >{{
            connectionState === "online"
              ? "已连接"
              : connectionState === "offline"
                ? "未连接"
                : "检查中"
          }}
        </button>
        <button class="icon-button" title="连接设置" @click="openSettings">
          <Settings :size="18" />
        </button>
        <button class="icon-button" title="退出登录" @click="logout">
          <LogOut :size="18" />
        </button>
      </div>
    </header>

    <aside class="sidebar" :class="{ open: mobileOpen }">
      <div class="brand">
        <img :src="brandMark" alt="" />
        <div><strong>Scenara</strong><span>景枢</span></div>
        <button
          class="icon-button sidebar-close"
          title="关闭导航"
          @click="mobileOpen = false"
        >
          <X :size="19" />
        </button>
      </div>
      <nav aria-label="主导航">
        <section v-for="[section, items] in navigation" :key="section">
          <p>{{ section }}</p>
          <RouterLink
            v-for="item in items"
            :key="item.path"
            :to="item.path"
            @click="mobileOpen = false"
          >
            <component :is="item.meta?.icon" :size="17" />
            <span>{{ item.meta?.title }}</span>
          </RouterLink>
        </section>
      </nav>
      <div class="sidebar-footer">
        <span>0.3 开发版</span><i></i><span>接口版本 1</span>
      </div>
    </aside>
    <button
      v-if="mobileOpen"
      class="nav-scrim"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    ></button>

    <main id="main-content" class="main-content" tabindex="-1">
      <RouterView />
    </main>

    <dialog :open="settingsOpen" class="modal" @close="settingsOpen = false">
      <form method="dialog" @submit.prevent="applySettings">
        <div class="modal-header">
          <div>
            <h2>连接设置</h2>
            <p>当前浏览器会话</p>
          </div>
          <button
            class="icon-button"
            title="关闭"
            @click="settingsOpen = false"
          >
            <X :size="18" />
          </button>
        </div>
        <div class="form-grid">
          <label class="span-2"
            ><span>接口地址</span
            ><input id="api-base" v-model="draft.apiBase" placeholder="同源"
          /></label>
          <label
            ><span>租户</span><input v-model="draft.tenantId" required
          /></label>
          <label
            ><span>项目</span><input v-model="draft.projectId" required
          /></label>
          <label class="span-2"
            ><span>访问令牌</span
            ><input v-model="draft.token" type="password" autocomplete="off"
          /></label>
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button secondary"
            @click="checkConnection"
          >
            <RefreshCw :size="16" />测试</button
          ><button class="button primary" type="submit">应用</button>
        </div>
      </form>
    </dialog>
  </div>
</template>
