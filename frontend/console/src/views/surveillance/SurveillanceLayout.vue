<script setup lang="ts">
import { ClipboardList, ListChecks, Radio, ShieldAlert } from "@lucide/vue";

const tabs = [
  { name: "surveillance-live", label: "实时预警", icon: Radio },
  { name: "surveillance-alerts", label: "告警研判", icon: ShieldAlert },
  { name: "surveillance-tasks", label: "布控任务", icon: ClipboardList },
  { name: "surveillance-watchlists", label: "布控名单", icon: ListChecks },
];
</script>

<template>
  <div class="surveillance-layout">
    <div class="tabs-header-bar">
      <nav class="domain-tabs" aria-label="布控预警功能">
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
.surveillance-layout {
  min-width: 0;
  width: 100%;
}
</style>
