<script setup lang="ts">
import { ArrowRight, RefreshCw, ScanSearch } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api, userFacingError } from "../api";
import { labelCapability, labelMediaKind } from "../labels";
import type { DomainManifest, Pipeline } from "../types";

const domains = ref<DomainManifest[]>([]);
const pipelines = ref<Pipeline[]>([]);
const error = ref("");
const loading = ref(false);

const orderedDomains = computed(() =>
  [...domains.value].sort(
    (left, right) =>
      (left.navigation_order ?? 100) - (right.navigation_order ?? 100) ||
      left.display_name.localeCompare(right.display_name),
  ),
);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    [domains.value, pipelines.value] = await Promise.all([
      api<DomainManifest[]>("/api/v1/domains"),
      api<Pipeline[]>("/api/v1/pipelines"),
    ]);
  } catch (caught) {
    error.value = userFacingError(caught, "领域能力加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

function domainPipelines(domainId: string): Pipeline[] {
  return pipelines.value.filter((item) => item.domain === domainId);
}

onMounted(refresh);
</script>

<template>
  <section class="page capabilities-page">
    <div class="page-header">
      <div>
        <h1>领域与能力</h1>
        <p>查看已安装领域、支持的媒体类型和可用解析流水线。</p>
      </div>
      <button class="button secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" :class="{ spin: loading }" />刷新
      </button>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="capability-grid">
      <article
        v-for="domain in orderedDomains"
        :key="domain.domain_id"
        class="capability-card"
      >
        <div class="capability-card-header">
          <div class="capability-card-title">
            <ScanSearch :size="18" />
            <div>
              <strong>{{ domain.display_name }}</strong>
              <span class="mono">{{ domain.domain_id }}</span>
            </div>
          </div>
          <span class="badge active">已安装</span>
        </div>
        <p class="capability-description">
          {{ domain.description || "该领域已接入统一解析工作区。" }}
        </p>
        <div class="capability-meta">
          <span v-for="kind in domain.supported_media_kinds ?? []" :key="kind">
            {{ labelMediaKind(kind) }}
          </span>
        </div>
        <div class="capability-list">
          <span v-for="capability in domain.capabilities" :key="capability">
            {{ labelCapability(capability) }}
          </span>
        </div>
        <div class="capability-pipelines">
          <div
            v-for="pipeline in domainPipelines(domain.domain_id)"
            :key="pipeline.pipeline_id + pipeline.version"
          >
            <span>{{ pipeline.pipeline_id }}</span>
            <small>{{ pipeline.version }}</small>
          </div>
        </div>
        <RouterLink
          class="button secondary capability-entry"
          :to="
            domain.console_route || {
              path: '/parse',
              query: { domain: domain.domain_id },
            }
          "
        >
          进入解析工作区 <ArrowRight :size="14" />
        </RouterLink>
      </article>
    </div>
    <div v-if="!loading && !orderedDomains.length" class="empty">
      暂未安装可用领域
    </div>
  </section>
</template>

<style scoped>
.capability-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.capability-card {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--line);
  background: var(--surface);
}
.capability-card-header,
.capability-card-title,
.capability-meta,
.capability-list,
.capability-pipelines,
.capability-entry {
  display: flex;
  align-items: center;
}
.capability-card-header {
  justify-content: space-between;
  gap: 10px;
}
.capability-card-title {
  gap: 9px;
  min-width: 0;
}
.capability-card-title > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.capability-card-title span {
  color: var(--muted);
  font-size: 11px;
  overflow-wrap: anywhere;
}
.capability-description {
  min-height: 40px;
  margin: 14px 0;
  color: var(--muted);
  line-height: 1.6;
}
.capability-meta,
.capability-list {
  flex-wrap: wrap;
  gap: 6px;
}
.capability-meta span,
.capability-list span {
  padding: 3px 7px;
  border: 1px solid var(--line);
  font-size: 11px;
}
.capability-meta span {
  background: #e7f1ee;
}
.capability-list {
  margin-top: 9px;
}
.capability-pipelines {
  display: grid;
  gap: 6px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.capability-pipelines div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}
.capability-pipelines small {
  color: var(--muted);
}
.capability-entry {
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: 14px;
}
.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 760px) {
  .capability-grid {
    grid-template-columns: 1fr;
  }
}
</style>
