<script setup lang="ts">
import { Check, KeyRound, Plus, Users } from "@lucide/vue";

import type { ServiceAccount } from "../../types";
import type { ApiKeyForm, DisplayProduct, ServiceAccountForm } from "./types";

const {
  serviceAccounts,
  productList,
  mutating,
  createServiceAccount,
  createApiKey,
} = defineProps<{
  serviceAccounts: ServiceAccount[];
  productList: DisplayProduct[];
  mutating: boolean;
  createServiceAccount: () => void | Promise<void>;
  createApiKey: () => void | Promise<void>;
}>();
const showCreateServiceAccount = defineModel<boolean>(
  "showCreateServiceAccount",
  { required: true },
);
const showCreateApiKey = defineModel<boolean>("showCreateApiKey", {
  required: true,
});
const serviceAccountForm = defineModel<ServiceAccountForm>(
  "serviceAccountForm",
  { required: true },
);
const keyForm = defineModel<ApiKeyForm>("keyForm", { required: true });

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

function toggleServiceAccountProduct(productId: string): void {
  const index = serviceAccountForm.value.product_ids.indexOf(productId);
  if (index >= 0) serviceAccountForm.value.product_ids.splice(index, 1);
  else serviceAccountForm.value.product_ids.push(productId);
}

function selectAllServiceAccountProducts(): void {
  serviceAccountForm.value.product_ids = productList.map((item) => item.id);
}

function clearServiceAccountProducts(): void {
  serviceAccountForm.value.product_ids = [];
}

function toggleKeyProduct(productId: string): void {
  const index = keyForm.value.product_ids.indexOf(productId);
  if (index >= 0) keyForm.value.product_ids.splice(index, 1);
  else keyForm.value.product_ids.push(productId);
}

function selectAllKeyProducts(): void {
  keyForm.value.product_ids = productList.map((item) => item.id);
}

function clearKeyProducts(): void {
  keyForm.value.product_ids = [];
}
</script>

<template>
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
              <select v-model="keyForm.service_account_id" class="field-input">
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
</template>
