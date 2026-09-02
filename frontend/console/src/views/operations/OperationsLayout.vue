<script setup lang="ts">
import { Plug, Server } from "@lucide/vue";

const tabs = [
  { name: "operations", label: "运行状态", icon: Server },
  { name: "operations-integrations", label: "集成适配器", icon: Plug },
];
</script>

<template>
  <div class="operations-layout">
    <div class="tabs-header-bar">
      <nav class="domain-tabs" aria-label="系统运维功能">
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
.operations-layout {
  min-width: 0;
  width: 100%;
}
</style>
