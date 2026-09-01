<script setup lang="ts">
import { Plus, ShieldCheck } from "@lucide/vue";

import type { DisplayProduct, EntitlementForm } from "./types";

const {
  availableProducts,
  selectedProduct,
  labelScopeTag,
  mutating,
  createEntitlement,
} = defineProps<{
  availableProducts: DisplayProduct[];
  selectedProduct: DisplayProduct | undefined;
  labelScopeTag: (scope: string) => string;
  mutating: boolean;
  createEntitlement: () => void | Promise<void>;
}>();
const showCreateEntitlement = defineModel<boolean>("showCreateEntitlement", {
  required: true,
});
const entitlementForm = defineModel<EntitlementForm>("entitlementForm", {
  required: true,
});
</script>

<template>
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

            <div v-if="selectedProduct" class="form-field selected-preview-box">
              <span class="field-label"
                >所选产品能力范围 ({{ selectedProduct.name }})</span
              >
              <div class="preview-scopes-list">
                <span
                  v-for="sc in selectedProduct.scopes"
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
</template>
