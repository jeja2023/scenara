<script setup lang="ts">
import { Box, Rocket } from "@lucide/vue";

const tabs = [
  { name: "model-catalog", label: "模型包", icon: Box },
  { name: "model-releases", label: "发布与准入", icon: Rocket },
];
</script>

<template>
  <div class="model-lifecycle-layout">
    <div class="tabs-header-bar">
      <nav class="domain-tabs" aria-label="模型生命周期功能">
        <RouterLink
          v-for="tab in tabs"
          :key="tab.name"
          :to="{ name: tab.name }"
          class="domain-tab-btn"
        >
          <component :is="tab.icon" :size="13" />
          <span>{{ tab.label }}</span>
        </RouterLink>
      </nav>
    </div>
    <RouterView />
  </div>
</template>

<style scoped>
.model-lifecycle-layout {
  min-width: 0;
  width: 100%;
}
</style>
