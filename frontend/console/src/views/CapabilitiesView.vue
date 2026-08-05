<script setup lang="ts">
import { ArrowRight, RefreshCw, ScanSearch } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api, userFacingError } from "../api";
import {
  labelCapability,
  labelDomainDescription,
  labelDomainDisplayName,
  labelMediaKind,
  labelPipelineDisplayName,
  labelPipelineStatus,
} from "../labels";
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
  return pipelines.value
    .filter((item) => item.domain === domainId)
    .sort((left, right) =>
      labelPipelineDisplayName(left.pipeline_id).localeCompare(
        labelPipelineDisplayName(right.pipeline_id),
        "zh-CN",
      ),
    );
}

function domainName(domain: DomainManifest): string {
  return labelDomainDisplayName(domain.domain_id, domain.display_name);
}

function domainSummary(domain: DomainManifest): string {
  return labelDomainDescription(domain.domain_id, domain.description);
}

onMounted(refresh);
</script>

<template>
  <section class="page capabilities-page">
    <div class="page-header">
      <div>
        <h1>领域与能力</h1>
        <p>查看已安装领域、支持的数据类型和可用解析流水线。</p>
        <div
          v-if="!loading"
          class="capability-summary"
          aria-label="领域能力概况"
        >
          <span
            >已安装领域 <strong>{{ orderedDomains.length }}</strong> 个</span
          >
          <span
            >可用流水线 <strong>{{ pipelines.length }}</strong> 条</span
          >
        </div>
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
              <strong>{{ domainName(domain) }}</strong>
              <span>领域契约 {{ domain.schema_version }}</span>
            </div>
          </div>
          <span class="badge active">已安装</span>
        </div>
        <p class="capability-description">
          {{ domainSummary(domain) }}
        </p>
        <div class="capability-section">
          <p class="capability-section-title">支持的数据类型</p>
          <div class="capability-meta">
            <span
              v-for="kind in domain.supported_media_kinds ?? []"
              :key="kind"
            >
              {{ labelMediaKind(kind) }}
            </span>
            <span
              v-if="!domain.supported_media_kinds?.length"
              class="muted-chip"
            >
              暂未声明支持类型
            </span>
          </div>
        </div>
        <div class="capability-section">
          <p class="capability-section-title">已启用能力</p>
          <div class="capability-list">
            <span v-for="capability in domain.capabilities" :key="capability">
              {{ labelCapability(capability) }}
            </span>
            <span v-if="!domain.capabilities.length" class="muted-chip">
              暂未声明领域能力
            </span>
          </div>
        </div>
        <div class="capability-pipelines">
          <p class="capability-section-title">可用解析流水线</p>
          <div
            v-for="pipeline in domainPipelines(domain.domain_id)"
            :key="pipeline.pipeline_id + pipeline.version"
          >
            <strong>{{
              labelPipelineDisplayName(pipeline.pipeline_id)
            }}</strong>
            <span class="pipeline-meta">
              <small>版本 {{ pipeline.version }}</small>
              <em :class="['pipeline-status', pipeline.status]">
                {{ labelPipelineStatus(pipeline.status) }}
              </em>
            </span>
          </div>
          <p
            v-if="!domainPipelines(domain.domain_id).length"
            class="capability-empty"
          >
            暂无可用解析流水线
          </p>
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
          进入{{ domainName(domain) }}工作区 <ArrowRight :size="14" />
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
.capability-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 8px;
  color: var(--muted);
  font-size: 12px;
}
.capability-summary strong {
  color: var(--ink);
}
.capability-section {
  margin-top: 12px;
}
.capability-section-title {
  margin: 0 0 7px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
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
.capability-meta .muted-chip,
.capability-list .muted-chip {
  color: var(--muted);
  background: #f4f6f5;
}
.capability-meta span {
  background: #e7f1ee;
}
.capability-list {
  margin-top: 0;
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
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}
.capability-pipelines strong {
  font-size: 12px;
  font-weight: 650;
}
.pipeline-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
}
.capability-pipelines small {
  color: var(--muted);
}
.pipeline-status {
  padding: 2px 6px;
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 10px;
  font-style: normal;
}
.pipeline-status.active,
.pipeline-status.approved,
.pipeline-status.validated {
  border-color: #9fc8bb;
  color: #17664f;
  background: #e7f1ee;
}
.capability-empty {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
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
