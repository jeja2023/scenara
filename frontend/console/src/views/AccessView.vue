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

<style src="./access/access-view.css"></style>
