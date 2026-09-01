<script setup lang="ts">
import { Check, Clipboard, X } from "@lucide/vue";
import { nextTick, ref, watch } from "vue";

import type { IssuedApiKey } from "./types";

const { issuedKey, copied, copyIssuedKey } = defineProps<{
  issuedKey: IssuedApiKey | null;
  copied: boolean;
  copyIssuedKey: () => void | Promise<void>;
}>();
const dialog = ref<HTMLDialogElement | null>(null);

watch(
  () => issuedKey,
  async (value) => {
    if (value) {
      await nextTick();
      dialog.value?.showModal();
    }
  },
);
</script>

<template>
  <dialog ref="dialog" class="modal">
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
</template>
