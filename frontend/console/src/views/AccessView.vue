<script setup lang="ts">
import DataTablePagination from "../components/DataTablePagination.vue";
import {
  BellPlus,
  Boxes,
  Building2,
  Check,
  CheckCircle2,
  Clipboard,
  Clock,
  Eye,
  EyeOff,
  FolderGit2,
  KeyRound,
  Lock,
  Phone,
  Plus,
  Radio,
  RotateCcw,
  Search,
  Server,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  X,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRefresh } from "../composables/useRefresh";
import {
  api,
  loadConnection,
  saveConnection,
  userFacingError,
  type ConnectionSettings,
} from "../api";
import {
  labelAccessCapability,
  labelDeliveryStatus,
  labelEntitlementSource,
  labelEventType,
  labelPolicyProvider,
  labelProduct,
  labelProductSummary,
  labelScope,
} from "../labels";
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
import type { AccessTab, DisplayProduct, IssuedApiKey } from "./access/types";
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
const keyDialog = ref<HTMLDialogElement | null>(null);
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

const productOptions = computed(() => availableProducts.value.map((p) => p.id));
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

type IdentitySubTab =
  "organizations" | "projects" | "users" | "memberships" | "roles";
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

const organizationForm = reactive({ display_name: "" });
const projectForm = reactive({ project_id: "", display_name: "" });
const userForm = reactive({
  user_id: "",
  display_name: "",
  phone: "",
  email: "",
  password: "",
});
const roleForm = reactive({
  role_id: "",
  display_name: "",
  scopes: "iam:read",
  product_ids: [] as string[],
});
const membershipForm = reactive({
  principal_id: "",
  principal_type: "user" as "user" | "service_account",
  role_ids: [] as string[],
});
const serviceAccountForm = reactive({
  service_account_id: "",
  display_name: "",
  scopes: "iam:read",
  product_ids: [] as string[],
});
const keyForm = reactive({
  service_account_id: "",
  name: "",
  scopes: "",
  product_ids: [] as string[],
  expires_at: "",
});
const entitlementForm = reactive({
  product_id: "parse",
  status: "active" as "active" | "suspended",
});
const hook = reactive({
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

const principalCandidateOptions = computed(() => {
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

function toggleRoleProduct(productId: string) {
  const index = roleForm.product_ids.indexOf(productId);
  if (index >= 0) {
    roleForm.product_ids.splice(index, 1);
  } else {
    roleForm.product_ids.push(productId);
  }
}

function selectAllRoleProducts() {
  roleForm.product_ids = productOptions.value.slice();
}

function clearRoleProducts() {
  roleForm.product_ids = [];
}

function toggleMembershipRole(roleId: string) {
  const index = membershipForm.role_ids.indexOf(roleId);
  if (index >= 0) {
    membershipForm.role_ids.splice(index, 1);
  } else {
    membershipForm.role_ids.push(roleId);
  }
}

function toggleScopePreset(scopeId: string) {
  const current = parseList(roleForm.scopes);
  const index = current.indexOf(scopeId);
  if (index >= 0) {
    current.splice(index, 1);
  } else {
    current.push(scopeId);
  }
  roleForm.scopes = current.join(", ");
}

function toggleServiceAccountProduct(productId: string) {
  const index = serviceAccountForm.product_ids.indexOf(productId);
  if (index >= 0) {
    serviceAccountForm.product_ids.splice(index, 1);
  } else {
    serviceAccountForm.product_ids.push(productId);
  }
}

function selectAllServiceAccountProducts() {
  serviceAccountForm.product_ids = productOptions.value.slice();
}

function clearServiceAccountProducts() {
  serviceAccountForm.product_ids = [];
}

function toggleKeyProduct(productId: string) {
  const index = keyForm.product_ids.indexOf(productId);
  if (index >= 0) {
    keyForm.product_ids.splice(index, 1);
  } else {
    keyForm.product_ids.push(productId);
  }
}

function selectAllKeyProducts() {
  keyForm.product_ids = productOptions.value.slice();
}

function clearKeyProducts() {
  keyForm.product_ids = [];
}

function toggleHookEventType(event: string) {
  const index = hook.event_types.indexOf(event);
  if (index >= 0) {
    hook.event_types.splice(index, 1);
  } else {
    hook.event_types.push(event);
  }
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
    keyDialog.value?.showModal();
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
  <section class="page">
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

    <template v-if="activeTab === 'foundation'">
      <!-- 4 组核心能力统计卡片 -->
      <div class="inventory-grid">
        <div class="stat teal">
          <div class="stat-top-row">
            <span class="stat-title">底座就绪状态</span>
            <div class="stat-icon-badge"><ShieldCheck :size="15" /></div>
          </div>
          <div class="stat-value">
            {{ readiness.available }}/{{
              (foundation?.capabilities ?? []).length
            }}
          </div>
          <div class="stat-desc">
            {{ readiness.available }} 项已就绪 ·
            {{ readiness.planned }} 项规划中 · {{ readiness.gated }} 项受限
          </div>
        </div>

        <div class="stat">
          <div class="stat-top-row">
            <span class="stat-title">策略提供方</span>
            <div class="stat-icon-badge"><Lock :size="15" /></div>
          </div>
          <div class="stat-value">
            {{
              foundation
                ? labelPolicyProvider(foundation.policy_provider)
                : "未连接"
            }}
          </div>
          <div class="stat-desc">
            认证模式:
            {{ foundation ? authModeLabels[foundation.auth_mode] : "未知" }}
          </div>
        </div>

        <div class="stat green">
          <div class="stat-top-row">
            <span class="stat-title">鉴权主体模型</span>
            <div class="stat-icon-badge"><Users :size="15" /></div>
          </div>
          <div class="stat-value">
            {{
              foundation
                ? principalSourceLabels[foundation.principal_source]
                : "未知"
            }}
          </div>
          <div class="stat-desc">
            租户:
            {{ foundation ? labelContext(foundation.tenant_id, "租户") : "-" }}
            · 项目:
            {{ foundation ? labelContext(foundation.project_id, "项目") : "-" }}
          </div>
        </div>

        <div class="stat coral">
          <div class="stat-top-row">
            <span class="stat-title">接入资源总览</span>
            <div class="stat-icon-badge"><Boxes :size="15" /></div>
          </div>
          <div class="stat-value">
            {{
              (iam?.inventory.service_accounts ?? 0) +
              (iam?.inventory.api_keys ?? 0)
            }}
          </div>
          <div class="stat-desc">
            {{ iam?.inventory.service_accounts ?? 0 }} 个服务账号 ·
            {{ iam?.inventory.api_keys ?? 0 }} 个密钥
          </div>
        </div>
      </div>

      <section class="panel access-panel">
        <div class="panel-header">
          <div class="header-left">
            <Server :size="16" class="header-icon" />
            <h2>访问底座</h2>
            <span class="badge" :class="foundation ? 'available' : 'gated'">
              {{
                foundation
                  ? labelPolicyProvider(foundation.policy_provider)
                  : "未读取"
              }}
            </span>
          </div>
        </div>

        <!-- 基础元数据栏 -->
        <div class="foundation-meta">
          <div>
            <span>认证模式</span>
            <strong>{{
              foundation ? authModeLabels[foundation.auth_mode] : "?"
            }}</strong>
          </div>
          <div>
            <span>身份来源</span>
            <strong>{{
              foundation
                ? principalSourceLabels[foundation.principal_source]
                : "?"
            }}</strong>
          </div>
          <div>
            <span>作用域</span>
            <strong>
              {{
                foundation ? labelContext(foundation.tenant_id, "租户") : "?"
              }}
              /
              {{
                foundation ? labelContext(foundation.project_id, "项目") : "?"
              }}
            </strong>
          </div>
          <div>
            <span>能力分布</span>
            <strong
              >{{ readiness.available }} 可用 · {{ readiness.planned }} 规划 ·
              {{ readiness.gated }} 门禁</strong
            >
          </div>
        </div>

        <!-- 访问底座核心能力分列表格 -->
        <div class="table-scroll" style="margin-top: 8px">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 150px">能力名称</th>
                <th style="min-width: 260px">功能职责说明</th>
                <th style="width: 90px; text-align: center">当前状态</th>
                <th style="min-width: 320px">阶段目标与演进门禁</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in foundation?.capabilities ?? []"
                :key="item.capability_id"
              >
                <td class="muted text-center">{{ index + 1 }}</td>
                <td>
                  <div class="capability-cell">
                    <component
                      :is="
                        item.status === 'available'
                          ? CheckCircle2
                          : item.status === 'planned'
                            ? Clock
                            : ShieldAlert
                      "
                      :size="14"
                      class="capability-status-icon"
                      :class="item.status"
                    />
                    <strong>{{
                      labelAccessCapability(item.capability_id).name
                    }}</strong>
                  </div>
                </td>
                <td :title="labelAccessCapability(item.capability_id).summary">
                  {{ labelAccessCapability(item.capability_id).summary }}
                </td>
                <td class="text-center">
                  <span
                    class="badge status-pill"
                    :class="
                      item.status === 'available'
                        ? 'active'
                        : item.status === 'planned'
                          ? 'ghost-badge'
                          : 'failed'
                    "
                  >
                    <span class="status-dot"></span>
                    {{ statusLabels[item.status] }}
                  </span>
                </td>
                <td
                  class="muted"
                  :title="labelAccessCapability(item.capability_id).nextGate"
                >
                  {{ labelAccessCapability(item.capability_id).nextGate }}
                </td>
              </tr>
              <tr v-if="!foundation?.capabilities?.length">
                <td colspan="5" class="empty">
                  {{
                    loading ? "正在加载访问底座状态..." : "未读取到访问底座状态"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <template v-else-if="activeTab === 'identity'">
      <!-- 统一的子模块 Tab 切换栏 -->
      <div class="tabs-header-bar subtabs-bar">
        <div class="domain-tabs" role="tablist" aria-label="成员与角色子视图">
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: identitySubTab === 'organizations' }"
            @click="identitySubTab = 'organizations'"
          >
            <Building2 :size="13" />
            <span>组织</span>
            <span class="tab-badge">{{ organizations.length }}</span>
          </button>
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: identitySubTab === 'projects' }"
            @click="identitySubTab = 'projects'"
          >
            <FolderGit2 :size="13" />
            <span>项目</span>
            <span class="tab-badge">{{ projects.length }}</span>
          </button>
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: identitySubTab === 'users' }"
            @click="identitySubTab = 'users'"
          >
            <Users :size="13" />
            <span>用户管理</span>
            <span class="tab-badge">{{ users.length }}</span>
          </button>
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: identitySubTab === 'memberships' }"
            @click="identitySubTab = 'memberships'"
          >
            <UserCheck :size="13" />
            <span>项目成员</span>
            <span class="tab-badge">{{ memberships.length }}</span>
          </button>
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: identitySubTab === 'roles' }"
            @click="identitySubTab = 'roles'"
          >
            <Shield :size="13" />
            <span>角色与权限</span>
            <span class="tab-badge">{{ roles.length }}</span>
          </button>
        </div>
      </div>

      <!-- 子视图 1：组织 (Organizations) -->
      <section v-if="identitySubTab === 'organizations'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <Building2 :size="16" class="header-icon" />
            <h2>组织</h2>
            <span class="badge">{{ organizations.length }}</span>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="orgSearch"
                placeholder="搜索组织名称 / 租户标识..."
                class="search-input"
              />
              <button
                v-if="orgSearch"
                class="clear-search-btn"
                @click="orgSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateOrg = true"
            >
              <Plus :size="13" />新建组织
            </button>
          </div>
        </div>

        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 160px">组织名称</th>
                <th style="min-width: 140px">租户标识</th>
                <th style="width: 100px; text-align: center">租户类型</th>
                <th style="width: 150px">创建时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedOrganizations"
                :key="item.tenant_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + orgsPagination.offset }}
                </td>
                <td>
                  <strong>{{ item.display_name }}</strong>
                </td>
                <td class="mono muted-id">{{ item.tenant_id }}</td>
                <td class="text-center">
                  <span
                    class="badge"
                    :class="
                      item.tenant_id === 'default'
                        ? 'primary-soft'
                        : 'ghost-badge'
                    "
                  >
                    {{
                      item.tenant_id === "default" ? "默认租户" : "自定义租户"
                    }}
                  </span>
                </td>
                <td class="muted">{{ formatTime(item.created_at) }}</td>
              </tr>
              <tr v-if="!filteredOrganizations.length">
                <td colspan="5" class="empty">
                  {{
                    organizations.length
                      ? "未找到符合条件的组织"
                      : "暂无组织信息"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredOrganizations.length"
          :total="filteredOrganizations.length"
          :offset="orgsPagination.offset"
          :page-size="orgsPagination.pageSize"
          :page-size-options="[10, 20, 50]"
          @update:offset="orgsPagination.offset = $event"
          @update:page-size="orgsPagination.pageSize = $event"
        />
      </section>

      <!-- 子视图 2：项目 (Projects) -->
      <section v-else-if="identitySubTab === 'projects'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <FolderGit2 :size="16" class="header-icon" />
            <h2>项目</h2>
            <span class="badge">{{ projects.length }}</span>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="projectSearch"
                placeholder="搜索项目名称 / 项目标识..."
                class="search-input"
              />
              <button
                v-if="projectSearch"
                class="clear-search-btn"
                @click="projectSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateProject = true"
            >
              <Plus :size="13" />新建项目
            </button>
          </div>
        </div>

        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 160px">项目名称</th>
                <th style="min-width: 140px">项目标识</th>
                <th style="min-width: 120px">所属租户</th>
                <th style="width: 150px">创建时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedProjects"
                :key="item.project_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + projectsPagination.offset }}
                </td>
                <td>
                  <strong>{{ item.display_name }}</strong>
                  <span
                    v-if="item.project_id === 'default'"
                    class="badge primary-soft"
                    style="margin-left: 6px"
                    >默认项目</span
                  >
                </td>
                <td class="mono muted-id">{{ item.project_id }}</td>
                <td class="mono muted">{{ item.tenant_id }}</td>
                <td class="muted">{{ formatTime(item.created_at) }}</td>
              </tr>
              <tr v-if="!filteredProjects.length">
                <td colspan="5" class="empty">
                  {{ projects.length ? "未找到符合条件的项目" : "暂无项目" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredProjects.length"
          :total="filteredProjects.length"
          :offset="projectsPagination.offset"
          :page-size="projectsPagination.pageSize"
          :page-size-options="[10, 20, 50]"
          @update:offset="projectsPagination.offset = $event"
          @update:page-size="projectsPagination.pageSize = $event"
        />
      </section>

      <!-- 子视图 3：用户管理 (Users) -->
      <section v-else-if="identitySubTab === 'users'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <Users :size="16" class="header-icon" />
            <h2>用户</h2>
            <span class="badge">{{ users.length }}</span>
            <div class="header-sub-stats">
              <span class="sub-stat-dot active"></span>
              <span class="sub-stat-text">{{ activeUsersCount }} 启用</span>
              <span
                v-if="disabledUsersCount"
                class="sub-stat-dot disabled"
              ></span>
              <span v-if="disabledUsersCount" class="sub-stat-text muted"
                >{{ disabledUsersCount }} 停用</span
              >
            </div>
          </div>
          <div class="header-actions">
            <!-- 快速搜索与筛选 -->
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="userSearch"
                placeholder="搜索用户名 / 显示名称 / 手机号码..."
                class="search-input"
              />
              <button
                v-if="userSearch"
                class="clear-search-btn"
                @click="userSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <select v-model="userStatusFilter" class="filter-select-sm">
              <option value="all">全部状态 ({{ users.length }})</option>
              <option value="active">仅启用 ({{ activeUsersCount }})</option>
              <option value="disabled">
                仅停用 ({{ disabledUsersCount }})
              </option>
            </select>
            <button
              class="button primary tiny-btn"
              @click="showCreateUser = true"
            >
              <Plus :size="13" />新建用户
            </button>
          </div>
        </div>

        <!-- 用户表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 140px">用户名</th>
                <th style="min-width: 140px">显示名称</th>
                <th style="min-width: 130px">手机号码</th>
                <th style="min-width: 180px">项目已授角色</th>
                <th style="width: 90px; text-align: center">账号状态</th>
                <th style="width: 150px">注册时间</th>
                <th style="width: 80px; text-align: center">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in paginatedUsers" :key="item.user_id">
                <td class="muted text-center">
                  {{ index + 1 + usersPagination.offset }}
                </td>
                <td>
                  <div class="user-id-chip-row">
                    <strong class="mono">{{ item.user_id }}</strong>
                    <button
                      type="button"
                      class="copy-mini-btn"
                      :title="
                        copiedKey === item.user_id ? '已复制' : '复制用户名'
                      "
                      @click="copyToClipboard(item.user_id, item.user_id)"
                    >
                      <Check
                        v-if="copiedKey === item.user_id"
                        :size="10"
                        class="copied-check"
                      />
                      <Clipboard v-else :size="10" />
                    </button>
                  </div>
                </td>
                <td>
                  <span>{{ item.display_name || item.user_id }}</span>
                </td>
                <td>
                  <div v-if="item.phone || item.email" class="phone-cell">
                    <Phone :size="12" class="muted-icon" />
                    <span>{{ item.phone || item.email }}</span>
                  </div>
                  <span v-else class="muted">-</span>
                </td>
                <td>
                  <div class="role-tags-cell">
                    <span
                      v-for="role in userRolesMap.get(item.user_id) || []"
                      :key="role.role_id"
                      class="badge role-pill"
                      :title="role.scopes.map(labelScope).join('、')"
                    >
                      <Shield :size="10" />
                      {{ role.display_name }}
                    </span>
                    <button
                      v-if="!userRolesMap.get(item.user_id)?.length"
                      type="button"
                      class="assign-role-btn-link"
                      title="为该用户分配项目角色"
                      @click="openAssignRole(item.user_id)"
                    >
                      <Plus :size="10" />分配角色
                    </button>
                  </div>
                </td>
                <td class="text-center">
                  <span
                    class="badge status-pill"
                    :class="item.disabled ? 'failed' : 'active'"
                  >
                    <span class="status-dot"></span>
                    {{ item.disabled ? "停用" : "启用" }}
                  </span>
                </td>
                <td class="muted">{{ formatTime(item.created_at) }}</td>
                <td class="text-center">
                  <button
                    type="button"
                    class="button secondary tiny-btn"
                    title="配置项目角色"
                    @click="openAssignRole(item.user_id)"
                  >
                    <Shield :size="11" />角色
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredUsers.length">
                <td colspan="8" class="empty">
                  {{ users.length ? "未找到符合条件的用户" : "暂无用户" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredUsers.length"
          :total="filteredUsers.length"
          :offset="usersPagination.offset"
          :page-size="usersPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="usersPagination.offset = $event"
          @update:page-size="usersPagination.pageSize = $event"
        />
      </section>

      <!-- 子视图 3：项目成员 (Memberships) -->
      <section v-else-if="identitySubTab === 'memberships'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <UserCheck :size="16" class="header-icon" />
            <h2>项目成员</h2>
            <span class="badge">{{ memberships.length }}</span>
          </div>
          <div class="header-actions">
            <!-- 搜索框 -->
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="memberSearch"
                placeholder="搜索成员主体标识 / 角色..."
                class="search-input"
              />
              <button
                v-if="memberSearch"
                class="clear-search-btn"
                @click="memberSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="
                membershipForm.principal_id = '';
                membershipForm.principal_type = 'user';
                membershipForm.role_ids = [];
                showCreateMembership = true;
              "
            >
              <Plus :size="13" />添加成员
            </button>
          </div>
        </div>

        <!-- 成员表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 160px">成员主体</th>
                <th style="width: 90px; text-align: center">主体类型</th>
                <th style="min-width: 140px">主体标识</th>
                <th style="min-width: 200px">项目已授角色</th>
                <th style="width: 80px; text-align: center">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedMemberships"
                :key="item.principal_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + membershipsPagination.offset }}
                </td>
                <td>
                  <strong>{{
                    getPrincipalDisplayName(
                      item.principal_id,
                      item.principal_type,
                    )
                  }}</strong>
                </td>
                <td class="text-center">
                  <span class="badge type-badge" :class="item.principal_type">
                    {{ item.principal_type === "user" ? "用户" : "服务账号" }}
                  </span>
                </td>
                <td class="mono muted-id">{{ item.principal_id }}</td>
                <td>
                  <div class="role-tags-cell">
                    <span
                      v-for="roleId in item.role_ids"
                      :key="roleId"
                      class="badge role-pill"
                    >
                      <Shield :size="10" />
                      {{
                        roles.find((r) => r.role_id === roleId)?.display_name ||
                        roleId
                      }}
                    </span>
                  </div>
                </td>
                <td class="text-center">
                  <button
                    type="button"
                    class="button secondary tiny-btn"
                    title="配置成员角色"
                    @click="
                      membershipForm.principal_type = item.principal_type;
                      membershipForm.principal_id = item.principal_id;
                      membershipForm.role_ids = item.role_ids.slice();
                      showCreateMembership = true;
                    "
                  >
                    <Shield :size="11" />配置
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredMemberships.length">
                <td colspan="6" class="empty">
                  {{
                    memberships.length
                      ? "未找到符合条件的项目成员"
                      : "当前项目暂无成员关联"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredMemberships.length"
          :total="filteredMemberships.length"
          :offset="membershipsPagination.offset"
          :page-size="membershipsPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="membershipsPagination.offset = $event"
          @update:page-size="membershipsPagination.pageSize = $event"
        />
      </section>

      <!-- 子视图 4：角色与权限 (Roles) -->
      <section v-else-if="identitySubTab === 'roles'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <Shield :size="16" class="header-icon" />
            <h2>角色</h2>
            <span class="badge">{{ roles.length }}</span>
          </div>
          <div class="header-actions">
            <!-- 搜索框 -->
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="roleSearch"
                placeholder="搜索角色名 / 标识 / 权限..."
                class="search-input"
              />
              <button
                v-if="roleSearch"
                class="clear-search-btn"
                @click="roleSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateRole = true"
            >
              <Plus :size="13" />新建角色
            </button>
          </div>
        </div>

        <!-- 角色表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 140px">角色名称</th>
                <th style="min-width: 130px">角色标识</th>
                <th style="min-width: 220px">权限范围</th>
                <th style="min-width: 160px">适用产品</th>
                <th style="width: 90px; text-align: center">绑定成员数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in paginatedRoles" :key="item.role_id">
                <td class="muted text-center">
                  {{ index + 1 + rolesPagination.offset }}
                </td>
                <td>
                  <strong>{{ item.display_name }}</strong>
                </td>
                <td class="mono muted-id">{{ item.role_id }}</td>
                <td>
                  <div class="role-tags-cell">
                    <span
                      v-for="scope in item.scopes"
                      :key="scope"
                      class="badge scope-pill"
                      :title="scope"
                    >
                      {{ labelScope(scope) }}
                    </span>
                  </div>
                </td>
                <td>
                  <div v-if="item.product_ids?.length" class="role-tags-cell">
                    <span
                      v-for="pid in item.product_ids"
                      :key="pid"
                      class="badge product-pill"
                    >
                      {{ labelProduct(pid) }}
                    </span>
                  </div>
                  <span v-else class="muted">全部产品</span>
                </td>
                <td class="text-center">
                  <span class="badge member-count-badge">
                    {{ getRoleMemberCount(item.role_id) }} 位成员
                  </span>
                </td>
              </tr>
              <tr v-if="!filteredRoles.length">
                <td colspan="6" class="empty">
                  {{ roles.length ? "未找到符合条件的角色" : "暂无角色定义" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredRoles.length"
          :total="filteredRoles.length"
          :offset="rolesPagination.offset"
          :page-size="rolesPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="rolesPagination.offset = $event"
          @update:page-size="rolesPagination.pageSize = $event"
        />
      </section>
    </template>

    <template v-else-if="activeTab === 'credentials'">
      <!-- 服务凭据子模块 Tab 切换栏 -->
      <div class="tabs-header-bar subtabs-bar">
        <div class="domain-tabs" role="tablist" aria-label="服务凭据子视图">
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: credentialSubTab === 'service_accounts' }"
            @click="credentialSubTab = 'service_accounts'"
          >
            <Users :size="13" />
            <span>服务账号</span>
            <span class="tab-badge">{{ serviceAccounts.length }}</span>
          </button>
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: credentialSubTab === 'api_keys' }"
            @click="credentialSubTab = 'api_keys'"
          >
            <KeyRound :size="13" />
            <span>API 密钥</span>
            <span class="tab-badge">{{ apiKeys.length }}</span>
          </button>
        </div>
      </div>

      <!-- 子视图 1：服务账号 (Service Accounts) -->
      <section v-if="credentialSubTab === 'service_accounts'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <Users :size="16" class="header-icon" />
            <h2>服务账号</h2>
            <span class="badge">{{ serviceAccounts.length }}</span>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="serviceAccountSearch"
                placeholder="搜索服务账号 / 标识 / 权限..."
                class="search-input"
              />
              <button
                v-if="serviceAccountSearch"
                class="clear-search-btn"
                @click="serviceAccountSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateServiceAccount = true"
            >
              <Plus :size="13" />新建服务账号
            </button>
          </div>
        </div>

        <!-- 服务账号数据表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 160px">服务账号</th>
                <th style="min-width: 140px">账号标识</th>
                <th style="min-width: 180px">权限范围</th>
                <th style="min-width: 140px">适用产品</th>
                <th style="width: 90px; text-align: center">账号状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedServiceAccounts"
                :key="item.service_account_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + serviceAccountsPagination.offset }}
                </td>
                <td>
                  <strong>{{ item.display_name }}</strong>
                </td>
                <td class="mono muted-id">{{ item.service_account_id }}</td>
                <td>
                  <div class="role-tags-cell">
                    <span
                      v-for="scope in item.scopes"
                      :key="scope"
                      class="badge scope-pill"
                      :title="scope"
                    >
                      {{ labelScope(scope) }}
                    </span>
                  </div>
                </td>
                <td>
                  <div v-if="item.product_ids?.length" class="role-tags-cell">
                    <span
                      v-for="pid in item.product_ids"
                      :key="pid"
                      class="badge product-pill"
                    >
                      {{ labelProduct(pid) }}
                    </span>
                  </div>
                  <span v-else class="muted">全部产品</span>
                </td>
                <td class="text-center">
                  <span
                    class="badge status-pill"
                    :class="item.disabled ? 'failed' : 'active'"
                  >
                    <span class="status-dot"></span>
                    {{ item.disabled ? "停用" : "启用" }}
                  </span>
                </td>
              </tr>
              <tr v-if="!filteredServiceAccounts.length">
                <td colspan="6" class="empty">
                  {{
                    serviceAccounts.length
                      ? "未找到符合条件的服务账号"
                      : "暂无服务账号"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredServiceAccounts.length"
          :total="filteredServiceAccounts.length"
          :offset="serviceAccountsPagination.offset"
          :page-size="serviceAccountsPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="serviceAccountsPagination.offset = $event"
          @update:page-size="serviceAccountsPagination.pageSize = $event"
        />
      </section>

      <!-- 子视图 2：API 密钥 (API Keys) -->
      <section v-else-if="credentialSubTab === 'api_keys'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <KeyRound :size="16" class="header-icon" />
            <h2>API 密钥</h2>
            <span class="badge">{{ apiKeys.length }}</span>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="apiKeySearch"
                placeholder="搜索密钥名称 / 服务账号 / 前缀..."
                class="search-input"
              />
              <button
                v-if="apiKeySearch"
                class="clear-search-btn"
                @click="apiKeySearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateApiKey = true"
            >
              <Plus :size="13" />签发 API 密钥
            </button>
          </div>
        </div>

        <!-- API 密钥数据表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 150px">密钥名称</th>
                <th style="min-width: 140px">密钥掩码</th>
                <th style="min-width: 140px">关联服务账号</th>
                <th style="min-width: 160px">权限范围</th>
                <th style="width: 150px">最后使用</th>
                <th style="width: 80px; text-align: center">状态</th>
                <th style="width: 80px; text-align: center">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in paginatedApiKeys" :key="item.key_id">
                <td class="muted text-center">
                  {{ index + 1 + apiKeysPagination.offset }}
                </td>
                <td>
                  <strong>{{ item.name }}</strong>
                </td>
                <td class="mono muted-id">{{ item.token_prefix }}••••••••</td>
                <td class="mono muted">{{ item.service_account_id }}</td>
                <td>
                  <div v-if="item.scopes.length" class="role-tags-cell">
                    <span
                      v-for="scope in item.scopes"
                      :key="scope"
                      class="badge scope-pill"
                      :title="scope"
                    >
                      {{ labelScope(scope) }}
                    </span>
                  </div>
                  <span v-else class="muted">继承账号权限</span>
                </td>
                <td class="muted">{{ formatTime(item.last_used_at) }}</td>
                <td class="text-center">
                  <span
                    class="badge status-pill"
                    :class="item.revoked_at ? 'failed' : 'active'"
                  >
                    <span class="status-dot"></span>
                    {{ item.revoked_at ? "已撤销" : "有效" }}
                  </span>
                </td>
                <td class="text-center">
                  <button
                    class="button secondary danger-btn tiny-btn"
                    title="撤销该 API 密钥"
                    :disabled="!!item.revoked_at || mutating"
                    @click="revokeApiKey(item.key_id)"
                  >
                    <ShieldOff :size="11" />撤销
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredApiKeys.length">
                <td colspan="8" class="empty">
                  {{
                    apiKeys.length
                      ? "未找到符合条件的 API 密钥"
                      : "暂无 API 密钥"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredApiKeys.length"
          :total="filteredApiKeys.length"
          :offset="apiKeysPagination.offset"
          :page-size="apiKeysPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="apiKeysPagination.offset = $event"
          @update:page-size="apiKeysPagination.pageSize = $event"
        />
      </section>
    </template>

    <template v-else-if="activeTab === 'products'">
      <section class="panel">
        <div class="panel-header">
          <div class="header-left">
            <ShieldCheck :size="16" class="header-icon" />
            <h2>项目产品授权</h2>
            <span class="badge">{{ entitlements.length }}</span>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="entitlementSearch"
                placeholder="搜索产品授权 / 项目..."
                class="search-input"
              />
              <button
                v-if="entitlementSearch"
                class="clear-search-btn"
                @click="entitlementSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateEntitlement = true"
            >
              <Plus :size="13" />配置产品授权
            </button>
          </div>
        </div>

        <!-- 产品授权数据表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 150px">产品名称</th>
                <th style="min-width: 110px">产品标识</th>
                <th style="min-width: 220px">产品职责与能力范围</th>
                <th style="min-width: 110px">所属项目</th>
                <th style="width: 100px; text-align: center">授权来源</th>
                <th style="width: 90px; text-align: center">授权状态</th>
                <th style="width: 140px">更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedEntitlements"
                :key="item.product_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + entitlementsPagination.offset }}
                </td>
                <td>
                  <strong>{{ labelProduct(item.product_id) }}</strong>
                </td>
                <td class="mono muted-id">{{ item.product_id }}</td>
                <td class="muted" :title="labelProductSummary(item.product_id)">
                  {{ labelProductSummary(item.product_id) }}
                </td>
                <td class="mono muted">{{ item.project_id }}</td>
                <td class="text-center">
                  <span class="badge ghost-badge">{{
                    labelEntitlementSource(item.source)
                  }}</span>
                </td>
                <td class="text-center">
                  <span
                    class="badge status-pill"
                    :class="item.status === 'active' ? 'active' : 'failed'"
                  >
                    <span class="status-dot"></span>
                    {{ item.status === "active" ? "启用" : "暂停" }}
                  </span>
                </td>
                <td class="muted">{{ formatTime(item.updated_at) }}</td>
              </tr>
              <tr v-if="!filteredEntitlements.length">
                <td colspan="8" class="empty">
                  {{
                    entitlements.length
                      ? "未找到符合条件的产品授权"
                      : "当前项目没有产品授权"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredEntitlements.length"
          :total="filteredEntitlements.length"
          :offset="entitlementsPagination.offset"
          :page-size="entitlementsPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="entitlementsPagination.offset = $event"
          @update:page-size="entitlementsPagination.pageSize = $event"
        />
      </section>
    </template>

    <template v-else-if="activeTab === 'events'">
      <!-- 事件回调子模块 Tab 切换栏 -->
      <div class="tabs-header-bar subtabs-bar">
        <div class="domain-tabs" role="tablist" aria-label="事件回调子视图">
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: eventSubTab === 'subscriptions' }"
            @click="eventSubTab = 'subscriptions'"
          >
            <BellPlus :size="13" />
            <span>事件回调订阅</span>
            <span class="tab-badge">{{ subscriptions.length }}</span>
          </button>
          <button
            type="button"
            class="domain-tab-btn"
            :class="{ active: eventSubTab === 'deliveries' }"
            @click="eventSubTab = 'deliveries'"
          >
            <Radio :size="13" />
            <span>投递日志</span>
            <span class="tab-badge">{{ deliveries.length }}</span>
          </button>
        </div>
      </div>

      <!-- 子视图 1：事件回调订阅 (Subscriptions) -->
      <section v-if="eventSubTab === 'subscriptions'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <BellPlus :size="16" class="header-icon" />
            <h2>事件回调订阅</h2>
            <span class="badge">{{ subscriptions.length }}</span>
          </div>
          <div class="header-actions">
            <div class="search-box">
              <Search :size="13" class="search-icon" />
              <input
                v-model="subscriptionSearch"
                placeholder="搜索订阅名称 / 端点 / URL..."
                class="search-input"
              />
              <button
                v-if="subscriptionSearch"
                class="clear-search-btn"
                @click="subscriptionSearch = ''"
              >
                <X :size="12" />
              </button>
            </div>
            <button
              class="button primary tiny-btn"
              @click="showCreateHook = true"
            >
              <Plus :size="13" />添加订阅
            </button>
          </div>
        </div>

        <!-- 订阅表格 -->
        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 150px">订阅名称</th>
                <th style="min-width: 130px">端点标识</th>
                <th style="min-width: 200px">HTTPS 回调地址</th>
                <th style="min-width: 160px">监听事件类型</th>
                <th style="width: 80px; text-align: center">状态</th>
                <th style="width: 60px; text-align: center">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedSubscriptions"
                :key="item.endpoint_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + subscriptionsPagination.offset }}
                </td>
                <td>
                  <strong>{{ item.name }}</strong>
                </td>
                <td class="mono muted-id">{{ item.endpoint_id }}</td>
                <td class="mono muted">{{ item.url }}</td>
                <td>
                  <div class="role-tags-cell">
                    <span
                      v-for="et in item.event_types"
                      :key="et"
                      class="badge event-pill"
                    >
                      {{ labelEventType(et) }}
                    </span>
                  </div>
                </td>
                <td class="text-center">
                  <span
                    class="badge status-pill"
                    :class="item.enabled ? 'active' : 'failed'"
                  >
                    <span class="status-dot"></span>
                    {{ item.enabled ? "启用" : "停用" }}
                  </span>
                </td>
                <td class="text-center">
                  <button
                    class="icon-button danger-icon"
                    title="删除订阅"
                    @click="removeHook(item.endpoint_id)"
                  >
                    <Trash2 :size="13" />
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredSubscriptions.length">
                <td colspan="7" class="empty">
                  {{
                    subscriptions.length
                      ? "未找到符合条件的回调订阅"
                      : "暂无事件回调订阅"
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredSubscriptions.length"
          :total="filteredSubscriptions.length"
          :offset="subscriptionsPagination.offset"
          :page-size="subscriptionsPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="subscriptionsPagination.offset = $event"
          @update:page-size="subscriptionsPagination.pageSize = $event"
        />
      </section>

      <!-- 子视图 2：投递日志 (Deliveries) -->
      <section v-else-if="eventSubTab === 'deliveries'" class="panel">
        <div class="panel-header">
          <div class="header-left">
            <Radio :size="16" class="header-icon" />
            <h2>投递日志</h2>
            <span class="badge">{{ deliveries.length }}</span>
          </div>
          <div class="header-actions">
            <select v-model="deliveryStatusFilter" class="filter-select-sm">
              <option value="all">
                全部投递状态 ({{ deliveries.length }})
              </option>
              <option value="delivered">仅已成功投递</option>
              <option value="dead_letter">仅死信失败</option>
              <option value="queued">仅排队重试中</option>
            </select>
          </div>
        </div>

        <div class="table-scroll">
          <table class="data-table iam-table">
            <thead>
              <tr>
                <th style="width: 48px; text-align: center">序号</th>
                <th style="min-width: 140px">事件类型</th>
                <th style="min-width: 140px">事件标识</th>
                <th style="min-width: 130px">目标端点</th>
                <th style="width: 100px; text-align: center">投递状态</th>
                <th style="width: 80px; text-align: center">尝试次数</th>
                <th style="width: 90px; text-align: center">HTTP 状态码</th>
                <th style="width: 150px">记录时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in paginatedDeliveries"
                :key="item.delivery_id"
              >
                <td class="muted text-center">
                  {{ index + 1 + deliveriesPagination.offset }}
                </td>
                <td>
                  <strong>{{ labelEventType(item.event_type) }}</strong>
                </td>
                <td class="mono muted-id">{{ item.event_id }}</td>
                <td class="mono muted">{{ item.endpoint_id }}</td>
                <td class="text-center">
                  <span
                    class="badge"
                    :class="
                      item.status === 'delivered'
                        ? 'status-pill active'
                        : item.status === 'dead_letter'
                          ? 'status-pill failed'
                          : 'ghost-badge'
                    "
                  >
                    <span class="status-dot"></span>
                    {{ labelDeliveryStatus(item.status) }}
                  </span>
                </td>
                <td class="text-center">
                  <span class="badge ghost-badge">{{ item.attempts }} 次</span>
                </td>
                <td class="text-center">
                  <span
                    v-if="item.status_code"
                    class="badge http-status-badge"
                    :class="
                      item.status_code >= 200 && item.status_code < 300
                        ? 'status-2xx'
                        : 'status-err'
                    "
                  >
                    {{ item.status_code }}
                  </span>
                  <span v-else class="muted">-</span>
                </td>
                <td class="muted">{{ formatTime(item.updated_at) }}</td>
              </tr>
              <tr v-if="!filteredDeliveries.length">
                <td colspan="8" class="empty">暂无投递记录</td>
              </tr>
            </tbody>
          </table>
        </div>
        <DataTablePagination
          v-if="filteredDeliveries.length"
          :total="filteredDeliveries.length"
          :offset="deliveriesPagination.offset"
          :page-size="deliveriesPagination.pageSize"
          :page-size-options="[10, 20, 50, 100]"
          @update:offset="deliveriesPagination.offset = $event"
          @update:page-size="deliveriesPagination.pageSize = $event"
        />
      </section>
    </template>

    <section v-else class="panel connection-settings-panel">
      <div class="panel-header">
        <div class="header-left">
          <Settings :size="16" class="header-icon" />
          <h2>浏览器连接</h2>
        </div>
        <div class="header-actions">
          <span class="badge" :class="form.apiBase ? 'primary-soft' : 'active'">
            <span class="status-dot"></span>
            {{ form.apiBase ? "自定义代理后端" : "同源默认" }}
          </span>
        </div>
      </div>

      <div class="panel-body connection-body">
        <div class="connection-form-grid">
          <label class="form-field">
            <span class="field-label">接口服务地址 (API Base)</span>
            <input
              v-model="form.apiBase"
              placeholder="例如: http://127.0.0.1:8000 (留空为同源)"
              class="field-input mono"
            />
            <small class="muted field-help"
              >若前后端分离部署，请指定 Scenara 后端服务根地址</small
            >
          </label>

          <label class="form-field">
            <span class="field-label">平台访问令牌 (认证令牌)</span>
            <div class="password-input-box">
              <input
                v-model="form.token"
                :type="showConnectionToken ? 'text' : 'password'"
                autocomplete="off"
                placeholder="输入平台根令牌或 API 密钥"
                class="field-input mono password-input"
              />
              <button
                type="button"
                class="icon-toggle-btn"
                :title="showConnectionToken ? '隐藏令牌' : '显示令牌'"
                @click="showConnectionToken = !showConnectionToken"
              >
                <EyeOff v-if="showConnectionToken" :size="14" />
                <Eye v-else :size="14" />
              </button>
            </div>
            <small class="muted field-help"
              >用于浏览器向平台发起请求时的 Authorization 头部</small
            >
          </label>

          <label class="form-field">
            <span class="field-label">租户标识 (Tenant ID)</span>
            <input
              v-model="form.tenantId"
              placeholder="default"
              class="field-input mono"
            />
          </label>

          <label class="form-field">
            <span class="field-label">项目标识 (Project ID)</span>
            <input
              v-model="form.projectId"
              placeholder="default"
              class="field-input mono"
            />
          </label>
        </div>

        <div class="connection-footer-actions">
          <button
            type="button"
            class="button secondary tiny-btn"
            @click="resetConnection"
          >
            <RotateCcw :size="13" />恢复默认设置
          </button>
          <button
            type="button"
            class="button primary tiny-btn"
            @click="applyConnection"
          >
            <Check :size="13" />应用连接设置并刷新
          </button>
        </div>
      </div>
    </section>

    <!-- ==================== 模态弹窗 1：新建组织 ==================== -->
    <div
      v-if="showCreateOrg"
      class="modal-overlay"
      @click.self="showCreateOrg = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <Building2 :size="17" class="modal-title-icon" />
            <div>
              <h3>新建组织租户</h3>
              <p>创建顶层多租户隔离组织边界</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createOrganization">
          <div class="modal-body">
            <label class="form-field">
              <span class="field-label"
                >组织显示名称 <em class="required">*</em></span
              >
              <input
                v-model="organizationForm.display_name"
                placeholder="例如: Scenara 华东研发中心"
                class="field-input"
                autofocus
              />
            </label>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateOrg = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="mutating || !organizationForm.display_name.trim()"
            >
              <Plus :size="13" />确认创建组织
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 2：新建项目 ==================== -->
    <div
      v-if="showCreateProject"
      class="modal-overlay"
      @click.self="showCreateProject = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <FolderGit2 :size="17" class="modal-title-icon" />
            <div>
              <h3>创建新多租户项目</h3>
              <p>在当前组织下创建业务工作空间与资源容器</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createProject">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >项目标识 (英文) <em class="required">*</em></span
                >
                <input
                  v-model="projectForm.project_id"
                  placeholder="例如: smart-campus"
                  class="field-input mono"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >显示名称 <em class="required">*</em></span
                >
                <input
                  v-model="projectForm.display_name"
                  placeholder="例如: 智慧园区视觉系统"
                  class="field-input"
                />
              </label>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateProject = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating ||
                !projectForm.project_id.trim() ||
                !projectForm.display_name.trim()
              "
            >
              <Plus :size="13" />确认创建项目
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 3：新建用户 ==================== -->
    <div
      v-if="showCreateUser"
      class="modal-overlay"
      @click.self="showCreateUser = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <Users :size="17" class="modal-title-icon" />
            <div>
              <h3>开通新用户账号</h3>
              <p>创建租户下用于登录与权限分配的用户账号</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createUser">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >用户名
                  <small class="muted">(登录账号，留空自动生成)</small></span
                >
                <input
                  v-model="userForm.user_id"
                  placeholder="如 operator-01"
                  class="field-input mono"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >显示名称 <em class="required">* (姓名或昵称)</em></span
                >
                <input
                  v-model="userForm.display_name"
                  placeholder="如 张三 / 运维工程师"
                  class="field-input"
                />
              </label>
            </div>
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label">手机号码</span>
                <input
                  v-model="userForm.phone"
                  type="tel"
                  placeholder="如 13800138000"
                  class="field-input"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >初始密码 <em class="required">* (至少8位)</em></span
                >
                <input
                  v-model="userForm.password"
                  type="password"
                  autocomplete="new-password"
                  placeholder="输入安全初始密码"
                  class="field-input"
                />
              </label>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateUser = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating ||
                !userForm.display_name.trim() ||
                userForm.password.length < 8
              "
            >
              <UserPlus :size="13" />确认创建用户
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 4：项目成员与角色配置 ==================== -->
    <div
      v-if="showCreateMembership"
      class="modal-overlay"
      @click.self="showCreateMembership = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <UserCheck :size="17" class="modal-title-icon" />
            <div>
              <h3>向当前项目分配成员与角色</h3>
              <p>绑定用户或服务账号至当前项目并授予角色权限</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createMembership">
          <div class="modal-body">
            <div class="form-grid-2col">
              <div class="form-field">
                <span class="field-label">主体类型</span>
                <div class="segmented-control">
                  <button
                    type="button"
                    class="seg-btn"
                    :class="{
                      active: membershipForm.principal_type === 'user',
                    }"
                    @click="membershipForm.principal_type = 'user'"
                  >
                    <Users :size="13" /> 用户
                  </button>
                  <button
                    type="button"
                    class="seg-btn"
                    :class="{
                      active:
                        membershipForm.principal_type === 'service_account',
                    }"
                    @click="membershipForm.principal_type = 'service_account'"
                  >
                    <KeyRound :size="13" /> 服务账号
                  </button>
                </div>
              </div>

              <label class="form-field">
                <span class="field-label"
                  >选择主体标识 <em class="required">*</em></span
                >
                <select
                  v-model="membershipForm.principal_id"
                  class="field-input"
                >
                  <option value="" disabled>
                    请选择{{
                      membershipForm.principal_type === "user"
                        ? "用户"
                        : "服务账号"
                    }}
                  </option>
                  <option
                    v-for="opt in principalCandidateOptions"
                    :key="opt.id"
                    :value="opt.id"
                  >
                    {{ opt.name }} ({{ opt.id }})
                  </option>
                </select>
              </label>
            </div>

            <!-- 分配角色多选药丸 -->
            <div class="form-field">
              <span class="field-label"
                >分配角色 (可多选) <em class="required">*</em></span
              >
              <div class="role-selection-pills">
                <button
                  v-for="role in roles"
                  :key="role.role_id"
                  type="button"
                  class="role-select-pill"
                  :class="{
                    active: membershipForm.role_ids.includes(role.role_id),
                  }"
                  @click="toggleMembershipRole(role.role_id)"
                >
                  <Check
                    v-if="membershipForm.role_ids.includes(role.role_id)"
                    :size="12"
                  />
                  <Shield v-else :size="12" />
                  <span>{{ role.display_name }}</span>
                </button>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateMembership = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating ||
                !membershipForm.principal_id ||
                !membershipForm.role_ids.length
              "
            >
              <Plus :size="13" />确认保存成员
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 5：新建角色与权限 ==================== -->
    <div
      v-if="showCreateRole"
      class="modal-overlay"
      @click.self="showCreateRole = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <Shield :size="17" class="modal-title-icon" />
            <div>
              <h3>定义新安全角色与权限</h3>
              <p>自定义角色权限范围及适用产品授权</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createRole">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >角色标识
                  <small class="muted">(英文标识，留空自动生成)</small></span
                >
                <input
                  v-model="roleForm.role_id"
                  placeholder="例如: role:operator"
                  class="field-input mono"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >角色显示名称 <em class="required">* (中文名称)</em></span
                >
                <input
                  v-model="roleForm.display_name"
                  placeholder="例如: 运维操作员 / 视觉审计员"
                  class="field-input"
                />
              </label>
            </div>

            <!-- 权限范围选择 -->
            <div class="form-field">
              <span class="field-label"
                >权限范围
                <em class="required">* (可点击上方快捷预设或手动输入)</em></span
              >
              <div class="scope-presets-row">
                <button
                  v-for="preset in scopePresets"
                  :key="preset.id"
                  type="button"
                  class="preset-chip"
                  :class="{
                    active: parseList(roleForm.scopes).includes(preset.id),
                  }"
                  :title="preset.summary"
                  @click="toggleScopePreset(preset.id)"
                >
                  <Check
                    v-if="parseList(roleForm.scopes).includes(preset.id)"
                    :size="11"
                  />
                  <span>{{ preset.label }}</span>
                </button>
              </div>
              <input
                v-model="roleForm.scopes"
                class="field-input mono scope-input"
                placeholder="支持逗号分隔多个权限标识，例如: iam:read, media_asset:create"
              />
            </div>

            <!-- 适用产品标签多选选择器 -->
            <div class="form-field">
              <div class="field-label-row">
                <span class="field-label"
                  >适用产品范围
                  <small class="muted"
                    >(可多选，留空默认全部产品可用)</small
                  ></span
                >
                <div class="chips-quick-actions">
                  <button
                    type="button"
                    class="link-btn"
                    @click="selectAllRoleProducts"
                  >
                    全选
                  </button>
                  <span class="divider">|</span>
                  <button
                    type="button"
                    class="link-btn"
                    @click="clearRoleProducts"
                  >
                    清空
                  </button>
                </div>
              </div>
              <div class="product-chips-grid">
                <button
                  v-for="prod in productList"
                  :key="prod.id"
                  type="button"
                  class="product-chip"
                  :class="{ active: roleForm.product_ids.includes(prod.id) }"
                  @click="toggleRoleProduct(prod.id)"
                >
                  <div class="chip-check">
                    <Check
                      v-if="roleForm.product_ids.includes(prod.id)"
                      :size="12"
                    />
                  </div>
                  <div class="chip-text">
                    <strong>{{ prod.name }}</strong>
                    <small>{{ prod.domain }}</small>
                  </div>
                </button>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateRole = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating ||
                !roleForm.display_name.trim() ||
                !parseList(roleForm.scopes).length
              "
            >
              <Plus :size="13" />确认创建角色
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 6：新建服务账号 ==================== -->
    <div
      v-if="showCreateServiceAccount"
      class="modal-overlay"
      @click.self="showCreateServiceAccount = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <Users :size="17" class="modal-title-icon" />
            <div>
              <h3>创建新系统服务账号</h3>
              <p>为自动化服务、SDK 与管道创建机机认证主体</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createServiceAccount">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >服务账号标识
                  <small class="muted">(英文标识，留空自动生成)</small></span
                >
                <input
                  v-model="serviceAccountForm.service_account_id"
                  placeholder="例如: sa-pipeline-runner"
                  class="field-input mono"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >显示名称 <em class="required">*</em></span
                >
                <input
                  v-model="serviceAccountForm.display_name"
                  placeholder="例如: 自动化流水线执行主体"
                  class="field-input"
                />
              </label>
            </div>

            <!-- 权限范围选择 -->
            <div class="form-field">
              <span class="field-label"
                >权限范围 <em class="required">* (逗号分隔)</em></span
              >
              <input
                v-model="serviceAccountForm.scopes"
                class="field-input mono"
                placeholder="逗号分隔，例如: iam:read, media_asset:create"
              />
            </div>

            <!-- 适用产品选择 -->
            <div class="form-field">
              <div class="field-label-row">
                <span class="field-label"
                  >适用产品范围
                  <small class="muted">(留空默认全部产品可用)</small></span
                >
                <div class="chips-quick-actions">
                  <button
                    type="button"
                    class="link-btn"
                    @click="selectAllServiceAccountProducts"
                  >
                    全选
                  </button>
                  <span class="divider">|</span>
                  <button
                    type="button"
                    class="link-btn"
                    @click="clearServiceAccountProducts"
                  >
                    清空
                  </button>
                </div>
              </div>
              <div class="product-chips-grid">
                <button
                  v-for="prod in productList"
                  :key="prod.id"
                  type="button"
                  class="product-chip"
                  :class="{
                    active: serviceAccountForm.product_ids.includes(prod.id),
                  }"
                  @click="toggleServiceAccountProduct(prod.id)"
                >
                  <div class="chip-check">
                    <Check
                      v-if="serviceAccountForm.product_ids.includes(prod.id)"
                      :size="12"
                    />
                  </div>
                  <div class="chip-text">
                    <strong>{{ prod.name }}</strong>
                    <small>{{ prod.domain }}</small>
                  </div>
                </button>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateServiceAccount = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating ||
                !serviceAccountForm.display_name.trim() ||
                !parseList(serviceAccountForm.scopes).length
              "
            >
              <Plus :size="13" />确认创建账号
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 7：签发 API 密钥 ==================== -->
    <div
      v-if="showCreateApiKey"
      class="modal-overlay"
      @click.self="showCreateApiKey = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <KeyRound :size="17" class="modal-title-icon" />
            <div>
              <h3>为服务账号签发新 API 密钥</h3>
              <p>生成用于 HTTP 接口认证的签名密钥凭据</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createApiKey">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >所属服务账号 <em class="required">*</em></span
                >
                <select
                  v-model="keyForm.service_account_id"
                  class="field-input"
                >
                  <option value="" disabled>选择服务账号</option>
                  <option
                    v-for="item in serviceAccounts"
                    :key="item.service_account_id"
                    :value="item.service_account_id"
                  >
                    {{ item.display_name }} ({{ item.service_account_id }})
                  </option>
                </select>
              </label>
              <label class="form-field">
                <span class="field-label"
                  >密钥描述名称 <em class="required">*</em></span
                >
                <input
                  v-model="keyForm.name"
                  placeholder="例如: 生产环境客户端凭据"
                  class="field-input"
                />
              </label>
            </div>

            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >权限范围
                  <small class="muted">(可选，留空则继承服务账号)</small></span
                >
                <input
                  v-model="keyForm.scopes"
                  class="field-input mono"
                  placeholder="留空自动继承账号权限"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >过期时间
                  <small class="muted">(可选，留空永不过期)</small></span
                >
                <input
                  v-model="keyForm.expires_at"
                  type="datetime-local"
                  class="field-input"
                />
              </label>
            </div>

            <!-- 适用产品选择 -->
            <div class="form-field">
              <div class="field-label-row">
                <span class="field-label"
                  >产品授权限制
                  <small class="muted">(可选，留空默认继承全部)</small></span
                >
                <div class="chips-quick-actions">
                  <button
                    type="button"
                    class="link-btn"
                    @click="selectAllKeyProducts"
                  >
                    全选
                  </button>
                  <span class="divider">|</span>
                  <button
                    type="button"
                    class="link-btn"
                    @click="clearKeyProducts"
                  >
                    清空
                  </button>
                </div>
              </div>
              <div class="product-chips-grid">
                <button
                  v-for="prod in productList"
                  :key="prod.id"
                  type="button"
                  class="product-chip"
                  :class="{ active: keyForm.product_ids.includes(prod.id) }"
                  @click="toggleKeyProduct(prod.id)"
                >
                  <div class="chip-check">
                    <Check
                      v-if="keyForm.product_ids.includes(prod.id)"
                      :size="12"
                    />
                  </div>
                  <div class="chip-text">
                    <strong>{{ prod.name }}</strong>
                    <small>{{ prod.domain }}</small>
                  </div>
                </button>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateApiKey = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating || !keyForm.service_account_id || !keyForm.name.trim()
              "
            >
              <KeyRound :size="13" />确认签发密钥
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 8：配置产品授权 ==================== -->
    <div
      v-if="showCreateEntitlement"
      class="modal-overlay"
      @click.self="showCreateEntitlement = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <ShieldCheck :size="17" class="modal-title-icon" />
            <div>
              <h3>保存项目产品授权</h3>
              <p>开通或调整当前项目对各视觉中枢能力与产品模块的使用权限</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createEntitlement">
          <div class="modal-body">
            <div class="form-field">
              <div class="field-label-row">
                <span class="field-label"
                  >选择授权产品 <em class="required">*</em></span
                >
                <span class="muted field-extra-info"
                  >请从平台 9 大核心产品中选择要授权的产品模块</span
                >
              </div>

              <!-- 产品可视化网格选择器 -->
              <div class="entitlement-product-grid">
                <div
                  v-for="prod in availableProducts"
                  :key="prod.id"
                  class="entitlement-product-card"
                  :class="{ active: entitlementForm.product_id === prod.id }"
                  @click="entitlementForm.product_id = prod.id"
                >
                  <div class="product-card-top">
                    <div class="product-card-title">
                      <strong>{{ prod.name }}</strong>
                      <span class="product-card-id mono"
                        >({{ prod.domain }} · {{ prod.id }})</span
                      >
                    </div>
                    <div class="product-card-radio">
                      <div
                        class="radio-circle"
                        :class="{
                          selected: entitlementForm.product_id === prod.id,
                        }"
                      >
                        <div
                          v-if="entitlementForm.product_id === prod.id"
                          class="radio-dot"
                        ></div>
                      </div>
                    </div>
                  </div>
                  <p class="product-card-summary">{{ prod.summary }}</p>
                  <div v-if="prod.scopes?.length" class="product-card-scopes">
                    <span
                      v-for="scope in prod.scopes.slice(0, 3)"
                      :key="scope"
                      class="mini-scope-tag"
                    >
                      {{ labelScopeTag(scope) }}
                    </span>
                    <span
                      v-if="prod.scopes.length > 3"
                      class="mini-scope-tag muted"
                    >
                      +{{ prod.scopes.length - 3 }} 项能力
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div class="form-grid-2col" style="margin-top: 14px">
              <label class="form-field">
                <span class="field-label"
                  >授权状态 <em class="required">*</em></span
                >
                <select v-model="entitlementForm.status" class="field-input">
                  <option value="active">启用授权 (生效中)</option>
                  <option value="suspended">暂停授权 (已停用)</option>
                </select>
              </label>

              <div
                v-if="selectedEntitlementProduct"
                class="form-field selected-preview-box"
              >
                <span class="field-label"
                  >所选产品能力范围 ({{
                    selectedEntitlementProduct.name
                  }})</span
                >
                <div class="preview-scopes-list">
                  <span
                    v-for="sc in selectedEntitlementProduct.scopes"
                    :key="sc"
                    class="badge scope-pill"
                  >
                    {{ labelScopeTag(sc) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateEntitlement = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="mutating"
            >
              <Plus :size="13" />保存授权配置
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 9：新建事件回调订阅 ==================== -->
    <div
      v-if="showCreateHook"
      class="modal-overlay"
      @click.self="showCreateHook = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <BellPlus :size="17" class="modal-title-icon" />
            <div>
              <h3>配置新事件 Webhook 回调推送</h3>
              <p>当视觉事件产生时向外部系统 HTTP 接口实时推送通知</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createHook">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >订阅名称 <em class="required">*</em></span
                >
                <input
                  v-model="hook.name"
                  placeholder="例如: 业务系统事件接收器"
                  class="field-input"
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >HTTPS 回调地址 <em class="required">*</em></span
                >
                <input
                  v-model="hook.url"
                  type="url"
                  placeholder="https://api.example.com/webhook"
                  class="field-input mono"
                />
              </label>
            </div>

            <div class="form-field">
              <span class="field-label"
                >签名密钥 (Secret) <em class="required">* (至少16位)</em></span
              >
              <div class="password-input-box">
                <input
                  v-model="hook.secret"
                  :type="showHookSecret ? 'text' : 'password'"
                  autocomplete="new-password"
                  placeholder="输入用于请求验签的安全密钥"
                  class="field-input mono password-input"
                />
                <button
                  type="button"
                  class="icon-toggle-btn"
                  :title="showHookSecret ? '隐藏密码' : '显示密码'"
                  @click="showHookSecret = !showHookSecret"
                >
                  <EyeOff v-if="showHookSecret" :size="14" />
                  <Eye v-else :size="14" />
                </button>
              </div>
            </div>

            <div class="form-field">
              <span class="field-label"
                >订阅事件类型 (可多选) <em class="required">*</em></span
              >
              <div class="event-chips-grid">
                <button
                  v-for="event in eventOptions"
                  :key="event"
                  type="button"
                  class="preset-chip"
                  :class="{ active: hook.event_types.includes(event) }"
                  @click="toggleHookEventType(event)"
                >
                  <Check v-if="hook.event_types.includes(event)" :size="11" />
                  <span>{{ labelEventType(event) }}</span>
                  <small class="mono-sub">{{ event }}</small>
                </button>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateHook = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                mutating ||
                !hook.name.trim() ||
                !hook.url.trim() ||
                hook.secret.length < 16 ||
                !hook.event_types.length
              "
            >
              <BellPlus :size="13" />确认添加订阅
            </button>
          </div>
        </form>
      </div>
    </div>

    <dialog ref="keyDialog" class="modal">
      <form method="dialog">
        <div class="modal-header">
          <div>
            <h2>API 密钥已签发</h2>
            <p>关闭后将不再显示完整密钥。</p>
          </div>
          <button class="icon-button" title="关闭"><X :size="18" /></button>
        </div>
        <label
          ><span>{{ issuedKey?.record.name }}</span
          ><input class="mono" :value="issuedKey?.api_key" readonly
        /></label>
        <div class="modal-actions">
          <button type="button" class="button secondary" @click="copyIssuedKey">
            <Check v-if="copied" :size="16" /><Clipboard v-else :size="16" />{{
              copied ? "已复制" : "复制"
            }}</button
          ><button class="button primary">完成</button>
        </div>
      </form>
    </dialog>
  </section>
</template>

<style scoped>
/* 顶部统一样式的分类 Tabs 导航条 */
.tabs-header-bar {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}

.subtabs-bar {
  display: flex;
  align-items: center;
  margin: 12px 0 14px;
}

.tab-badge {
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
.domain-tab-btn.active .tab-badge {
  background: var(--color-accent, #087682);
  color: #ffffff;
}

.domain-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
  flex-wrap: wrap;
}

.domain-tab-btn {
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

.domain-tab-btn:hover {
  color: var(--graphite, #17211f);
  background: rgba(255, 255, 255, 0.6);
}

.domain-tab-btn.active {
  color: var(--color-accent-hover, #065e67);
  background: var(--color-accent-soft, #e4f1f1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.access-panel {
  margin-top: 14px;
}

.section-gap {
  margin-top: 14px;
}

.inventory-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.iam-stats-grid {
  margin-bottom: 2px;
}

.foundation-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--line, #e2e8e6);
  border-bottom: 1px solid var(--line, #e2e8e6);
}

.foundation-meta div {
  min-width: 0;
  padding: 12px 14px;
  background: #fff;
}

.foundation-meta span,
.record-row small {
  display: block;
  color: var(--muted, #64716d);
  font-size: 11px;
}

.foundation-meta strong {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  font-size: 12.5px;
}

.capability-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  vertical-align: middle;
}

.capability-status-icon {
  flex-shrink: 0;
}
.capability-status-icon.available {
  color: var(--color-accent, #087682);
}
.capability-status-icon.planned {
  color: var(--muted, #64716d);
}
.capability-status-icon.gated {
  color: #b45309;
}

.badge.available {
  background: #e4f2e9;
  color: #226a42;
}

.badge.seed {
  background: var(--teal-soft, #e0f2fe);
  color: #08636c;
}

.badge.planned {
  background: #edf0ef;
  color: #45534f;
}

.badge.gated {
  background: #fbf0de;
  color: #8b5a14;
}

/* 头部左右布局与操作区域 */
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.header-icon {
  color: var(--color-accent, #087682);
  flex-shrink: 0;
}

.header-sub-stats {
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

.sub-stat-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.sub-stat-dot.active {
  background: #16a34a;
}
.sub-stat-dot.disabled {
  background: #94a3b8;
  margin-left: 4px;
}

.sub-stat-text {
  font-size: 11px;
  color: var(--graphite, #17211f);
  font-weight: 500;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  flex-shrink: 0;
}

.tiny-btn {
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
.collapsible-form-box {
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

.form-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  margin-bottom: 10px;
}

.form-grid-inline {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.form-grid-inline .form-field {
  flex: 1;
  margin-bottom: 0;
}

.form-grid-2col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}

.form-grid-4col {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 10px;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.field-label .required {
  color: var(--coral, #ef4444);
  font-style: normal;
  font-weight: 700;
}

.field-input {
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
.field-input:focus {
  border-color: var(--color-accent, #087682);
  box-shadow: 0 0 0 2px var(--color-accent-soft, #e4f1f1);
}

.form-action-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

select.filter-select-sm,
.filter-select-sm {
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
.iam-table {
  border-collapse: collapse !important;
}

.text-center {
  text-align: center !important;
}

.user-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  white-space: nowrap;
}

.avatar-circle {
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

.avatar-teal {
  background: #e4f1f1 !important;
  color: #065e67 !important;
  border: 1px solid rgba(8, 118, 130, 0.25) !important;
}
.avatar-blue {
  background: #eff6ff !important;
  color: #1d4ed8 !important;
  border: 1px solid #bfdbfe !important;
}
.avatar-purple {
  background: #f5f3ff !important;
  color: #6d28d9 !important;
  border: 1px solid #ddd6fe !important;
}
.avatar-amber {
  background: #fffbeb !important;
  color: #b45309 !important;
  border: 1px solid #fde68a !important;
}
.avatar-emerald {
  background: #ecfdf5 !important;
  color: #047857 !important;
  border: 1px solid #a7f3d0 !important;
}
.avatar-rose {
  background: #fff1f2 !important;
  color: #be123c !important;
  border: 1px solid #fecdd3 !important;
}

.user-cell-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.user-name {
  font-weight: 600;
  font-size: 12px;
}

.user-id-chip-row {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.phone-cell {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--graphite, #17211f);
}

.copy-mini-btn {
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
.copy-mini-btn:hover {
  opacity: 1;
  color: var(--color-accent, #087682);
  background: #eef2f1;
}

.copied-check {
  color: #16a34a;
}

.muted-id {
  font-size: 11.5px;
  color: var(--muted, #64716d);
  font-family: var(--font-mono);
}

.email-cell {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--graphite, #17211f);
}
.muted-icon {
  color: var(--muted, #64716d);
}

.role-tags-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.assign-role-btn-link {
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
.assign-role-btn-link:hover {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
}

.role-pill {
  background: #eef5f4;
  color: #17544e;
  border: 1px solid #d3e5e2;
  font-size: 10.5px;
  font-weight: 500;
  padding: 0 6px;
  gap: 3px;
}

.no-role-hint {
  font-size: 11px;
  color: #9eb0aa;
}

.status-pill {
  font-size: 10.5px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.status-pill.active {
  background: #e8f5ed;
  color: #1b6338;
}
.status-pill.failed {
  background: #fdf0ee;
  color: #a33222;
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

/* 组织与项目卡片列表 */
.org-list,
.project-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
}

.entity-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  transition: all 0.15s ease;
}
.entity-card:hover {
  border-color: var(--color-accent, #087682);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}

.entity-avatar {
  width: 34px;
  height: 34px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.org-avatar {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
}
.project-avatar {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #dcfce7;
}

.entity-info {
  flex: 1;
  min-width: 0;
}

.entity-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}
.entity-name-row strong {
  font-size: 13px;
  color: var(--graphite, #17211f);
}

.entity-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.meta-dot {
  color: var(--line-strong, #b7c2bd);
}

.primary-soft {
  background: var(--color-accent-soft, #e4f1f1);
  color: var(--color-accent-hover, #065e67);
  border: 1px solid rgba(8, 118, 130, 0.2);
  font-size: 10px;
}

.ghost-badge {
  background: #f1f4f3;
  color: var(--muted, #64716d);
  font-size: 10.5px;
}

/* 权限预设药丸与产品选择芯片 */
.scope-presets-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 6px;
}

.preset-chip {
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
.preset-chip:hover {
  background: #f5f8f7;
  border-color: #bcc6c2;
}
.preset-chip.active {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
  color: var(--color-accent-hover, #065e67);
  font-weight: 600;
}

.scope-input {
  margin-top: 2px;
}

.chips-quick-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.link-btn {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--color-accent, #087682);
  cursor: pointer;
  font-size: 11px;
}
.link-btn:hover {
  text-decoration: underline;
}

.divider {
  color: var(--line-strong, #b7c2bd);
}

.product-chips-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 12px;
}

.product-chip {
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
.product-chip:hover {
  border-color: #bcc6c2;
  background: #f8faf9;
}
.product-chip.active {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
}

.chip-check {
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
.product-chip.active .chip-check {
  border-color: var(--color-accent, #087682);
  background: var(--color-accent, #087682);
  color: #ffffff;
}

.chip-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
  flex: 1;
}
.chip-text strong {
  font-size: 12.5px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.chip-text small {
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ==================== 产品授权卡片网格选择器 (Modal 8) ==================== */
.entitlement-product-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 12px;
  padding: 2px;
  box-sizing: border-box;
}

.entitlement-product-card {
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

.entitlement-product-card:hover {
  border-color: #bcc6c2;
  background: #fafbfb;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
}

.entitlement-product-card.active {
  background: var(--color-accent-soft, #eef7f7);
  border-color: var(--color-accent, #087682);
  box-shadow: 0 0 0 1px var(--color-accent, #087682);
}

.product-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.product-card-title {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.product-card-title strong {
  font-size: 12px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.product-card-id {
  font-size: 10.5px;
  color: var(--muted, #64716d);
}

.product-card-radio {
  flex-shrink: 0;
  margin-top: 2px;
}

.product-card-radio .radio-circle {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 1.5px solid var(--line-strong, #b7c2bd);
  background: #ffffff;
  display: grid;
  place-items: center;
  transition: all 0.15s ease;
}

.product-card-radio .radio-circle.selected {
  border-color: var(--color-accent, #087682);
}

.radio-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-accent, #087682);
}

.product-card-summary {
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

.product-card-scopes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.mini-scope-tag {
  display: inline-block;
  padding: 1px 5px;
  font-size: 9.5px;
  border-radius: 3px;
  background: #edf2f1;
  color: #3b4d48;
  white-space: nowrap;
}

.mini-scope-tag.muted {
  color: var(--muted, #64716d);
  background: #f4f6f5;
}

.selected-preview-box {
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 8px 10px;
}

.preview-scopes-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

/* 角色与成员卡片清单 */
.role-card-list,
.member-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
}

.role-card-item {
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: all 0.15s ease;
}
.role-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
}

.role-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.role-title-box {
  display: flex;
  align-items: center;
  gap: 7px;
}
.role-icon {
  color: var(--color-accent, #087682);
}
.role-title-box strong {
  font-size: 13px;
}

.role-id-badge {
  font-size: 10.5px;
  color: var(--muted, #64716d);
  background: #f1f4f3;
  padding: 1px 5px;
  border-radius: 3px;
}

.member-count-badge {
  background: #edf0ef;
  color: #45534f;
  font-size: 10px;
}

.role-scopes-row,
.role-products-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.scope-pill {
  background: #f4f6f5;
  color: #2b3a36;
  border: 1px solid #e1e7e4;
  font-size: 10.5px;
}
.mono-sub {
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--muted, #64716d);
  margin-left: 3px;
}

.products-label {
  font-size: 10.5px;
  color: var(--muted, #64716d);
  font-weight: 500;
}
.product-pill {
  background: #f0f7f6;
  color: #0c6a72;
  border: 1px solid #d0e7e5;
  font-size: 10px;
}

/* 分段控制器与药丸选择 */
.segmented-control {
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

.seg-btn {
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
.seg-btn:hover {
  color: var(--graphite, #17211f);
}
.seg-btn.active {
  background: #ffffff;
  color: var(--color-accent, #087682);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.role-selection-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.role-select-pill {
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
.role-select-pill:hover {
  background: #f5f8f7;
  border-color: #bcc6c2;
}
.role-select-pill.active {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
  color: var(--color-accent-hover, #065e67);
  font-weight: 600;
}

.member-card-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  transition: all 0.15s ease;
}
.member-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
}

.member-card-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.member-card-avatar.user {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
}
.member-card-avatar.service_account {
  background: #eff6ff;
  color: #2563eb;
  border: 1px solid #dbeafe;
}

.member-card-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.member-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.member-name-row strong {
  font-size: 12.5px;
}

.type-badge.user {
  background: #e6f4f1;
  color: #0f766e;
}
.type-badge.service_account {
  background: #eff6ff;
  color: #2563eb;
}

.member-roles-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

/* 基础通用样式 */
.form-stack {
  display: grid;
  gap: 10px;
}

.inline-form {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1.4fr auto;
  gap: 10px;
  align-items: end;
  margin-bottom: 12px;
}

.record-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 36px;
  padding: 6px 0;
  border-top: 1px solid #e8ecea;
  font-size: 11.5px;
}

.record-row > div {
  min-width: 0;
}

.record-row small {
  margin-top: 2px;
  overflow-wrap: anywhere;
}

select[multiple] {
  min-height: 76px;
}

.entitlement-form {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(160px, 0.6fr) auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 12px;
}

.event-options {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 12px;
  margin: 12px 0;
}

.event-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.event-options input {
  width: 14px;
  min-height: 14px;
}

.connection-form {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr 1.5fr auto;
  gap: 12px;
  align-items: end;
}

.compact-empty {
  min-height: 90px;
}

.danger-icon {
  color: var(--coral, #ef4444);
}

.danger-btn {
  color: var(--coral, #ef4444) !important;
  border-color: rgba(239, 68, 68, 0.3) !important;
}
.danger-btn:hover {
  background: #fef2f2 !important;
  border-color: var(--coral, #ef4444) !important;
}

/* 能力清单卡片 */
.capability-main {
  min-width: 0;
}

.capability-name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.capability-status-icon {
  flex-shrink: 0;
}
.capability-status-icon.available {
  color: #16a34a;
}
.capability-status-icon.planned {
  color: #64716d;
}
.capability-status-icon.gated {
  color: #d97706;
}

.capability-gate {
  text-align: right;
}

/* 凭据与产品头像徽章 */
.sa-avatar {
  background: #eff6ff !important;
  color: #2563eb !important;
  border-color: #dbeafe !important;
}

.key-avatar {
  background: #fef3c7 !important;
  color: #d97706 !important;
  border-color: #fde68a !important;
}

.prod-avatar {
  background: #f3e8ff !important;
  color: #9333ea !important;
  border-color: #e9d5ff !important;
}

/* 密码与敏感输入切换 */
.password-input-box {
  position: relative;
  display: flex;
  align-items: center;
}

.password-input {
  width: 100%;
  padding-right: 34px !important;
}

.icon-toggle-btn {
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
.icon-toggle-btn:hover {
  color: var(--graphite, #17211f);
}

/* 事件回调芯片与药丸 */
.event-chips-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.event-pill {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
  font-size: 10px;
}

/* HTTP 状态码徽章 */
.http-status-badge {
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  font-weight: 600;
}
.http-status-badge.status-2xx {
  background: #e8f5ed;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.http-status-badge.status-err {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

/* 连接设置配置卡片 */
.connection-settings-panel {
  max-width: 860px;
}

.connection-body {
  padding: 16px 18px;
}

.connection-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 16px;
  margin-bottom: 20px;
}

.field-help {
  font-size: 10.5px;
  margin-top: 2px;
  line-height: 1.3;
}

.connection-footer-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--line, #e2e8e6);
}

/* 全局统一 28px 数据表格行高与 2px 8px 内边距、四周完整边框与单行截断 */
.table-scroll {
  overflow-x: auto;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  margin-bottom: 6px;
}

.data-table,
.iam-table {
  width: 100%;
  border-collapse: collapse !important;
  border: none !important;
  font-size: 11.5px !important;
  table-layout: auto;
}

.data-table th,
.iam-table th {
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

.data-table td,
.iam-table td {
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

.data-table tr,
.iam-table tr {
  height: 28px !important;
  max-height: 28px !important;
}

.data-table td strong,
.iam-table td strong {
  font-weight: 600;
  display: inline !important;
}

.data-table td .mono.muted,
.iam-table td .mono.muted {
  margin-left: 4px;
  display: inline !important;
  font-size: 11px;
  color: var(--muted, #64716d);
}

/* 按钮及胶囊高度严格微型化 (20px)，严禁撑高 28px 单元格行高 */
.data-table .button.tiny-btn,
.iam-table .button.tiny-btn {
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

.data-table .icon-button,
.iam-table .icon-button {
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

.data-table .badge,
.iam-table .badge,
.badge {
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

.role-tags-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.assign-role-btn-link {
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
  .inventory-grid,
  .foundation-meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .form-grid-4col {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .inline-form,
  .connection-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .event-options {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .inventory-grid,
  .foundation-meta,
  .inline-form,
  .connection-form,
  .connection-form-grid,
  .entitlement-form,
  .form-grid-2col,
  .form-grid-4col,
  .form-grid-inline {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }
  .capability-row {
    grid-template-columns: 1fr;
  }
  .capability-gate {
    text-align: left;
  }
  .capability-list {
    padding: 10px;
  }
  .event-options {
    grid-template-columns: 1fr;
  }
}

/* ==================== 模态弹窗系统样式 (Modal Dialog System) ==================== */
.modal-overlay {
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

.modal-dialog {
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

.modal-dialog.modal-dialog-md {
  width: min(780px, 95vw);
}

.modal-dialog.modal-dialog-lg {
  width: min(980px, 96vw);
}

.modal-dialog.modal-dialog-xl {
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

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
  flex-shrink: 0;
}

.modal-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title-icon {
  color: var(--color-accent, #087682);
  flex-shrink: 0;
}

.modal-title-box h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  line-height: 1.2;
}

.modal-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.3;
}

.modal-close-btn {
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
.modal-close-btn:hover {
  background: #edf2f0;
  color: var(--graphite, #17211f);
}

.modal-body {
  padding: 18px;
  overflow-y: auto;
  max-height: calc(100vh - 180px);
}

.modal-actions {
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
