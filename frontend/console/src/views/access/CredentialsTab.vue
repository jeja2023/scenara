<script setup lang="ts">
import { KeyRound, Plus, Search, ShieldOff, Users, X } from "@lucide/vue";

import DataTablePagination from "../../components/DataTablePagination.vue";
import { labelProduct, labelScope } from "../../labels";
import type { ApiKeyRecord, ServiceAccount } from "../../types";

const {
  serviceAccounts,
  apiKeys,
  serviceAccountItems,
  serviceAccountTotal,
  apiKeyItems,
  apiKeyTotal,
  mutating,
  revokeApiKey,
  formatTime,
} = defineProps<{
  serviceAccounts: ServiceAccount[];
  apiKeys: ApiKeyRecord[];
  serviceAccountItems: ServiceAccount[];
  serviceAccountTotal: number;
  apiKeyItems: ApiKeyRecord[];
  apiKeyTotal: number;
  mutating: boolean;
  revokeApiKey: (keyId: string) => void | Promise<void>;
  formatTime: (value: number | null | undefined) => string;
}>();
const emit = defineEmits<{
  (event: "open-service-account"): void;
  (event: "open-api-key"): void;
}>();
const credentialTab = defineModel<"service_accounts" | "api_keys">(
  "credentialTab",
  { required: true },
);
const serviceAccountSearch = defineModel<string>("serviceAccountSearch", {
  required: true,
});
const apiKeySearch = defineModel<string>("apiKeySearch", { required: true });
const serviceAccountPagination = defineModel<{
  offset: number;
  pageSize: number;
}>("serviceAccountPagination", { required: true });
const apiKeyPagination = defineModel<{ offset: number; pageSize: number }>(
  "apiKeyPagination",
  { required: true },
);
</script>

<template>
  <!-- 服务凭据子模块 Tab 切换栏 -->
  <div class="tabs-header-bar subtabs-bar">
    <div class="domain-tabs" role="tablist" aria-label="服务凭据子视图">
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: credentialTab === 'service_accounts' }"
        @click="credentialTab = 'service_accounts'"
      >
        <Users :size="13" />
        <span>服务账号</span>
        <span class="tab-badge">{{ serviceAccounts.length }}</span>
      </button>
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: credentialTab === 'api_keys' }"
        @click="credentialTab = 'api_keys'"
      >
        <KeyRound :size="13" />
        <span>API 密钥</span>
        <span class="tab-badge">{{ apiKeys.length }}</span>
      </button>
    </div>
  </div>

  <!-- 子视图 1：服务账号 (Service Accounts) -->
  <section v-if="credentialTab === 'service_accounts'" class="panel">
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
          @click="emit('open-service-account')"
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
            v-for="(item, index) in serviceAccountItems"
            :key="item.service_account_id"
          >
            <td class="muted text-center">
              {{ index + 1 + serviceAccountPagination.offset }}
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
          <tr v-if="!serviceAccountTotal">
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
      v-if="serviceAccountTotal"
      :total="serviceAccountTotal"
      :offset="serviceAccountPagination.offset"
      :page-size="serviceAccountPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="serviceAccountPagination.offset = $event"
      @update:page-size="serviceAccountPagination.pageSize = $event"
    />
  </section>

  <!-- 子视图 2：API 密钥 (API Keys) -->
  <section v-else-if="credentialTab === 'api_keys'" class="panel">
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
        <button class="button primary tiny-btn" @click="emit('open-api-key')">
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
          <tr v-for="(item, index) in apiKeyItems" :key="item.key_id">
            <td class="muted text-center">
              {{ index + 1 + apiKeyPagination.offset }}
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
          <tr v-if="!apiKeyTotal">
            <td colspan="8" class="empty">
              {{
                apiKeys.length ? "未找到符合条件的 API 密钥" : "暂无 API 密钥"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="apiKeyTotal"
      :total="apiKeyTotal"
      :offset="apiKeyPagination.offset"
      :page-size="apiKeyPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="apiKeyPagination.offset = $event"
      @update:page-size="apiKeyPagination.pageSize = $event"
    />
  </section>
</template>
