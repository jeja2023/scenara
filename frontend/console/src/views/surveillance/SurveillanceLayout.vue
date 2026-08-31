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
      <nav class="domain-tabs surveillance-tabs" aria-label="布控预警功能">
        <RouterLink
          v-for="tab in tabs"
          :key="tab.name"
          :to="{ name: tab.name }"
          class="domain-tab-btn surveillance-tab"
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
}

.tabs-header-bar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.surveillance-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
  flex-wrap: wrap;
}

.surveillance-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  font-size: 12px;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.surveillance-tab:hover {
  color: var(--graphite, #17211f);
  background: rgba(255, 255, 255, 0.6);
}

.surveillance-tab.router-link-exact-active {
  color: var(--color-accent-hover, #065e67);
  background: var(--color-accent-soft, #e4f1f1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}
</style>
