<script setup lang="ts">
import {
  BellPlus,
  Check,
  Clipboard,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldOff,
  Trash2,
  X,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
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
  labelScope,
} from "../labels";
import type {
  AccessCapabilityStatus,
  AccessFoundationStatus,
  ApiKeyRecord,
  IamSummary,
  Membership,
  Organization,
  ProductEntitlement,
  Project,
  Role,
  ServiceAccount,
  UserAccount,
  WebhookDelivery,
  WebhookSubscription,
} from "../types";

type AccessTab =
  | "foundation"
  | "identity"
  | "credentials"
  | "products"
  | "events"
  | "connection";
interface IssuedApiKey {
  record: ApiKeyRecord;
  api_key: string;
}

const productOptions = [
  "parse",
  "model",
  "data",
  "console",
  "edge",
  "sdk",
  "api",
  "flow",
  "agent",
  "search",
  "index",
];
const eventOptions = [
  "result.available",
  "run.completed",
  "run.failed",
  "run.cancelled",
];
const tabs: Array<{ id: AccessTab; label: string }> = [
  { id: "foundation", label: "访问底座" },
  { id: "identity", label: "成员与角色" },
  { id: "credentials", label: "服务凭据" },
  { id: "products", label: "产品授权" },
  { id: "events", label: "事件回调" },
  { id: "connection", label: "连接设置" },
];

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
const error = ref("");
const loading = ref(false);
const mutating = ref(false);
const issuedKey = ref<IssuedApiKey | null>(null);
const keyDialog = ref<HTMLDialogElement | null>(null);
const copied = ref(false);

const organizationForm = reactive({ display_name: "" });
const projectForm = reactive({ project_id: "", display_name: "" });
const userForm = reactive({
  user_id: "",
  display_name: "",
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

const readiness = computed(() => {
  const capabilities = foundation.value?.capabilities ?? [];
  return {
    available: capabilities.filter((item) => item.status === "available")
      .length,
    planned: capabilities.filter((item) => item.status === "planned").length,
    gated: capabilities.filter((item) => item.status === "gated").length,
  };
});

const inventory = computed(() => [
  {
    label: "组织",
    value: iam.value?.inventory.organizations ?? 0,
    detail: "租户级",
  },
  {
    label: "项目",
    value: iam.value?.inventory.projects ?? 0,
    detail: "当前租户",
  },
  { label: "用户", value: iam.value?.inventory.users ?? 0, detail: "当前租户" },
  { label: "角色", value: iam.value?.inventory.roles ?? 0, detail: "权限集合" },
  {
    label: "成员关系",
    value: iam.value?.inventory.memberships ?? 0,
    detail: "当前项目",
  },
  {
    label: "服务账号",
    value: iam.value?.inventory.service_accounts ?? 0,
    detail: "当前项目",
  },
  {
    label: "API 密钥",
    value: iam.value?.inventory.api_keys ?? 0,
    detail: "含已撤销",
  },
  {
    label: "产品授权",
    value: iam.value?.inventory.product_entitlements ?? 0,
    detail: "当前项目",
  },
]);

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
  });
}

async function createProject(): Promise<void> {
  await mutate(async () => {
    await api<Project>("/api/v1/platform/projects", {
      method: "POST",
      body: JSON.stringify(projectForm),
    });
    Object.assign(projectForm, { project_id: "", display_name: "" });
  });
}

async function createUser(): Promise<void> {
  await mutate(async () => {
    await api<UserAccount>("/api/v1/platform/users", {
      method: "POST",
      body: JSON.stringify({
        ...userForm,
        user_id: userForm.user_id || null,
        email: userForm.email || null,
        password: userForm.password || null,
      }),
    });
    Object.assign(userForm, {
      user_id: "",
      display_name: "",
      email: "",
      password: "",
    });
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
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>接入与权限</h1>
        <p>身份、权限、产品授权与事件通道。</p>
      </div>
      <button class="button secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" />刷新
      </button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="access-tabs" role="tablist" aria-label="接入管理视图">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        role="tab"
        :aria-selected="activeTab === tab.id"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <template v-if="activeTab === 'foundation'">
      <div class="inventory-grid">
        <div
          v-for="(item, index) in inventory"
          :key="item.label"
          class="stat"
          :class="{ teal: index === 0, green: index === 5, coral: index === 7 }"
        >
          <span>{{ item.label }}</span
          ><strong>{{ item.value }}</strong
          ><small>{{ item.detail }}</small>
        </div>
      </div>
      <section class="panel access-panel">
        <div class="panel-header">
          <h2>访问底座</h2>
          <span class="badge">{{
            foundation
              ? labelPolicyProvider(foundation.policy_provider)
              : "未读取"
          }}</span>
        </div>
        <div class="foundation-meta">
          <div>
            <span>认证模式</span
            ><strong>{{
              foundation ? authModeLabels[foundation.auth_mode] : "?"
            }}</strong>
          </div>
          <div>
            <span>身份来源</span
            ><strong>{{
              foundation
                ? principalSourceLabels[foundation.principal_source]
                : "?"
            }}</strong>
          </div>
          <div>
            <span>作用域</span
            ><strong
              >{{
                foundation ? labelContext(foundation.tenant_id, "租户") : "?"
              }}
              /
              {{
                foundation ? labelContext(foundation.project_id, "项目") : "?"
              }}</strong
            >
          </div>
          <div>
            <span>能力状态</span
            ><strong
              >{{ readiness.available }} 可用 · {{ readiness.planned }} 规划 ·
              {{ readiness.gated }} 门禁</strong
            >
          </div>
        </div>
        <div class="capability-list">
          <article
            v-for="item in foundation?.capabilities ?? []"
            :key="item.capability_id"
            class="capability-row"
          >
            <div>
              <strong>{{
                labelAccessCapability(item.capability_id).name
              }}</strong>
              <p>{{ labelAccessCapability(item.capability_id).summary }}</p>
            </div>
            <span class="badge" :class="item.status">{{
              statusLabels[item.status]
            }}</span>
            <small>{{
              labelAccessCapability(item.capability_id).nextGate
            }}</small>
          </article>
          <div v-if="!foundation" class="empty">未读取到访问底座状态</div>
        </div>
      </section>
    </template>

    <template v-else-if="activeTab === 'identity'">
      <div class="two-column">
        <section class="panel">
          <div class="panel-header">
            <h2>组织</h2>
            <span class="badge">{{ organizations.length }}</span>
          </div>
          <div class="panel-body form-stack">
            <label
              ><span>显示名称</span
              ><input v-model="organizationForm.display_name"
            /></label>
            <button
              class="button primary"
              :disabled="mutating || !organizationForm.display_name"
              @click="createOrganization"
            >
              <Plus :size="16" />创建组织
            </button>
            <div
              v-for="item in organizations"
              :key="item.tenant_id"
              class="record-row"
            >
              <strong>{{ item.display_name }}</strong
              ><span class="mono">{{ item.tenant_id }}</span>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header">
            <h2>项目</h2>
            <span class="badge">{{ projects.length }}</span>
          </div>
          <div class="panel-body form-stack">
            <div class="form-grid">
              <label
                ><span>项目标识</span
                ><input v-model="projectForm.project_id" /></label
              ><label
                ><span>显示名称</span><input v-model="projectForm.display_name"
              /></label>
            </div>
            <button
              class="button primary"
              :disabled="
                mutating || !projectForm.project_id || !projectForm.display_name
              "
              @click="createProject"
            >
              <Plus :size="16" />创建项目
            </button>
            <div
              v-for="item in projects"
              :key="item.project_id"
              class="record-row"
            >
              <strong>{{ item.display_name }}</strong
              ><span class="mono">{{ item.project_id }}</span>
            </div>
          </div>
        </section>
      </div>

      <section class="panel access-panel">
        <div class="panel-header">
          <h2>用户</h2>
          <span class="badge">{{ users.length }}</span>
        </div>
        <div class="panel-body inline-form">
          <label
            ><span>用户标识</span><input v-model="userForm.user_id"
          /></label>
          <label
            ><span>显示名称</span><input v-model="userForm.display_name"
          /></label>
          <label
            ><span>邮箱</span><input v-model="userForm.email" type="email"
          /></label>
          <label
            ><span>密码</span
            ><input
              v-model="userForm.password"
              type="password"
              autocomplete="new-password"
              minlength="8"
            />
          </label>
          <button
            class="button primary"
            :disabled="
              mutating || !userForm.display_name || userForm.password.length < 8
            "
            @click="createUser"
          >
            <Plus :size="16" />创建
          </button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>用户</th>
                <th>邮箱</th>
                <th>状态</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in users" :key="item.user_id">
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <strong>{{ item.display_name }}</strong>
                  <div class="mono muted">{{ item.user_id }}</div>
                </td>
                <td>{{ item.email ?? "-" }}</td>
                <td>
                  <span
                    class="badge"
                    :class="item.disabled ? 'failed' : 'active'"
                    >{{ item.disabled ? "停用" : "启用" }}</span
                  >
                </td>
                <td>{{ formatTime(item.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!users.length" class="empty compact-empty">暂无用户</div>
        </div>
      </section>

      <div class="two-column access-panel">
        <section class="panel">
          <div class="panel-header">
            <h2>角色</h2>
            <span class="badge">{{ roles.length }}</span>
          </div>
          <div class="panel-body form-stack">
            <div class="form-grid">
              <label
                ><span>角色标识</span
                ><input v-model="roleForm.role_id" /></label
              ><label
                ><span>显示名称</span><input v-model="roleForm.display_name"
              /></label>
            </div>
            <label
              ><span>权限范围</span
              ><input v-model="roleForm.scopes" class="mono"
            /></label>
            <label
              ><span>产品</span
              ><select v-model="roleForm.product_ids" multiple>
                <option v-for="id in productOptions" :key="id" :value="id">
                  {{ labelProduct(id) }}
                </option>
              </select></label
            >
            <button
              class="button primary"
              :disabled="
                mutating ||
                !roleForm.display_name ||
                !parseList(roleForm.scopes).length
              "
              @click="createRole"
            >
              <Plus :size="16" />创建角色
            </button>
            <div v-for="item in roles" :key="item.role_id" class="record-row">
              <div>
                <strong>{{ item.display_name }}</strong
                ><small>{{ item.scopes.map(labelScope).join("、") }}</small>
              </div>
              <span class="mono">{{ item.role_id }}</span>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header">
            <h2>项目成员</h2>
            <span class="badge">{{ memberships.length }}</span>
          </div>
          <div class="panel-body form-stack">
            <div class="form-grid">
              <label
                ><span>主体类型</span
                ><select v-model="membershipForm.principal_type">
                  <option value="user">用户</option>
                  <option value="service_account">服务账号</option>
                </select></label
              ><label
                ><span>主体标识</span
                ><input v-model="membershipForm.principal_id"
              /></label>
            </div>
            <label
              ><span>角色</span
              ><select v-model="membershipForm.role_ids" multiple>
                <option
                  v-for="item in roles"
                  :key="item.role_id"
                  :value="item.role_id"
                >
                  {{ item.display_name }}
                </option>
              </select></label
            >
            <button
              class="button primary"
              :disabled="
                mutating ||
                !membershipForm.principal_id ||
                !membershipForm.role_ids.length
              "
              @click="createMembership"
            >
              <Plus :size="16" />添加成员
            </button>
            <div
              v-for="item in memberships"
              :key="item.principal_id"
              class="record-row"
            >
              <div>
                <strong>{{ item.principal_id }}</strong
                ><small>{{ item.role_ids.join(", ") }}</small>
              </div>
              <span class="badge">{{
                item.principal_type === "user" ? "用户" : "服务账号"
              }}</span>
            </div>
          </div>
        </section>
      </div>
    </template>

    <template v-else-if="activeTab === 'credentials'">
      <div class="two-column">
        <section class="panel">
          <div class="panel-header"><h2>创建服务账号</h2></div>
          <div class="panel-body form-stack">
            <div class="form-grid">
              <label
                ><span>账号标识</span
                ><input
                  v-model="serviceAccountForm.service_account_id" /></label
              ><label
                ><span>显示名称</span
                ><input v-model="serviceAccountForm.display_name"
              /></label>
            </div>
            <label
              ><span>权限范围</span
              ><input v-model="serviceAccountForm.scopes" class="mono"
            /></label>
            <label
              ><span>产品</span
              ><select v-model="serviceAccountForm.product_ids" multiple>
                <option v-for="id in productOptions" :key="id" :value="id">
                  {{ labelProduct(id) }}
                </option>
              </select></label
            >
            <button
              class="button primary"
              :disabled="
                mutating ||
                !serviceAccountForm.display_name ||
                !parseList(serviceAccountForm.scopes).length
              "
              @click="createServiceAccount"
            >
              <Plus :size="16" />创建账号
            </button>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><h2>签发 API 密钥</h2></div>
          <div class="panel-body form-stack">
            <label
              ><span>服务账号</span
              ><select v-model="keyForm.service_account_id">
                <option value="" disabled>选择账号</option>
                <option
                  v-for="item in serviceAccounts"
                  :key="item.service_account_id"
                  :value="item.service_account_id"
                >
                  {{ item.display_name }}
                </option>
              </select></label
            >
            <label><span>密钥名称</span><input v-model="keyForm.name" /></label>
            <label
              ><span>权限范围</span
              ><input
                v-model="keyForm.scopes"
                class="mono"
                placeholder="继承服务账号"
            /></label>
            <div class="form-grid">
              <label
                ><span>产品</span
                ><select v-model="keyForm.product_ids" multiple>
                  <option v-for="id in productOptions" :key="id" :value="id">
                    {{ labelProduct(id) }}
                  </option>
                </select></label
              ><label
                ><span>过期时间</span
                ><input v-model="keyForm.expires_at" type="datetime-local"
              /></label>
            </div>
            <button
              class="button primary"
              :disabled="
                mutating || !keyForm.service_account_id || !keyForm.name
              "
              @click="createApiKey"
            >
              <KeyRound :size="16" />签发密钥
            </button>
          </div>
        </section>
      </div>

      <section class="panel access-panel">
        <div class="panel-header">
          <h2>服务账号</h2>
          <span class="badge">{{ serviceAccounts.length }}</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>账号</th>
                <th>权限范围</th>
                <th>产品</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in serviceAccounts"
                :key="item.service_account_id"
              >
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <strong>{{ item.display_name }}</strong>
                  <div class="mono muted">{{ item.service_account_id }}</div>
                </td>
                <td>{{ item.scopes.map(labelScope).join("、") }}</td>
                <td>
                  {{ item.product_ids.map(labelProduct).join("、") || "-" }}
                </td>
                <td>
                  <span
                    class="badge"
                    :class="item.disabled ? 'failed' : 'active'"
                    >{{ item.disabled ? "停用" : "启用" }}</span
                  >
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!serviceAccounts.length" class="empty compact-empty">
            暂无服务账号
          </div>
        </div>
      </section>

      <section class="panel access-panel">
        <div class="panel-header">
          <h2>API 密钥</h2>
          <span class="badge">{{ apiKeys.length }}</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>密钥</th>
                <th>服务账号</th>
                <th>权限范围</th>
                <th>最后使用</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in apiKeys" :key="item.key_id">
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <strong>{{ item.name }}</strong>
                  <div class="mono muted">{{ item.token_prefix }}…</div>
                </td>
                <td class="mono">{{ item.service_account_id }}</td>
                <td>{{ item.scopes.map(labelScope).join("、") }}</td>
                <td>{{ formatTime(item.last_used_at) }}</td>
                <td>
                  <span
                    class="badge"
                    :class="item.revoked_at ? 'failed' : 'active'"
                    >{{ item.revoked_at ? "已撤销" : "有效" }}</span
                  >
                </td>
                <td>
                  <button
                    class="icon-button danger-icon"
                    title="撤销 API 密钥"
                    :disabled="!!item.revoked_at || mutating"
                    @click="revokeApiKey(item.key_id)"
                  >
                    <ShieldOff :size="15" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!apiKeys.length" class="empty compact-empty">
            暂无 API 密钥
          </div>
        </div>
      </section>
    </template>

    <template v-else-if="activeTab === 'products'">
      <section class="panel">
        <div class="panel-header">
          <h2>项目产品授权</h2>
          <span class="badge">{{ entitlements.length }}</span>
        </div>
        <div class="panel-body entitlement-form">
          <label
            ><span>产品</span
            ><select v-model="entitlementForm.product_id">
              <option v-for="id in productOptions" :key="id" :value="id">
                {{ labelProduct(id) }}
              </option>
            </select></label
          >
          <label
            ><span>状态</span
            ><select v-model="entitlementForm.status">
              <option value="active">启用</option>
              <option value="suspended">暂停</option>
            </select></label
          >
          <button
            class="button primary"
            :disabled="mutating"
            @click="createEntitlement"
          >
            <Plus :size="16" />保存授权
          </button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>产品</th>
                <th>项目</th>
                <th>来源</th>
                <th>状态</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in entitlements" :key="item.product_id">
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <strong>{{ labelProduct(item.product_id) }}</strong>
                </td>
                <td class="mono">{{ item.project_id }}</td>
                <td>{{ labelEntitlementSource(item.source) }}</td>
                <td>
                  <span
                    class="badge"
                    :class="item.status === 'active' ? 'active' : 'paused'"
                    >{{ item.status === "active" ? "启用" : "暂停" }}</span
                  >
                </td>
                <td>{{ formatTime(item.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!entitlements.length" class="empty">
            当前项目没有产品授权
          </div>
        </div>
      </section>
    </template>

    <template v-else-if="activeTab === 'events'">
      <section class="panel">
        <div class="panel-header"><h2>事件回调订阅</h2></div>
        <div class="panel-body">
          <div class="form-grid">
            <label><span>名称</span><input v-model="hook.name" /></label
            ><label
              ><span>HTTPS 地址</span
              ><input v-model="hook.url" type="url" /></label
            ><label class="span-2"
              ><span>签名密钥</span
              ><input
                v-model="hook.secret"
                type="password"
                autocomplete="new-password"
            /></label>
          </div>
          <div class="event-options">
            <label v-for="event in eventOptions" :key="event"
              ><input
                v-model="hook.event_types"
                type="checkbox"
                :value="event"
              />{{ labelEventType(event) }}</label
            >
          </div>
          <button
            class="button primary"
            :disabled="
              mutating ||
              !hook.name ||
              !hook.url ||
              hook.secret.length < 16 ||
              !hook.event_types.length
            "
            @click="createHook"
          >
            <BellPlus :size="16" />添加订阅
          </button>
        </div>
      </section>
      <section class="panel access-panel">
        <div class="panel-header">
          <h2>订阅</h2>
          <span class="badge">{{ subscriptions.length }}</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>名称</th>
                <th>地址</th>
                <th>事件</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in subscriptions"
                :key="item.endpoint_id"
              >
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <strong>{{ item.name }}</strong>
                  <div class="mono muted">{{ item.endpoint_id }}</div>
                </td>
                <td class="truncate">{{ item.url }}</td>
                <td>{{ item.event_types.map(labelEventType).join(" · ") }}</td>
                <td>
                  <span class="badge" :class="item.enabled ? 'active' : ''">{{
                    item.enabled ? "启用" : "停用"
                  }}</span>
                </td>
                <td>
                  <button
                    class="icon-button danger-icon"
                    title="删除订阅"
                    @click="removeHook(item.endpoint_id)"
                  >
                    <Trash2 :size="15" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!subscriptions.length" class="empty compact-empty">
            没有事件回调订阅
          </div>
        </div>
      </section>
      <section class="panel access-panel">
        <div class="panel-header">
          <h2>最近投递</h2>
          <span class="badge">{{ deliveries.length }}</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>事件</th>
                <th>订阅</th>
                <th>状态</th>
                <th>尝试</th>
                <th>HTTP 状态</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in deliveries" :key="item.delivery_id">
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <strong>{{ labelEventType(item.event_type) }}</strong>
                  <div class="mono muted">{{ item.event_id }}</div>
                </td>
                <td class="mono">{{ item.endpoint_id }}</td>
                <td>
                  <span
                    class="badge"
                    :class="
                      item.status === 'delivered'
                        ? 'completed'
                        : item.status === 'dead_letter'
                          ? 'failed'
                          : 'queued'
                    "
                    >{{ labelDeliveryStatus(item.status) }}</span
                  >
                </td>
                <td>{{ item.attempts }}</td>
                <td>{{ item.status_code ?? "-" }}</td>
                <td>{{ formatTime(item.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!deliveries.length" class="empty compact-empty">
            没有投递记录
          </div>
        </div>
      </section>
    </template>

    <section v-else class="panel">
      <div class="panel-header"><h2>浏览器连接</h2></div>
      <div class="panel-body connection-form">
        <label
          ><span>接口地址</span
          ><input v-model="form.apiBase" placeholder="同源"
        /></label>
        <label><span>租户</span><input v-model="form.tenantId" /></label>
        <label><span>项目</span><input v-model="form.projectId" /></label>
        <label
          ><span>访问令牌</span
          ><input v-model="form.token" type="password" autocomplete="off"
        /></label>
        <button class="button primary" @click="applyConnection">
          <Check :size="16" />应用
        </button>
      </div>
    </section>

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
.access-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  padding-bottom: 1px;
  overflow-x: auto;
  border-bottom: 1px solid var(--line);
}
.access-tabs button {
  flex: 0 0 auto;
  height: 38px;
  padding: 0 13px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
}
.access-tabs button.active {
  border-bottom-color: var(--teal);
  color: var(--graphite);
  font-weight: 700;
}
.access-panel {
  margin-top: 16px;
}
.inventory-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.foundation-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
  border-bottom: 1px solid var(--line);
}
.foundation-meta div {
  min-width: 0;
  padding: 14px 16px;
  background: #fff;
}
.foundation-meta span,
.record-row small {
  display: block;
  color: var(--muted);
  font-size: 11px;
}
.foundation-meta strong {
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-size: 13px;
}
.capability-list {
  display: grid;
  gap: 10px;
  padding: 16px;
}
.capability-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(220px, 0.55fr);
  gap: 12px;
  align-items: start;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 5px;
}
.capability-row p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}
.capability-row small {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
}
.badge.available {
  background: #e4f2e9;
  color: #226a42;
}
.badge.seed {
  background: var(--teal-soft);
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
.form-stack {
  display: grid;
  gap: 13px;
}
.inline-form {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1.4fr auto;
  gap: 10px;
  align-items: end;
}
.record-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  padding: 9px 0;
  border-top: 1px solid #e8ecea;
  font-size: 12px;
}
.record-row > div {
  min-width: 0;
}
.record-row small {
  margin-top: 4px;
  overflow-wrap: anywhere;
}
select[multiple] {
  min-height: 92px;
}
.entitlement-form {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(160px, 0.6fr) auto;
  gap: 12px;
  align-items: end;
}
.event-options {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 12px;
  margin: 14px 0;
}
.event-options label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}
.event-options input {
  width: 15px;
  min-height: 15px;
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
  color: var(--coral);
}
@media (max-width: 1080px) {
  .inventory-grid,
  .foundation-meta {
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
  .entitlement-form {
    grid-template-columns: 1fr;
  }
  .capability-row {
    grid-template-columns: 1fr;
  }
  .capability-list {
    padding: 12px;
  }
  .event-options {
    grid-template-columns: 1fr;
  }
}
</style>
