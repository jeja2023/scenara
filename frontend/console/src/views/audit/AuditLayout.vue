<script setup lang="ts">
import { FileClock, History } from "@lucide/vue";

const tabs = [
  { name: "audit", label: "审计事件", icon: FileClock },
  { name: "audit-retention", label: "保留策略", icon: History },
];
</script>

<template>
  <div class="audit-layout">
    <div class="tabs-header-bar">
      <nav class="domain-tabs" aria-label="审计中心功能">
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
.audit-layout {
  min-width: 0;
  width: 100%;
}
</style>
