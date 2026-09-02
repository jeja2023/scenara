<script setup lang="ts">
import { Search, UserCheck } from "@lucide/vue";

const tabs = [
  { name: "search-query", label: "文本与人像检索", icon: Search },
  { name: "search-compare", label: "人像 1:1 比对", icon: UserCheck },
];
</script>

<template>
  <div class="search-layout">
    <div class="tabs-header-bar">
      <nav class="domain-tabs" aria-label="智能检索功能">
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
.search-layout {
  min-width: 0;
  width: 100%;
}
</style>
