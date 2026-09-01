<script setup lang="ts">
import ConnectionTab from "./access/ConnectionTab.vue";
import CredentialsTab from "./access/CredentialsTab.vue";
import CredentialsDialogs from "./access/CredentialsDialogs.vue";
import FoundationTab from "./access/FoundationTab.vue";
import EventsTab from "./access/EventsTab.vue";
import EventsDialog from "./access/EventsDialog.vue";
import ProductsTab from "./access/ProductsTab.vue";
import ProductsDialog from "./access/ProductsDialog.vue";
import IdentityTab from "./access/IdentityTab.vue";
import IdentityDialogs from "./access/IdentityDialogs.vue";
import IssuedKeyDialog from "./access/IssuedKeyDialog.vue";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRefresh } from "../composables/useRefresh";
import {
  api,
  loadConnection,
  saveConnection,
  userFacingError,
  type ConnectionSettings,
} from "../api";
import { labelProduct, labelProductSummary } from "../labels";
import type {
  AccessCapabilityStatus,
  AccessFoundationStatus,
  ApiKeyRecord,
  IamSummary,
  Membership,
  Organization,
  ProductCatalogItem,
  ProductEntitlement,
  Project,
  Role,
  ServiceAccount,
  UserAccount,
  WebhookDelivery,
  WebhookSubscription,
} from "../types";
import type {
  AccessTab,
  ApiKeyForm,
  DisplayProduct,
  EntitlementForm,
  IdentitySubTab,
  IssuedApiKey,
  MembershipForm,
  OrganizationForm,
  PrincipalCandidate,
  ProjectForm,
  RoleForm,
  ServiceAccountForm,
  UserForm,
  WebhookForm,
} from "./access/types";
import {
  defaultProductsList,
  eventOptions,
  scopePresets,
  tabs,
} from "./access/config";

const activeTab = ref<AccessTab>("foundation");
const form = reactive<ConnectionSettings>(loadConnection());
const foundation = ref<AccessFoundationStatus | null>(null);
const iam = ref<IamSummary | null>(null);
const organizations = ref<Organization[]>([]);
const projects = ref<Project[]>([]);
const users = ref<UserAccount[]>([]);
const roles = ref<Role[]>([]);
const memberships = ref<Membership[]>([]);
const serviceAccounts = ref<ServiceAccount[]>([]);
const apiKeys = ref<ApiKeyRecord[]>([]);
const entitlements = ref<ProductEntitlement[]>([]);
const subscriptions = ref<WebhookSubscription[]>([]);
const deliveries = ref<WebhookDelivery[]>([]);
const products = ref<ProductCatalogItem[]>([]);
const error = ref("");
const loading = ref(false);
const mutating = ref(false);
const issuedKey = ref<IssuedApiKey | null>(null);
const copied = ref(false);

const availableProducts = computed<DisplayProduct[]>(() => {
  if (!products.value.length) return defaultProductsList;
  return products.value
    .filter(
      (p) =>
        p.maturity !== "gated" &&
        p.product_id !== "agent" &&
        p.product_id !== "edge",
    )
    .map((p) => {
      const fallback = defaultProductsList.find((df) => df.id === p.product_id);
      return {
        id: p.product_id,
        name: labelProduct(p.product_id),
        domain: fallback?.domain ?? p.layer,
        summary: p.summary || labelProductSummary(p.product_id),
        layer: p.layer,
        maturity: p.maturity,
        scopes: p.current_scope?.length
          ? p.current_scope
          : (fallback?.scopes ?? []),
      };
    });
});

const productList = computed(() => availableProducts.value);
const selectedEntitlementProduct = computed(() =>
  availableProducts.value.find((p) => p.id === entitlementForm.product_id),
);

function labelScopeTag(scope: string): string {
  const map: Record<string, string> = {
    "OCR document parsing": "OCR 文档解析与识别",
    "OpenAPI 契约": "OpenAPI 标准契约",
    "v1 接口": "v1 接口路由",
    Webhook: "Webhook 事件推送",
    系统探针: "系统运行探针",
    "Python SDK": "Python SDK 客户端",
    "TypeScript SDK": "TypeScript SDK 客户端",
    "OpenAPI 生成的模式类型": "OpenAPI 类型定义契约",
    "Qdrant FeatureStore provider adapter with tenant/project filters":
      "Qdrant 向量特征库适配",
    "Cosplay 识别与服饰风格分析": "服饰风格与二次元识别",
  };
  return map[scope] || scope;
}

const identitySubTab = ref<IdentitySubTab>("organizations");

type CredentialSubTab = "service_accounts" | "api_keys";
const credentialSubTab = ref<CredentialSubTab>("service_accounts");

type EventSubTab = "subscriptions" | "deliveries";
const eventSubTab = ref<EventSubTab>("subscriptions");

const orgSearch = ref("");
const projectSearch = ref("");
const userSearch = ref("");
const userStatusFilter = ref<"all" | "active" | "disabled">("all");
const memberSearch = ref("");
const roleSearch = ref("");

const serviceAccountSearch = ref("");
const apiKeySearch = ref("");
const entitlementSearch = ref("");
const subscriptionSearch = ref("");
const deliveryStatusFilter = ref<
  "all" | "delivered" | "dead_letter" | "queued"
>("all");

// 10 组独立表格客户端分页配置（默认每页 10 条）
const orgsPagination = reactive({ offset: 0, pageSize: 10 });
const projectsPagination = reactive({ offset: 0, pageSize: 10 });
const usersPagination = reactive({ offset: 0, pageSize: 10 });
const membershipsPagination = reactive({ offset: 0, pageSize: 10 });
const rolesPagination = reactive({ offset: 0, pageSize: 10 });
const serviceAccountsPagination = reactive({ offset: 0, pageSize: 10 });
const apiKeysPagination = reactive({ offset: 0, pageSize: 10 });
const entitlementsPagination = reactive({ offset: 0, pageSize: 10 });
const subscriptionsPagination = reactive({ offset: 0, pageSize: 10 });
const deliveriesPagination = reactive({ offset: 0, pageSize: 10 });

const showCreateOrg = ref(false);
const showCreateProject = ref(false);
const showCreateUser = ref(false);
const showCreateRole = ref(false);
const showCreateMembership = ref(false);
const showCreateServiceAccount = ref(false);
const showCreateApiKey = ref(false);
const showCreateEntitlement = ref(false);
const showCreateHook = ref(false);
const showHookSecret = ref(false);
const showConnectionToken = ref(false);

const organizationForm = reactive<OrganizationForm>({ display_name: "" });
const projectForm = reactive<ProjectForm>({ project_id: "", display_name: "" });
const userForm = reactive<UserForm>({
  user_id: "",
  display_name: "",
  phone: "",
  email: "",
  password: "",
});
const roleForm = reactive<RoleForm>({
  role_id: "",
  display_name: "",
  scopes: "iam:read",
  product_ids: [] as string[],
});
const membershipForm = reactive<MembershipForm>({
  principal_id: "",
  principal_type: "user" as "user" | "service_account",
  role_ids: [] as string[],
});
const serviceAccountForm = reactive<ServiceAccountForm>({
  service_account_id: "",
  display_name: "",
  scopes: "iam:read",
  product_ids: [] as string[],
});
const keyForm = reactive<ApiKeyForm>({
  service_account_id: "",
  name: "",
  scopes: "",
  product_ids: [] as string[],
  expires_at: "",
});
const entitlementForm = reactive<EntitlementForm>({
  product_id: "parse",
  status: "active" as "active" | "suspended",
});
const hook = reactive<WebhookForm>({
  name: "",
  url: "",
  secret: "",
  event_types: ["result.available"] as string[],
});

// 组织与项目过滤
const filteredOrganizations = computed(() => {
  const q = orgSearch.value.trim().toLowerCase();
  if (!q) return organizations.value;
  return organizations.value.filter((o) => {
    return (
      o.display_name.toLowerCase().includes(q) ||
      o.tenant_id.toLowerCase().includes(q)
    );
  });
});

const filteredProjects = computed(() => {
  const q = projectSearch.value.trim().toLowerCase();
  if (!q) return projects.value;
  return projects.value.filter((p) => {
    return (
      p.display_name.toLowerCase().includes(q) ||
      p.project_id.toLowerCase().includes(q) ||
      p.tenant_id.toLowerCase().includes(q)
    );
  });
});

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase();
  return users.value.filter((u) => {
    const contact = (u.phone || u.email || "").toLowerCase();
    const matchesSearch =
      !q ||
      u.display_name.toLowerCase().includes(q) ||
      u.user_id.toLowerCase().includes(q) ||
      contact.includes(q);
    const matchesStatus =
      userStatusFilter.value === "all" ||
      (userStatusFilter.value === "active" && !u.disabled) ||
      (userStatusFilter.value === "disabled" && u.disabled);
    return matchesSearch && matchesStatus;
  });
});

const userRolesMap = computed(() => {
  const map = new Map<string, Role[]>();
  for (const m of memberships.value) {
    if (m.principal_type === "user") {
      const assigned = roles.value.filter((r) =>
        m.role_ids.includes(r.role_id),
      );
      map.set(m.principal_id, assigned);
    }
  }
  return map;
});

const filteredMemberships = computed(() => {
  const q = memberSearch.value.trim().toLowerCase();
  if (!q) return memberships.value;
  return memberships.value.filter((m) => {
    return (
      m.principal_id.toLowerCase().includes(q) ||
      m.role_ids.some((r) => r.toLowerCase().includes(q))
    );
  });
});

const filteredRoles = computed(() => {
  const q = roleSearch.value.trim().toLowerCase();
  if (!q) return roles.value;
  return roles.value.filter((r) => {
    return (
      r.display_name.toLowerCase().includes(q) ||
      r.role_id.toLowerCase().includes(q) ||
      r.scopes.some((s) => s.toLowerCase().includes(q))
    );
  });
});

const filteredServiceAccounts = computed(() => {
  const q = serviceAccountSearch.value.trim().toLowerCase();
  if (!q) return serviceAccounts.value;
  return serviceAccounts.value.filter((sa) => {
    return (
      sa.display_name.toLowerCase().includes(q) ||
      sa.service_account_id.toLowerCase().includes(q) ||
      sa.scopes.some((s) => s.toLowerCase().includes(q))
    );
  });
});

const filteredApiKeys = computed(() => {
  const q = apiKeySearch.value.trim().toLowerCase();
  if (!q) return apiKeys.value;
  return apiKeys.value.filter((k) => {
    return (
      k.name.toLowerCase().includes(q) ||
      k.service_account_id.toLowerCase().includes(q) ||
      k.key_id.toLowerCase().includes(q) ||
      k.token_prefix.toLowerCase().includes(q)
    );
  });
});

const filteredEntitlements = computed(() => {
  const q = entitlementSearch.value.trim().toLowerCase();
  if (!q) return entitlements.value;
  return entitlements.value.filter((e) => {
    return (
      labelProduct(e.product_id).toLowerCase().includes(q) ||
      e.product_id.toLowerCase().includes(q) ||
      e.project_id.toLowerCase().includes(q)
    );
  });
});

const filteredSubscriptions = computed(() => {
  const q = subscriptionSearch.value.trim().toLowerCase();
  if (!q) return subscriptions.value;
  return subscriptions.value.filter((s) => {
    return (
      s.name.toLowerCase().includes(q) ||
      s.endpoint_id.toLowerCase().includes(q) ||
      s.url.toLowerCase().includes(q)
    );
  });
});

const filteredDeliveries = computed(() => {
  const list = deliveries.value;
  if (deliveryStatusFilter.value === "all") return list;
  return list.filter((d) => d.status === deliveryStatusFilter.value);
});

// 搜索或筛选变化时自动重置第一页
watch(orgSearch, () => {
  orgsPagination.offset = 0;
});
watch(projectSearch, () => {
  projectsPagination.offset = 0;
});
watch([userSearch, userStatusFilter], () => {
  usersPagination.offset = 0;
});
watch(memberSearch, () => {
  membershipsPagination.offset = 0;
});
watch(roleSearch, () => {
  rolesPagination.offset = 0;
});
watch(serviceAccountSearch, () => {
  serviceAccountsPagination.offset = 0;
});
watch(apiKeySearch, () => {
  apiKeysPagination.offset = 0;
});
watch(entitlementSearch, () => {
  entitlementsPagination.offset = 0;
});
watch(subscriptionSearch, () => {
  subscriptionsPagination.offset = 0;
});
watch(deliveryStatusFilter, () => {
  deliveriesPagination.offset = 0;
});

// 10 组列表的分页切片计算属性
const paginatedOrganizations = computed(() =>
  filteredOrganizations.value.slice(
    orgsPagination.offset,
    orgsPagination.offset + orgsPagination.pageSize,
  ),
);
const paginatedProjects = computed(() =>
  filteredProjects.value.slice(
    projectsPagination.offset,
    projectsPagination.offset + projectsPagination.pageSize,
  ),
);
const paginatedUsers = computed(() =>
  filteredUsers.value.slice(
    usersPagination.offset,
    usersPagination.offset + usersPagination.pageSize,
  ),
);
const paginatedMemberships = computed(() =>
  filteredMemberships.value.slice(
    membershipsPagination.offset,
    membershipsPagination.offset + membershipsPagination.pageSize,
  ),
);
const paginatedRoles = computed(() =>
  filteredRoles.value.slice(
    rolesPagination.offset,
    rolesPagination.offset + rolesPagination.pageSize,
  ),
);
const paginatedServiceAccounts = computed(() =>
  filteredServiceAccounts.value.slice(
    serviceAccountsPagination.offset,
    serviceAccountsPagination.offset + serviceAccountsPagination.pageSize,
  ),
);
const paginatedApiKeys = computed(() =>
  filteredApiKeys.value.slice(
    apiKeysPagination.offset,
    apiKeysPagination.offset + apiKeysPagination.pageSize,
  ),
);
const paginatedEntitlements = computed(() =>
  filteredEntitlements.value.slice(
    entitlementsPagination.offset,
    entitlementsPagination.offset + entitlementsPagination.pageSize,
  ),
);
const paginatedSubscriptions = computed(() =>
  filteredSubscriptions.value.slice(
    subscriptionsPagination.offset,
    subscriptionsPagination.offset + subscriptionsPagination.pageSize,
  ),
);
const paginatedDeliveries = computed(() =>
  filteredDeliveries.value.slice(
    deliveriesPagination.offset,
    deliveriesPagination.offset + deliveriesPagination.pageSize,
  ),
);

const principalCandidateOptions = computed<PrincipalCandidate[]>(() => {
  if (membershipForm.principal_type === "user") {
    return users.value.map((u) => ({
      id: u.user_id,
      name: u.display_name,
      detail: u.email || "无邮箱",
    }));
  } else {
    return serviceAccounts.value.map((sa) => ({
      id: sa.service_account_id,
      name: sa.display_name,
      detail: sa.scopes.join(", "),
    }));
  }
});

function getRoleMemberCount(roleId: string): number {
  return memberships.value.filter((m) => m.role_ids.includes(roleId)).length;
}

function getPrincipalDisplayName(
  principalId: string,
  principalType: "user" | "service_account",
): string {
  if (principalType === "user") {
    const user = users.value.find((u) => u.user_id === principalId);
    return user ? user.display_name : principalId;
  } else {
    const sa = serviceAccounts.value.find(
      (s) => s.service_account_id === principalId,
    );
    return sa ? sa.display_name : principalId;
  }
}

const activeUsersCount = computed(
  () => users.value.filter((u) => !u.disabled).length,
);
const disabledUsersCount = computed(
  () => users.value.filter((u) => u.disabled).length,
);

const copiedKey = ref<string | null>(null);
async function copyToClipboard(text: string, key: string) {
  try {
    await navigator.clipboard.writeText(text);
    copiedKey.value = key;
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = null;
    }, 1500);
  } catch {
    // clipboard fallback
  }
}

function openAssignRole(userId: string) {
  membershipForm.principal_type = "user";
  membershipForm.principal_id = userId;
  membershipForm.role_ids = (userRolesMap.value.get(userId) || []).map(
    (r) => r.role_id,
  );
  identitySubTab.value = "memberships";
  showCreateMembership.value = true;
}

function openMembershipDialog(
  principalType: "user" | "service_account" = "user",
  principalId = "",
  roleIds: string[] = [],
): void {
  membershipForm.principal_type = principalType;
  membershipForm.principal_id = principalId;
  membershipForm.role_ids = roleIds.slice();
  showCreateMembership.value = true;
}

const readiness = computed(() => {
  const capabilities = foundation.value?.capabilities ?? [];
  return {
    available: capabilities.filter((item) => item.status === "available")
      .length,
    planned: capabilities.filter((item) => item.status === "planned").length,
    gated: capabilities.filter((item) => item.status === "gated").length,
  };
});

const statusLabels: Record<AccessCapabilityStatus, string> = {
  available: "可用",
  seed: "种子能力",
  planned: "规划中",
  gated: "门禁中",
};
const authModeLabels: Record<AccessFoundationStatus["auth_mode"], string> = {
  development_open: "开发开放",
  single_bearer_token: "令牌认证",
};
const principalSourceLabels: Record<
  AccessFoundationStatus["principal_source"],
  string
> = {
  anonymous: "匿名身份",
  api_token: "平台根令牌",
  service_account_api_key: "服务账号 API 密钥",
  header: "请求头身份",
};

function parseList(value: string): string[] {
  return [
    ...new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ];
}

function formatTime(value?: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : "从未";
}

function labelContext(value: string, kind: "租户" | "项目"): string {
  return value === "default" ? `默认${kind}` : value;
}

function applyConnection(): void {
  saveConnection({ ...form, apiBase: form.apiBase.replace(/\/$/, "") });
  window.location.reload();
}

function resetConnection(): void {
  form.apiBase = "";
  form.tenantId = "default";
  form.projectId = "default";
  form.token = "";
  applyConnection();
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const results = await Promise.all([
      api<AccessFoundationStatus>("/api/v1/platform/access-foundation"),
      api<IamSummary>("/api/v1/platform/iam/summary"),
      api<Organization[]>("/api/v1/platform/organizations"),
      api<Project[]>("/api/v1/platform/projects"),
      api<UserAccount[]>("/api/v1/platform/users"),
      api<Role[]>("/api/v1/platform/roles"),
      api<Membership[]>("/api/v1/platform/memberships"),
      api<ServiceAccount[]>("/api/v1/platform/service-accounts"),
      api<ApiKeyRecord[]>("/api/v1/platform/api-keys"),
      api<ProductEntitlement[]>("/api/v1/platform/product-entitlements"),
      api<WebhookSubscription[]>("/api/v1/webhooks/subscriptions"),
      api<WebhookDelivery[]>("/api/v1/webhooks/deliveries?limit=50"),
      api<ProductCatalogItem[]>("/api/v1/platform/products"),
    ]);
    [
      foundation.value,
      iam.value,
      organizations.value,
      projects.value,
      users.value,
      roles.value,
      memberships.value,
      serviceAccounts.value,
      apiKeys.value,
      entitlements.value,
      subscriptions.value,
      deliveries.value,
      products.value,
    ] = results;
    const firstServiceAccount = serviceAccounts.value[0];
    if (!keyForm.service_account_id && firstServiceAccount) {
      keyForm.service_account_id = firstServiceAccount.service_account_id;
    }
  } catch (caught) {
    error.value = userFacingError(caught, "接入数据加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function mutate(action: () => Promise<void>): Promise<void> {
  mutating.value = true;
  error.value = "";
  try {
    await action();
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    mutating.value = false;
  }
}

async function createOrganization(): Promise<void> {
  await mutate(async () => {
    await api<Organization>("/api/v1/platform/organizations", {
      method: "POST",
      body: JSON.stringify(organizationForm),
    });
    organizationForm.display_name = "";
    showCreateOrg.value = false;
  });
}

async function createProject(): Promise<void> {
  await mutate(async () => {
    await api<Project>("/api/v1/platform/projects", {
      method: "POST",
      body: JSON.stringify(projectForm),
    });
    Object.assign(projectForm, { project_id: "", display_name: "" });
    showCreateProject.value = false;
  });
}

async function createUser(): Promise<void> {
  await mutate(async () => {
    await api<UserAccount>("/api/v1/platform/users", {
      method: "POST",
      body: JSON.stringify({
        ...userForm,
        user_id: userForm.user_id || null,
        phone: userForm.phone || null,
        email: userForm.phone || userForm.email || null,
        password: userForm.password || null,
      }),
    });
    Object.assign(userForm, {
      user_id: "",
      display_name: "",
      phone: "",
      email: "",
      password: "",
    });
    showCreateUser.value = false;
  });
}

async function createRole(): Promise<void> {
  await mutate(async () => {
    await api<Role>("/api/v1/platform/roles", {
      method: "POST",
      body: JSON.stringify({
        role_id: roleForm.role_id || null,
        display_name: roleForm.display_name,
        scopes: parseList(roleForm.scopes),
        product_ids: roleForm.product_ids,
      }),
    });
    Object.assign(roleForm, {
      role_id: "",
      display_name: "",
      scopes: "iam:read",
      product_ids: [],
    });
    showCreateRole.value = false;
  });
}

async function createMembership(): Promise<void> {
  await mutate(async () => {
    await api<Membership>("/api/v1/platform/memberships", {
      method: "POST",
      body: JSON.stringify(membershipForm),
    });
    Object.assign(membershipForm, {
      principal_id: "",
      principal_type: "user",
      role_ids: [],
    });
    showCreateMembership.value = false;
  });
}

async function createServiceAccount(): Promise<void> {
  await mutate(async () => {
    await api<ServiceAccount>("/api/v1/platform/service-accounts", {
      method: "POST",
      body: JSON.stringify({
        service_account_id: serviceAccountForm.service_account_id || null,
        display_name: serviceAccountForm.display_name,
        scopes: parseList(serviceAccountForm.scopes),
        product_ids: serviceAccountForm.product_ids,
      }),
    });
    Object.assign(serviceAccountForm, {
      service_account_id: "",
      display_name: "",
      scopes: "iam:read",
      product_ids: [],
    });
    showCreateServiceAccount.value = false;
  });
}

async function createApiKey(): Promise<void> {
  await mutate(async () => {
    const expiresAt = keyForm.expires_at
      ? new Date(keyForm.expires_at).getTime() / 1000
      : null;
    issuedKey.value = await api<IssuedApiKey>(
      `/api/v1/platform/service-accounts/${encodeURIComponent(keyForm.service_account_id)}/api-keys`,
      {
        method: "POST",
        body: JSON.stringify({
          name: keyForm.name,
          scopes: parseList(keyForm.scopes).length
            ? parseList(keyForm.scopes)
            : null,
          product_ids: keyForm.product_ids.length ? keyForm.product_ids : null,
          expires_at: expiresAt,
        }),
      },
    );
    copied.value = false;
    Object.assign(keyForm, {
      name: "",
      scopes: "",
      product_ids: [],
      expires_at: "",
    });
    showCreateApiKey.value = false;
  });
}

async function revokeApiKey(keyId: string): Promise<void> {
  await mutate(async () => {
    await api<ApiKeyRecord>(
      `/api/v1/platform/api-keys/${encodeURIComponent(keyId)}/revoke`,
      { method: "POST" },
    );
  });
}

async function createEntitlement(): Promise<void> {
  await mutate(async () => {
    const current = entitlements.value.find(
      (item) => item.product_id === entitlementForm.product_id,
    );
    const path = current
      ? `/api/v1/platform/product-entitlements/${encodeURIComponent(entitlementForm.product_id)}`
      : "/api/v1/platform/product-entitlements";
    await api<ProductEntitlement>(path, {
      method: current ? "PUT" : "POST",
      body: JSON.stringify(
        current
          ? { status: entitlementForm.status, source: "manual" }
          : entitlementForm,
      ),
    });
    showCreateEntitlement.value = false;
  });
}

async function createHook(): Promise<void> {
  await mutate(async () => {
    await api<WebhookSubscription>("/api/v1/webhooks/subscriptions", {
      method: "POST",
      body: JSON.stringify(hook),
    });
    Object.assign(hook, {
      name: "",
      url: "",
      secret: "",
      event_types: ["result.available"],
    });
    showCreateHook.value = false;
  });
}

async function removeHook(endpointId: string): Promise<void> {
  await mutate(async () => {
    await api<void>(
      `/api/v1/webhooks/subscriptions/${encodeURIComponent(endpointId)}`,
      { method: "DELETE" },
    );
  });
}

async function copyIssuedKey(): Promise<void> {
  if (!issuedKey.value) return;
  await navigator.clipboard.writeText(issuedKey.value.api_key);
  copied.value = true;
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page access-page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="tabs-header-bar">
      <div class="domain-tabs" role="tablist" aria-label="接入管理视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="domain-tab-btn"
          :class="{ active: activeTab === tab.id }"
          role="tab"
          :aria-selected="activeTab === tab.id"
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" :size="13" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <FoundationTab
      v-if="activeTab === 'foundation'"
      :foundation="foundation"
      :iam="iam"
      :loading="loading"
      :readiness="readiness"
      :status-labels="statusLabels"
      :auth-mode-labels="authModeLabels"
      :principal-source-labels="principalSourceLabels"
      :label-context="labelContext"
    />
    <IdentityTab
      v-else-if="activeTab === 'identity'"
      :organizations="organizations"
      :projects="projects"
      :users="users"
      :roles="roles"
      :memberships="memberships"
      :filtered-organizations="filteredOrganizations"
      :filtered-projects="filteredProjects"
      :filtered-users="filteredUsers"
      :filtered-memberships="filteredMemberships"
      :filtered-roles="filteredRoles"
      :paginated-organizations="paginatedOrganizations"
      :paginated-projects="paginatedProjects"
      :paginated-users="paginatedUsers"
      :paginated-memberships="paginatedMemberships"
      :paginated-roles="paginatedRoles"
      :active-users-count="activeUsersCount"
      :disabled-users-count="disabledUsersCount"
      :user-roles-map="userRolesMap"
      :copied-key="copiedKey"
      :copy-to-clipboard="copyToClipboard"
      :open-assign-role="openAssignRole"
      :get-principal-display-name="getPrincipalDisplayName"
      :get-role-member-count="getRoleMemberCount"
      :format-time="formatTime"
      :identity-sub-tab="identitySubTab"
      :org-search="orgSearch"
      :project-search="projectSearch"
      :user-search="userSearch"
      :user-status-filter="userStatusFilter"
      :member-search="memberSearch"
      :role-search="roleSearch"
      :orgs-pagination="orgsPagination"
      :projects-pagination="projectsPagination"
      :users-pagination="usersPagination"
      :memberships-pagination="membershipsPagination"
      :roles-pagination="rolesPagination"
      @open-organization="showCreateOrg = true"
      @open-project="showCreateProject = true"
      @open-user="showCreateUser = true"
      @open-role="showCreateRole = true"
      @open-membership="openMembershipDialog"
      @update:identity-sub-tab="identitySubTab = $event"
      @update:org-search="orgSearch = $event"
      @update:project-search="projectSearch = $event"
      @update:user-search="userSearch = $event"
      @update:user-status-filter="userStatusFilter = $event"
      @update:member-search="memberSearch = $event"
      @update:role-search="roleSearch = $event"
      @update:orgs-pagination="Object.assign(orgsPagination, $event)"
      @update:projects-pagination="Object.assign(projectsPagination, $event)"
      @update:users-pagination="Object.assign(usersPagination, $event)"
      @update:memberships-pagination="
        Object.assign(membershipsPagination, $event)
      "
      @update:roles-pagination="Object.assign(rolesPagination, $event)"
    />
    <CredentialsTab
      v-else-if="activeTab === 'credentials'"
      :service-accounts="serviceAccounts"
      :api-keys="apiKeys"
      :service-account-items="paginatedServiceAccounts"
      :service-account-total="filteredServiceAccounts.length"
      :api-key-items="paginatedApiKeys"
      :api-key-total="filteredApiKeys.length"
      :mutating="mutating"
      :revoke-api-key="revokeApiKey"
      :format-time="formatTime"
      :credential-tab="credentialSubTab"
      :service-account-search="serviceAccountSearch"
      :api-key-search="apiKeySearch"
      :service-account-pagination="serviceAccountsPagination"
      :api-key-pagination="apiKeysPagination"
      @open-service-account="showCreateServiceAccount = true"
      @open-api-key="showCreateApiKey = true"
      @update:credential-tab="credentialSubTab = $event"
      @update:service-account-search="serviceAccountSearch = $event"
      @update:api-key-search="apiKeySearch = $event"
      @update:service-account-pagination="
        Object.assign(serviceAccountsPagination, $event)
      "
      @update:api-key-pagination="Object.assign(apiKeysPagination, $event)"
    />
    <ProductsTab
      v-else-if="activeTab === 'products'"
      :entitlements="entitlements"
      :items="paginatedEntitlements"
      :filtered-count="filteredEntitlements.length"
      :search="entitlementSearch"
      :offset="entitlementsPagination.offset"
      :page-size="entitlementsPagination.pageSize"
      :format-time="formatTime"
      @open-create="showCreateEntitlement = true"
      @update:search="entitlementSearch = $event"
      @update:offset="entitlementsPagination.offset = $event"
      @update:page-size="entitlementsPagination.pageSize = $event"
    />
    <EventsTab
      v-else-if="activeTab === 'events'"
      :subscriptions="subscriptions"
      :deliveries="deliveries"
      :subscription-items="paginatedSubscriptions"
      :subscription-total="filteredSubscriptions.length"
      :delivery-items="paginatedDeliveries"
      :delivery-total="filteredDeliveries.length"
      :remove-hook="removeHook"
      :format-time="formatTime"
      :event-tab="eventSubTab"
      :subscription-search="subscriptionSearch"
      :delivery-status="deliveryStatusFilter"
      :subscription-pagination="subscriptionsPagination"
      :delivery-pagination="deliveriesPagination"
      @open-create="showCreateHook = true"
      @update:event-tab="eventSubTab = $event"
      @update:subscription-search="subscriptionSearch = $event"
      @update:delivery-status="deliveryStatusFilter = $event"
      @update:subscription-pagination="
        Object.assign(subscriptionsPagination, $event)
      "
      @update:delivery-pagination="Object.assign(deliveriesPagination, $event)"
    />
    <ConnectionTab
      v-else
      :form="form"
      :show-token="showConnectionToken"
      :reset-connection="resetConnection"
      :apply-connection="applyConnection"
      @update:form="Object.assign(form, $event)"
      @update:show-token="showConnectionToken = $event"
    />

    <IdentityDialogs
      v-model:show-create-org="showCreateOrg"
      v-model:show-create-project="showCreateProject"
      v-model:show-create-user="showCreateUser"
      v-model:show-create-membership="showCreateMembership"
      v-model:show-create-role="showCreateRole"
      :organization-form="organizationForm"
      :project-form="projectForm"
      :user-form="userForm"
      :membership-form="membershipForm"
      :role-form="roleForm"
      :roles="roles"
      :principal-candidate-options="principalCandidateOptions"
      :scope-presets="scopePresets"
      :product-list="productList"
      :mutating="mutating"
      :create-organization="createOrganization"
      :create-project="createProject"
      :create-user="createUser"
      :create-membership="createMembership"
      :create-role="createRole"
      @update:organization-form="Object.assign(organizationForm, $event)"
      @update:project-form="Object.assign(projectForm, $event)"
      @update:user-form="Object.assign(userForm, $event)"
      @update:membership-form="Object.assign(membershipForm, $event)"
      @update:role-form="Object.assign(roleForm, $event)"
    />
    <CredentialsDialogs
      v-model:show-create-service-account="showCreateServiceAccount"
      v-model:show-create-api-key="showCreateApiKey"
      :service-account-form="serviceAccountForm"
      :key-form="keyForm"
      :service-accounts="serviceAccounts"
      :product-list="productList"
      :mutating="mutating"
      :create-service-account="createServiceAccount"
      :create-api-key="createApiKey"
      @update:service-account-form="Object.assign(serviceAccountForm, $event)"
      @update:key-form="Object.assign(keyForm, $event)"
    />
    <ProductsDialog
      v-model:show-create-entitlement="showCreateEntitlement"
      :entitlement-form="entitlementForm"
      :available-products="availableProducts"
      :selected-product="selectedEntitlementProduct"
      :label-scope-tag="labelScopeTag"
      :mutating="mutating"
      :create-entitlement="createEntitlement"
      @update:entitlement-form="Object.assign(entitlementForm, $event)"
    />
    <EventsDialog
      v-model:show-create-hook="showCreateHook"
      v-model:show-hook-secret="showHookSecret"
      :hook="hook"
      :event-options="eventOptions"
      :mutating="mutating"
      :create-hook="createHook"
      @update:hook="Object.assign(hook, $event)"
    />
    <IssuedKeyDialog
      :issued-key="issuedKey"
      :copied="copied"
      :copy-issued-key="copyIssuedKey"
    />
  </section>
</template>

<style>
/* 顶部统一样式的分类 Tabs 导航条 */
.access-page .tabs-header-bar {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}

.access-page .subtabs-bar {
  display: flex;
  align-items: center;
  margin: 12px 0 14px;
}

.access-page .tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.08);
  font-size: 10px;
  font-weight: 600;
  color: inherit;
}
.access-page .domain-tab-btn.active .tab-badge {
  background: var(--color-accent, #087682);
  color: #ffffff;
}

.access-page .domain-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
  flex-wrap: wrap;
}

.access-page .domain-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.access-page .domain-tab-btn:hover {
  color: var(--graphite, #17211f);
  background: rgba(255, 255, 255, 0.6);
}

.access-page .domain-tab-btn.active {
  color: var(--color-accent-hover, #065e67);
  background: var(--color-accent-soft, #e4f1f1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.access-page .access-panel {
  margin-top: 14px;
}

.access-page .section-gap {
  margin-top: 14px;
}

.access-page .inventory-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.access-page .iam-stats-grid {
  margin-bottom: 2px;
}

.access-page .foundation-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--line, #e2e8e6);
  border-bottom: 1px solid var(--line, #e2e8e6);
}

.access-page .foundation-meta div {
  min-width: 0;
  padding: 12px 14px;
  background: #fff;
}

.access-page .foundation-meta span,
.access-page .record-row small {
  display: block;
  color: var(--muted, #64716d);
  font-size: 11px;
}

.access-page .foundation-meta strong {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  font-size: 12.5px;
}

.access-page .capability-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  vertical-align: middle;
}

.access-page .capability-status-icon {
  flex-shrink: 0;
}
.access-page .capability-status-icon.available {
  color: var(--color-accent, #087682);
}
.access-page .capability-status-icon.planned {
  color: var(--muted, #64716d);
}
.access-page .capability-status-icon.gated {
  color: #b45309;
}

.access-page .badge.available {
  background: #e4f2e9;
  color: #226a42;
}

.access-page .badge.seed {
  background: var(--teal-soft, #e0f2fe);
  color: #08636c;
}

.access-page .badge.planned {
  background: #edf0ef;
  color: #45534f;
}

.access-page .badge.gated {
  background: #fbf0de;
  color: #8b5a14;
}

/* 头部左右布局与操作区域 */
.access-page .header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.access-page .header-icon {
  color: var(--color-accent, #087682);
  flex-shrink: 0;
}

.access-page .header-sub-stats {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 6px;
  font-size: 11px;
  padding: 1px 8px;
  background: #f1f4f3;
  border-radius: 12px;
  white-space: nowrap;
}

.access-page .sub-stat-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.access-page .sub-stat-dot.active {
  background: #16a34a;
}
.access-page .sub-stat-dot.disabled {
  background: #94a3b8;
  margin-left: 4px;
}

.access-page .sub-stat-text {
  font-size: 11px;
  color: var(--graphite, #17211f);
  font-weight: 500;
}

.access-page .header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  flex-shrink: 0;
}

.access-page .tiny-btn {
  min-height: 28px !important;
  height: 28px !important;
  padding: 0 10px !important;
  font-size: 11.5px !important;
  border-radius: 4px !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 4px !important;
  box-sizing: border-box !important;
  white-space: nowrap !important;
  flex-shrink: 0 !important;
}

/* 折叠式表单面板 */
.access-page .collapsible-form-box {
  background: var(--surface-soft, #f6f8f7);
  border-bottom: 1px solid var(--line, #e2e8e6);
  padding: 14px 16px;
  animation: slideDown 180ms ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.access-page .form-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  margin-bottom: 10px;
}

.access-page .form-grid-inline {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.access-page .form-grid-inline .form-field {
  flex: 1;
  margin-bottom: 0;
}

.access-page .form-grid-2col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}

.access-page .form-grid-4col {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}

.access-page .form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 10px;
}

.access-page .field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.access-page .field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.access-page .field-label .required {
  color: var(--coral, #ef4444);
  font-style: normal;
  font-weight: 700;
}

.access-page .field-input {
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  font-size: 12px;
  color: var(--graphite, #17211f);
  outline: none;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.access-page .field-input:focus {
  border-color: var(--color-accent, #087682);
  box-shadow: 0 0 0 2px var(--color-accent-soft, #e4f1f1);
}

.access-page .form-action-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.access-page select.filter-select-sm,
.access-page .filter-select-sm {
  width: auto !important;
  min-width: 106px !important;
  height: 28px !important;
  min-height: 28px !important;
  padding: 0 10px !important;
  border: 1px solid var(--line, #e2e8e6) !important;
  border-radius: 4px !important;
  background: #ffffff !important;
  font-size: 11.5px !important;
  color: var(--graphite, #17211f) !important;
  cursor: pointer !important;
  box-sizing: border-box !important;
  flex-shrink: 0 !important;
}

/* 用户数据表格行样式 */
.access-page .iam-table {
  border-collapse: collapse !important;
}

.access-page .text-center {
  text-align: center !important;
}

.access-page .user-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  white-space: nowrap;
}

.access-page .avatar-circle {
  width: 18px;
  height: 18px;
  min-width: 18px;
  min-height: 18px;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  line-height: 16px;
}

.access-page .avatar-teal {
  background: #e4f1f1 !important;
  color: #065e67 !important;
  border: 1px solid rgba(8, 118, 130, 0.25) !important;
}
.access-page .avatar-blue {
  background: #eff6ff !important;
  color: #1d4ed8 !important;
  border: 1px solid #bfdbfe !important;
}
.access-page .avatar-purple {
  background: #f5f3ff !important;
  color: #6d28d9 !important;
  border: 1px solid #ddd6fe !important;
}
.access-page .avatar-amber {
  background: #fffbeb !important;
  color: #b45309 !important;
  border: 1px solid #fde68a !important;
}
.access-page .avatar-emerald {
  background: #ecfdf5 !important;
  color: #047857 !important;
  border: 1px solid #a7f3d0 !important;
}
.access-page .avatar-rose {
  background: #fff1f2 !important;
  color: #be123c !important;
  border: 1px solid #fecdd3 !important;
}

.access-page .user-cell-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.access-page .user-name {
  font-weight: 600;
  font-size: 12px;
}

.access-page .user-id-chip-row {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.access-page .phone-cell {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--graphite, #17211f);
}

.access-page .copy-mini-btn {
  background: transparent;
  border: none;
  padding: 2px;
  color: var(--muted, #64716d);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 2px;
  transition: all 0.15s ease;
  opacity: 0.6;
}
.access-page .copy-mini-btn:hover {
  opacity: 1;
  color: var(--color-accent, #087682);
  background: #eef2f1;
}

.access-page .copied-check {
  color: #16a34a;
}

.access-page .muted-id {
  font-size: 11.5px;
  color: var(--muted, #64716d);
  font-family: var(--font-mono);
}

.access-page .email-cell {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--graphite, #17211f);
}
.access-page .muted-icon {
  color: var(--muted, #64716d);
}

.access-page .role-tags-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.access-page .assign-role-btn-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: transparent;
  border: 1px dashed var(--line-strong, #b7c2bd);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 10.5px;
  color: var(--color-accent, #087682);
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 16px;
}
.access-page .assign-role-btn-link:hover {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
}

.access-page .role-pill {
  background: #eef5f4;
  color: #17544e;
  border: 1px solid #d3e5e2;
  font-size: 10.5px;
  font-weight: 500;
  padding: 0 6px;
  gap: 3px;
}

.access-page .no-role-hint {
  font-size: 11px;
  color: #9eb0aa;
}

.access-page .status-pill {
  font-size: 10.5px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.access-page .status-pill.active {
  background: #e8f5ed;
  color: #1b6338;
}
.access-page .status-pill.failed {
  background: #fdf0ee;
  color: #a33222;
}

.access-page .status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

/* 组织与项目卡片列表 */
.access-page .org-list,
.access-page .project-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
}

.access-page .entity-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  transition: all 0.15s ease;
}
.access-page .entity-card:hover {
  border-color: var(--color-accent, #087682);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}

.access-page .entity-avatar {
  width: 34px;
  height: 34px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.access-page .org-avatar {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
}
.access-page .project-avatar {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #dcfce7;
}

.access-page .entity-info {
  flex: 1;
  min-width: 0;
}

.access-page .entity-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}
.access-page .entity-name-row strong {
  font-size: 13px;
  color: var(--graphite, #17211f);
}

.access-page .entity-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.access-page .meta-dot {
  color: var(--line-strong, #b7c2bd);
}

.access-page .primary-soft {
  background: var(--color-accent-soft, #e4f1f1);
  color: var(--color-accent-hover, #065e67);
  border: 1px solid rgba(8, 118, 130, 0.2);
  font-size: 10px;
}

.access-page .ghost-badge {
  background: #f1f4f3;
  color: var(--muted, #64716d);
  font-size: 10.5px;
}

/* 权限预设药丸与产品选择芯片 */
.access-page .scope-presets-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 6px;
}

.access-page .preset-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--line, #e2e8e6);
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.access-page .preset-chip:hover {
  background: #f5f8f7;
  border-color: #bcc6c2;
}
.access-page .preset-chip.active {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
  color: var(--color-accent-hover, #065e67);
  font-weight: 600;
}

.access-page .scope-input {
  margin-top: 2px;
}

.access-page .chips-quick-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.access-page .link-btn {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--color-accent, #087682);
  cursor: pointer;
  font-size: 11px;
}
.access-page .link-btn:hover {
  text-decoration: underline;
}

.access-page .divider {
  color: var(--line-strong, #b7c2bd);
}

.access-page .product-chips-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 12px;
}

.access-page .product-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--line, #e2e8e6);
  background: #ffffff;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
  min-width: 0;
  box-sizing: border-box;
}
.access-page .product-chip:hover {
  border-color: #bcc6c2;
  background: #f8faf9;
}
.access-page .product-chip.active {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
}

.access-page .chip-check {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  border: 1px solid var(--line-strong, #b7c2bd);
  background: #ffffff;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: var(--color-accent, #087682);
}
.access-page .product-chip.active .chip-check {
  border-color: var(--color-accent, #087682);
  background: var(--color-accent, #087682);
  color: #ffffff;
}

.access-page .chip-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
  flex: 1;
}
.access-page .chip-text strong {
  font-size: 12.5px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.access-page .chip-text small {
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ==================== 产品授权卡片网格选择器 (Modal 8) ==================== */
.access-page .entitlement-product-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 12px;
  padding: 2px;
  box-sizing: border-box;
}

.access-page .entitlement-product-card {
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: all 0.15s ease;
  user-select: none;
  box-sizing: border-box;
  min-height: 106px;
}

.access-page .entitlement-product-card:hover {
  border-color: #bcc6c2;
  background: #fafbfb;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
}

.access-page .entitlement-product-card.active {
  background: var(--color-accent-soft, #eef7f7);
  border-color: var(--color-accent, #087682);
  box-shadow: 0 0 0 1px var(--color-accent, #087682);
}

.access-page .product-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.access-page .product-card-title {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.access-page .product-card-title strong {
  font-size: 12px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.access-page .product-card-id {
  font-size: 10.5px;
  color: var(--muted, #64716d);
}

.access-page .product-card-radio {
  flex-shrink: 0;
  margin-top: 2px;
}

.access-page .product-card-radio .radio-circle {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 1.5px solid var(--line-strong, #b7c2bd);
  background: #ffffff;
  display: grid;
  place-items: center;
  transition: all 0.15s ease;
}

.access-page .product-card-radio .radio-circle.selected {
  border-color: var(--color-accent, #087682);
}

.access-page .radio-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-accent, #087682);
}

.access-page .product-card-summary {
  margin: 0;
  font-size: 10.5px;
  color: var(--muted, #64716d);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.access-page .product-card-scopes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.access-page .mini-scope-tag {
  display: inline-block;
  padding: 1px 5px;
  font-size: 9.5px;
  border-radius: 3px;
  background: #edf2f1;
  color: #3b4d48;
  white-space: nowrap;
}

.access-page .mini-scope-tag.muted {
  color: var(--muted, #64716d);
  background: #f4f6f5;
}

.access-page .selected-preview-box {
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 8px 10px;
}

.access-page .preview-scopes-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

/* 角色与成员卡片清单 */
.access-page .role-card-list,
.access-page .member-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
}

.access-page .role-card-item {
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: all 0.15s ease;
}
.access-page .role-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
}

.access-page .role-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.access-page .role-title-box {
  display: flex;
  align-items: center;
  gap: 7px;
}
.access-page .role-icon {
  color: var(--color-accent, #087682);
}
.access-page .role-title-box strong {
  font-size: 13px;
}

.access-page .role-id-badge {
  font-size: 10.5px;
  color: var(--muted, #64716d);
  background: #f1f4f3;
  padding: 1px 5px;
  border-radius: 3px;
}

.access-page .member-count-badge {
  background: #edf0ef;
  color: #45534f;
  font-size: 10px;
}

.access-page .role-scopes-row,
.access-page .role-products-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.access-page .scope-pill {
  background: #f4f6f5;
  color: #2b3a36;
  border: 1px solid #e1e7e4;
  font-size: 10.5px;
}
.access-page .mono-sub {
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--muted, #64716d);
  margin-left: 3px;
}

.access-page .products-label {
  font-size: 10.5px;
  color: var(--muted, #64716d);
  font-weight: 500;
}
.access-page .product-pill {
  background: #f0f7f6;
  color: #0c6a72;
  border: 1px solid #d0e7e5;
  font-size: 10px;
}

/* 分段控制器与药丸选择 */
.access-page .segmented-control {
  display: flex;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
  width: 100%;
  box-sizing: border-box;
  height: 32px;
  align-items: center;
}

.access-page .seg-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  height: 26px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.access-page .seg-btn:hover {
  color: var(--graphite, #17211f);
}
.access-page .seg-btn.active {
  background: #ffffff;
  color: var(--color-accent, #087682);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.access-page .role-selection-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.access-page .role-select-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 5px;
  border: 1px solid var(--line, #e2e8e6);
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.access-page .role-select-pill:hover {
  background: #f5f8f7;
  border-color: #bcc6c2;
}
.access-page .role-select-pill.active {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
  color: var(--color-accent-hover, #065e67);
  font-weight: 600;
}

.access-page .member-card-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  transition: all 0.15s ease;
}
.access-page .member-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
}

.access-page .member-card-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.access-page .member-card-avatar.user {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
}
.access-page .member-card-avatar.service_account {
  background: #eff6ff;
  color: #2563eb;
  border: 1px solid #dbeafe;
}

.access-page .member-card-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.access-page .member-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.access-page .member-name-row strong {
  font-size: 12.5px;
}

.access-page .type-badge.user {
  background: #e6f4f1;
  color: #0f766e;
}
.access-page .type-badge.service_account {
  background: #eff6ff;
  color: #2563eb;
}

.access-page .member-roles-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

/* 基础通用样式 */
.access-page .form-stack {
  display: grid;
  gap: 10px;
}

.access-page .inline-form {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1.4fr auto;
  gap: 10px;
  align-items: end;
  margin-bottom: 12px;
}

.access-page .record-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 36px;
  padding: 6px 0;
  border-top: 1px solid #e8ecea;
  font-size: 11.5px;
}

.access-page .record-row > div {
  min-width: 0;
}

.access-page .record-row small {
  margin-top: 2px;
  overflow-wrap: anywhere;
}

.access-page select[multiple] {
  min-height: 76px;
}

.access-page .entitlement-form {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(160px, 0.6fr) auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 12px;
}

.access-page .event-options {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 12px;
  margin: 12px 0;
}

.access-page .event-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.access-page .event-options input {
  width: 14px;
  min-height: 14px;
}

.access-page .connection-form {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr 1.5fr auto;
  gap: 12px;
  align-items: end;
}

.access-page .compact-empty {
  min-height: 90px;
}

.access-page .danger-icon {
  color: var(--coral, #ef4444);
}

.access-page .danger-btn {
  color: var(--coral, #ef4444) !important;
  border-color: rgba(239, 68, 68, 0.3) !important;
}
.access-page .danger-btn:hover {
  background: #fef2f2 !important;
  border-color: var(--coral, #ef4444) !important;
}

/* 能力清单卡片 */
.access-page .capability-main {
  min-width: 0;
}

.access-page .capability-name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.access-page .capability-status-icon {
  flex-shrink: 0;
}
.access-page .capability-status-icon.available {
  color: #16a34a;
}
.access-page .capability-status-icon.planned {
  color: #64716d;
}
.access-page .capability-status-icon.gated {
  color: #d97706;
}

.access-page .capability-gate {
  text-align: right;
}

/* 凭据与产品头像徽章 */
.access-page .sa-avatar {
  background: #eff6ff !important;
  color: #2563eb !important;
  border-color: #dbeafe !important;
}

.access-page .key-avatar {
  background: #fef3c7 !important;
  color: #d97706 !important;
  border-color: #fde68a !important;
}

.access-page .prod-avatar {
  background: #f3e8ff !important;
  color: #9333ea !important;
  border-color: #e9d5ff !important;
}

/* 密码与敏感输入切换 */
.access-page .password-input-box {
  position: relative;
  display: flex;
  align-items: center;
}

.access-page .password-input {
  width: 100%;
  padding-right: 34px !important;
}

.access-page .icon-toggle-btn {
  position: absolute;
  right: 8px;
  background: transparent;
  border: none;
  color: var(--muted, #64716d);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: color 0.15s ease;
}
.access-page .icon-toggle-btn:hover {
  color: var(--graphite, #17211f);
}

/* 事件回调芯片与药丸 */
.access-page .event-chips-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.access-page .event-pill {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
  font-size: 10px;
}

/* HTTP 状态码徽章 */
.access-page .http-status-badge {
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  font-weight: 600;
}
.access-page .http-status-badge.status-2xx {
  background: #e8f5ed;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.access-page .http-status-badge.status-err {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

/* 连接设置配置卡片 */
.access-page .connection-settings-panel {
  max-width: 860px;
}

.access-page .connection-body {
  padding: 16px 18px;
}

.access-page .connection-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 16px;
  margin-bottom: 20px;
}

.access-page .field-help {
  font-size: 10.5px;
  margin-top: 2px;
  line-height: 1.3;
}

.access-page .connection-footer-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--line, #e2e8e6);
}

/* 全局统一 28px 数据表格行高与 2px 8px 内边距、四周完整边框与单行截断 */
.access-page .table-scroll {
  overflow-x: auto;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  margin-bottom: 6px;
}

.access-page .data-table,
.access-page .iam-table {
  width: 100%;
  border-collapse: collapse !important;
  border: none !important;
  font-size: 11.5px !important;
  table-layout: auto;
}

.access-page .data-table th,
.access-page .iam-table th {
  height: 28px !important;
  min-height: 28px !important;
  max-height: 28px !important;
  padding: 2px 8px !important;
  font-size: 11.5px !important;
  font-weight: 600;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  background: #fafbfb;
  color: var(--muted, #64716d);
  border: 1px solid var(--line, #e2e8e6) !important;
  vertical-align: middle;
  box-sizing: border-box;
}

.access-page .data-table td,
.access-page .iam-table td {
  height: 28px !important;
  min-height: 28px !important;
  max-height: 28px !important;
  padding: 2px 8px !important;
  vertical-align: middle;
  line-height: 24px !important;
  font-size: 11.5px !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  border: 1px solid var(--line, #e2e8e6) !important;
  color: var(--graphite, #17211f);
  box-sizing: border-box;
}

.access-page .data-table tr,
.access-page .iam-table tr {
  height: 28px !important;
  max-height: 28px !important;
}

.access-page .data-table td strong,
.access-page .iam-table td strong {
  font-weight: 600;
  display: inline !important;
}

.access-page .data-table td .mono.muted,
.access-page .iam-table td .mono.muted {
  margin-left: 4px;
  display: inline !important;
  font-size: 11px;
  color: var(--muted, #64716d);
}

/* 按钮及胶囊高度严格微型化 (20px)，严禁撑高 28px 单元格行高 */
.access-page .data-table .button.tiny-btn,
.access-page .iam-table .button.tiny-btn {
  width: auto !important;
  min-width: unset !important;
  height: 20px !important;
  min-height: 20px !important;
  max-height: 20px !important;
  line-height: 18px !important;
  padding: 0 6px !important;
  font-size: 10.5px !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 3px !important;
  box-sizing: border-box !important;
  white-space: nowrap !important;
}

.access-page .data-table .icon-button,
.access-page .iam-table .icon-button {
  width: 20px !important;
  min-width: 20px !important;
  height: 20px !important;
  min-height: 20px !important;
  max-height: 20px !important;
  padding: 0 !important;
  font-size: 10.5px !important;
  display: inline-grid !important;
  place-items: center !important;
  box-sizing: border-box !important;
}

.access-page .data-table .badge,
.access-page .iam-table .badge,
.access-page .badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 18px !important;
  min-height: 18px !important;
  max-height: 18px !important;
  line-height: 16px !important;
  padding: 0 5px !important;
  font-size: 10px !important;
  white-space: nowrap !important;
  box-sizing: border-box !important;
}

.access-page .role-tags-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.access-page .assign-role-btn-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: transparent;
  border: 1px dashed var(--line-strong, #b7c2bd);
  border-radius: 3px;
  padding: 0 5px;
  font-size: 10px;
  color: var(--color-accent, #087682);
  cursor: pointer;
  height: 18px;
  line-height: 16px;
  box-sizing: border-box;
}

@media (max-width: 1080px) {
  .access-page .inventory-grid,
  .access-page .foundation-meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .access-page .form-grid-4col {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .access-page .inline-form,
  .access-page .connection-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .access-page .event-options {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .access-page .inventory-grid,
  .access-page .foundation-meta,
  .access-page .inline-form,
  .access-page .connection-form,
  .access-page .connection-form-grid,
  .access-page .entitlement-form,
  .access-page .form-grid-2col,
  .access-page .form-grid-4col,
  .access-page .form-grid-inline {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }
  .access-page .capability-row {
    grid-template-columns: 1fr;
  }
  .access-page .capability-gate {
    text-align: left;
  }
  .access-page .capability-list {
    padding: 10px;
  }
  .access-page .event-options {
    grid-template-columns: 1fr;
  }
}

/* ==================== 模态弹窗系统样式 (Modal Dialog System) ==================== */
.access-page .modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 21, 0.48);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1200;
  padding: 16px;
  animation: modalFadeIn 150ms ease-out;
}

@keyframes modalFadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.access-page .modal-dialog {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  box-shadow:
    0 20px 50px rgba(15, 23, 21, 0.22),
    0 4px 12px rgba(0, 0, 0, 0.08);
  width: min(640px, 95vw);
  max-height: calc(100vh - 40px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: modalScaleUp 180ms cubic-bezier(0.16, 1, 0.3, 1);
}

.access-page .modal-dialog.modal-dialog-md {
  width: min(780px, 95vw);
}

.access-page .modal-dialog.modal-dialog-lg {
  width: min(980px, 96vw);
}

.access-page .modal-dialog.modal-dialog-xl {
  width: min(1120px, 96vw);
}

@keyframes modalScaleUp {
  from {
    opacity: 0;
    transform: scale(0.96) translateY(-8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.access-page .modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
  flex-shrink: 0;
}

.access-page .modal-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.access-page .modal-title-icon {
  color: var(--color-accent, #087682);
  flex-shrink: 0;
}

.access-page .modal-title-box h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  line-height: 1.2;
}

.access-page .modal-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.3;
}

.access-page .modal-close-btn {
  background: transparent;
  border: none;
  color: var(--muted, #64716d);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}
.access-page .modal-close-btn:hover {
  background: #edf2f0;
  color: var(--graphite, #17211f);
}

.access-page .modal-body {
  padding: 18px;
  overflow-y: auto;
  max-height: calc(100vh - 180px);
}

.access-page .modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
  flex-shrink: 0;
}
</style>
