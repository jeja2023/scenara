<script setup lang="ts">
import { BellPlus, Check, Eye, EyeOff } from "@lucide/vue";

import { labelEventType } from "../../labels";
import type { WebhookForm } from "./types";

const { eventOptions, mutating, createHook } = defineProps<{
  eventOptions: string[];
  mutating: boolean;
  createHook: () => void | Promise<void>;
}>();
const showCreateHook = defineModel<boolean>("showCreateHook", {
  required: true,
});
const showHookSecret = defineModel<boolean>("showHookSecret", {
  required: true,
});
const hook = defineModel<WebhookForm>("hook", { required: true });

function toggleHookEventType(event: string): void {
  const index = hook.value.event_types.indexOf(event);
  if (index >= 0) hook.value.event_types.splice(index, 1);
  else hook.value.event_types.push(event);
}
</script>

<template>
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
</template>
