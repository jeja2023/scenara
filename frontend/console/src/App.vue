<script setup lang="ts">
import {
  FileText,
  LogOut,
  Menu,
  RefreshCw,
  ScanFace,
  Settings,
  Sparkles,
  X,
  Zap,
} from "@lucide/vue";
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
const activePlatform = computed(() =>
  ["core", "data", "model", "contracts"].includes(String(route.meta.platform))
    ? String(route.meta.platform)
    : "core",
);
const mobileOpen = ref(false);
const settingsOpen = ref(false);
const settingsDialog = ref<HTMLDialogElement | null>(null);
const connectionState = ref<"checking" | "online" | "offline">("checking");
const draft = reactive<ConnectionSettings>(loadConnection());
const domainManifests = ref<DomainManifest[]>([]);

const domainIcons = {
  behavior: Zap,
  fashion: Sparkles,
  ocr: FileText,
  portrait: ScanFace,
};

type NavigationItem =
  | (typeof routes)[number]
  | {
      path: string;
      name: string;
      meta: {
        title: string;
        description: string;
        icon: typeof ScanFace;
        section: string;
      };
    };

function domainConsoleRoute(manifest: DomainManifest): string {
  const route = manifest.console_route?.trim();
  // The API still exposes the legacy query route for built-in and installed
  // domains. Use the path-param route so /parse's portrait redirect cannot
  // swallow a newly installed domain.
  if (!route || route.startsWith("/parse?domain=")) {
    return `/parse/${encodeURIComponent(manifest.domain_id)}`;
  }
  return route;
}

const navigation = computed(() => {
  const groups = new Map<string, NavigationItem[]>();
  for (const item of routes.filter(
    (entry) =>
      !entry.meta?.hideFromNavigation &&
      typeof entry.meta?.section === "string",
  )) {
    const section = String(item.meta?.section);
    groups.set(section, [...(groups.get(section) ?? []), item]);
  }

  const coreItems = groups.get("核心工作区");
  if (coreItems && domainManifests.value.length) {
    const staticDomainIds = new Set(
      coreItems
        .map((item) => item.path.match(/^\/parse\/([^/:]+)$/u)?.[1])
        .filter((value): value is string => Boolean(value)),
    );
    const installedDomains = [...domainManifests.value]
      .filter((manifest) => !staticDomainIds.has(manifest.domain_id))
      .sort(
        (left, right) =>
          (left.navigation_order ?? 100) - (right.navigation_order ?? 100) ||
          labelDomainDisplayName(
            left.domain_id,
            left.display_name,
          ).localeCompare(
            labelDomainDisplayName(right.domain_id, right.display_name),
          ),
      )
      .map((manifest) => {
        const domainName = labelDomainDisplayName(
          manifest.domain_id,
          manifest.display_name,
        );
        return {
          path: domainConsoleRoute(manifest),
          name: `domain-${manifest.domain_id}`,
          meta: {
            title: domainName.endsWith("解析")
              ? domainName
              : `${domainName}解析`,
            description: labelDomainDescription(
              manifest.domain_id,
              manifest.description,
            ),
            icon:
              domainIcons[manifest.domain_id as keyof typeof domainIcons] ??
              ScanFace,
            section: "核心工作区",
          },
        } satisfies NavigationItem;
      });

    // Keep run history after all installed parsing domains in the workbench.
    const runsIndex = coreItems.findIndex((item) => item.path === "/runs");
    coreItems.splice(
      runsIndex < 0 ? coreItems.length : runsIndex,
      0,
      ...installedDomains,
    );
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
  void nextTick(() => {
    settingsDialog.value?.showModal();
    document.querySelector<HTMLInputElement>("#api-base")?.focus();
  });
}

function applySettings(): void {
  saveConnection(
    { ...draft, apiBase: draft.apiBase.replace(/\/$/, "") },
    { persistAuth: connectionTokenIsPersistent() },
  );
  settingsOpen.value = false;
  settingsDialog.value?.close();
  void checkConnection();
}

function logout(): void {
  signOut();
  mobileOpen.value = false;
  settingsOpen.value = false;
  settingsDialog.value?.close();
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
  <div v-else class="shell" :data-platform="activePlatform">
    <a class="skip-link" href="#main-content">跳到主内容</a>
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
        <h1 class="context-title">{{ pageTitle }}</h1>
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

    <dialog ref="settingsDialog" class="modal" @close="settingsOpen = false">
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
