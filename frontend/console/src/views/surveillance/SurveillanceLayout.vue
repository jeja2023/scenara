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
    <nav class="surveillance-tabs" aria-label="布控预警功能">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.name"
        :to="{ name: tab.name }"
        class="surveillance-tab"
      >
        <component :is="tab.icon" :size="16" />
        <span>{{ tab.label }}</span>
      </RouterLink>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.surveillance-layout {
  min-width: 0;
}

.surveillance-tabs {
  display: flex;
  gap: var(--space-1);
  width: fit-content;
  max-width: 100%;
  margin: var(--space-5) var(--space-6) 0;
  padding: var(--space-1);
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}

.surveillance-tab {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--space-2);
  min-height: 34px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

.surveillance-tab:hover {
  color: var(--color-accent-hover);
  background: var(--color-surface-muted);
}

.surveillance-tab.router-link-exact-active {
  color: var(--color-accent-hover);
  background: var(--color-accent-soft);
}

@media (max-width: 720px) {
  .surveillance-tabs {
    width: auto;
    margin: var(--space-4) var(--space-4) 0;
  }
}
</style>
