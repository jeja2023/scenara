<script setup lang="ts">
import { Check, Eye, EyeOff, RotateCcw, Settings } from "@lucide/vue";
import { reactive, watch } from "vue";

import type { ConnectionSettings } from "../../api";

const props = defineProps<{
  form: ConnectionSettings;
  showToken: boolean;
  resetConnection: () => void;
  applyConnection: () => void;
}>();
const emit = defineEmits<{
  (event: "update:showToken", value: boolean): void;
  (event: "update:form", value: ConnectionSettings): void;
}>();
const draft = reactive<ConnectionSettings>({ ...props.form });

watch(
  () => props.form,
  (value) => Object.assign(draft, value),
  { deep: true },
);
watch(draft, (value) => emit("update:form", { ...value }), { deep: true });

function toggleToken(): void {
  emit("update:showToken", !props.showToken);
}
</script>

<template>
  <section class="panel connection-settings-panel">
    <div class="panel-header">
      <div class="header-left">
        <Settings :size="16" class="header-icon" />
        <h2>浏览器连接</h2>
      </div>
      <div class="header-actions">
        <span class="badge" :class="draft.apiBase ? 'primary-soft' : 'active'">
          <span class="status-dot"></span>
          {{ draft.apiBase ? "自定义代理后端" : "同源默认" }}
        </span>
      </div>
    </div>

    <div class="panel-body connection-body">
      <div class="connection-form-grid">
        <label class="form-field">
          <span class="field-label">接口服务地址 (API Base)</span>
          <input
            v-model="draft.apiBase"
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
              v-model="draft.token"
              :type="showToken ? 'text' : 'password'"
              autocomplete="off"
              placeholder="输入平台根令牌或 API 密钥"
              class="field-input mono password-input"
            />
            <button
              type="button"
              class="icon-toggle-btn"
              :title="showToken ? '隐藏令牌' : '显示令牌'"
              @click="toggleToken"
            >
              <EyeOff v-if="showToken" :size="14" />
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
            v-model="draft.tenantId"
            placeholder="default"
            class="field-input mono"
          />
        </label>

        <label class="form-field">
          <span class="field-label">项目标识 (Project ID)</span>
          <input
            v-model="draft.projectId"
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
</template>
