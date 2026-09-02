<script setup lang="ts">
import {
  Activity,
  ArrowRight,
  FileText,
  ScanFace,
  Sparkles,
} from "@lucide/vue";
import { computed, onMounted, ref, type Component } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { RouterLink } from "vue-router";
import { api, userFacingError } from "../api";
import {
  labelCapability,
  labelDomainDescription,
  labelDomainDisplayName,
  labelMediaKind,
  labelOperator,
  labelPipelineDisplayName,
  labelPipelineStatus,
} from "../labels";
import type { DomainManifest, Pipeline } from "../types";

const domains = ref<DomainManifest[]>([]);
const pipelines = ref<Pipeline[]>([]);
const error = ref("");
const loading = ref(false);

const domainIconsMap: Record<string, Component> = {
  portrait: ScanFace,
  ocr: FileText,
  behavior: Activity,
  fashion: Sparkles,
};

function domainIcon(domainId: string): Component {
  return domainIconsMap[domainId] || ScanFace;
}

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
useRefresh(refresh);
</script>

<template>
  <section class="page capabilities-page">
    <div class="page-header">
      <div v-if="!loading" class="capability-summary" aria-label="领域能力概况">
        <span
          >已安装领域 <strong>{{ orderedDomains.length }}</strong> 个</span
        >
        <span
          >可用流水线 <strong>{{ pipelines.length }}</strong> 条</span
        >
      </div>
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
            <component :is="domainIcon(domain.domain_id)" :size="18" />
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
          <p class="capability-section-title">领域声明能力</p>
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
            class="pipeline-detail"
          >
            <div class="pipeline-detail-header">
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
            <small class="pipeline-nodes">
              {{
                pipeline.nodes
                  .map((node) => labelOperator(node.operator_id))
                  .join(" → ")
              }}
              · {{ pipeline.pausable ? "支持暂停" : "不支持暂停" }}
            </small>
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
.capabilities-page .page-header {
  margin-bottom: 10px;
}
.capability-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.capability-card {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: var(--radius-sm, 6px);
  background: var(--surface, #fff);
  display: flex;
  flex-direction: column;
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
  gap: 8px;
  min-width: 0;
}
.capability-card-title strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text, #17211f);
}
.capability-card-title > div {
  display: grid;
  gap: 1px;
  min-width: 0;
}
.capability-card-title span {
  color: var(--muted, #64716d);
  font-size: 10.5px;
  overflow-wrap: anywhere;
}
.capability-description {
  margin: 6px 0 8px;
  color: #4b5d58;
  font-size: 11.5px;
  line-height: 1.4;
}
.capability-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 0;
  color: var(--muted, #64716d);
  font-size: 12px;
}
.capability-summary strong {
  color: var(--color-text, #17211f);
}
.capability-section {
  margin-top: 7px;
}
.capability-section-title {
  margin: 0 0 3px;
  color: var(--color-text, #17211f);
  font-size: 11.5px;
  font-weight: 600;
}
.capability-meta,
.capability-list {
  flex-wrap: wrap;
  gap: 4px;
}
.capability-meta span,
.capability-list span {
  padding: 2px 6px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 3px;
  font-size: 10.5px;
}
.capability-meta .muted-chip,
.capability-list .muted-chip {
  color: var(--muted, #64716d);
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
  gap: 4px;
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px dashed var(--line, #e2e8e6);
}
.pipeline-detail {
  display: grid;
  gap: 2px;
}
.pipeline-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11.5px;
}
.pipeline-nodes {
  color: var(--muted, #64716d);
  line-height: 1.35;
}
.capability-pipelines strong {
  font-size: 11.5px;
  font-weight: 650;
}
.pipeline-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.capability-pipelines small {
  color: var(--muted);
  font-size: 10.5px;
}
.pipeline-status {
  padding: 1px 5px;
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 10px;
  font-style: normal;
  border-radius: 3px;
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
  font-size: 11.5px;
}
.capability-entry {
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: 10px;
  min-height: 30px;
  height: 30px;
  font-size: 12px;
  padding: 0 10px;
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
