<script setup lang="ts">
import {
  Activity,
  AlertCircle,
  FileText,
  Layers,
  Play,
  ScanFace,
  Sparkles,
} from "@lucide/vue";
import { computed, onMounted, ref, type Component } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import {
  labelDomain,
  labelMediaKind,
  labelPipeline,
  labelRunStatus,
} from "../labels";
import DataTable from "../components/DataTable.vue";
import type {
  DomainManifest,
  Pipeline,
  Run,
  RunPage,
  TableColumn,
} from "../types";

const overviewRunColumns: TableColumn<Run>[] = [
  { key: "run_id", label: "任务标识", class: "mono" },
  { key: "domain", label: "领域" },
  { key: "pipeline", label: "流水线", class: "truncate" },
  { key: "status", label: "状态" },
  { key: "updated_at", label: "更新时间", class: "muted" },
];

const loading = ref(false);
const error = ref("");
const runs = ref<RunPage>({ items: [], offset: 0, limit: 10, total: 0 });
const domains = ref<DomainManifest[]>([]);
const pipelines = ref<Pipeline[]>([]);

const activeRuns = computed(
  () =>
    runs.value.items.filter((run) =>
      ["queued", "running", "pausing", "paused"].includes(run.status),
    ).length,
);
const failedRuns = computed(
  () =>
    runs.value.items.filter((run) =>
      ["failed", "cancelled"].includes(run.status),
    ).length,
);
const capabilityCount = computed(() =>
  domains.value.reduce(
    (total, domain) => total + domain.capabilities.length,
    0,
  ),
);

const domainIconsMap: Record<string, Component> = {
  portrait: ScanFace,
  ocr: FileText,
  behavior: Activity,
  fashion: Sparkles,
};

function domainIcon(domainId: string): Component {
  return domainIconsMap[domainId] || ScanFace;
}

function domainLabel(value: string): string {
  return (
    domains.value.find((item) => item.domain_id === value)?.display_name ||
    labelDomain(value)
  );
}

function domainPipelineCount(domainId: string): number {
  return pipelines.value.filter((pipeline) => pipeline.domain === domainId)
    .length;
}

function domainWorkspacePath(domainId: string): string {
  return `/parse/${encodeURIComponent(domainId)}`;
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    [runs.value, domains.value, pipelines.value] = await Promise.all([
      api<RunPage>("/api/v1/runs?limit=10"),
      api<DomainManifest[]>("/api/v1/domains"),
      api<Pipeline[]>("/api/v1/pipelines"),
    ]);
  } catch (caught) {
    error.value = userFacingError(caught, "总览加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page overview-page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">总任务运行</span>
          <div class="stat-icon-badge"><Activity :size="15" /></div>
        </div>
        <div class="stat-value">{{ runs.total }}</div>
        <div class="stat-desc">历史与当前处理总数</div>
      </div>
      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">活跃队列</span>
          <div class="stat-icon-badge"><Play :size="15" /></div>
        </div>
        <div class="stat-value">{{ activeRuns }}</div>
        <div class="stat-desc">排队与并发执行中</div>
      </div>
      <div class="stat coral">
        <div class="stat-top-row">
          <span class="stat-title">异常与关注</span>
          <div class="stat-icon-badge"><AlertCircle :size="15" /></div>
        </div>
        <div class="stat-value">{{ failedRuns }}</div>
        <div class="stat-desc">失败或已取消任务</div>
      </div>
      <div class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">已安装能力</span>
          <div class="stat-icon-badge"><Layers :size="15" /></div>
        </div>
        <div class="stat-value">{{ domains.length }} 个领域</div>
        <div class="stat-desc">
          {{ capabilityCount }} 项已声明能力 · {{ pipelines.length }} 条流水线
        </div>
      </div>
    </div>

    <section class="panel domains-panel">
      <div class="panel-header">
        <div>
          <h2>领域与工作区</h2>
          <p>仅展示服务端已安装领域及其声明的能力和流水线。</p>
        </div>
        <RouterLink class="button secondary" to="/capabilities">
          查看能力详情
        </RouterLink>
      </div>
      <div class="domain-summary-grid">
        <article
          v-for="domain in domains"
          :key="domain.domain_id"
          class="domain-summary-card"
        >
          <div class="domain-summary-title">
            <component :is="domainIcon(domain.domain_id)" :size="17" />
            <strong>{{ domain.display_name }}</strong>
          </div>
          <p>{{ domain.description || "该领域暂未提供说明。" }}</p>
          <div class="domain-summary-meta">
            <span>{{ domain.capabilities.length }} 项声明能力</span>
            <span>{{ domainPipelineCount(domain.domain_id) }} 条流水线</span>
          </div>
          <div class="domain-summary-kinds">
            <span v-for="kind in domain.supported_media_kinds" :key="kind">
              {{ labelMediaKind(kind) }}
            </span>
          </div>
          <RouterLink
            class="button secondary"
            :to="domainWorkspacePath(domain.domain_id)"
          >
            进入工作区
          </RouterLink>
        </article>
      </div>
      <p v-if="!loading && !domains.length" class="empty">暂无已安装领域</p>
    </section>

    <section class="panel runs-panel">
      <div class="panel-header">
        <div>
          <h2>最近运行动态</h2>
          <p>实时查看多领域解析任务队列与执行状态。</p>
        </div>
        <RouterLink class="button secondary" to="/runs"
          >查看全部队列</RouterLink
        >
      </div>
      <DataTable
        :columns="overviewRunColumns"
        :items="runs.items"
        :loading="loading"
        empty-text="暂无运行记录，请先进入领域工作区开始解析"
      >
        <template #run_id="{ row }">
          <RouterLink
            :to="{ path: '/parse', query: { run: row.run_id } }"
            class="run-link"
          >
            {{ row.run_id }}
          </RouterLink>
        </template>
        <template #domain="{ row }">
          <span class="domain-tag">
            <component :is="domainIcon(row.domain)" :size="12" />
            {{ domainLabel(row.domain) }}
          </span>
        </template>
        <template #pipeline="{ row }">
          {{ labelPipeline(row.pipeline.pipeline_id) }} ·
          {{ row.pipeline.version }}
        </template>
        <template #status="{ row }">
          <span class="badge" :class="row.status">{{
            labelRunStatus(row.status)
          }}</span>
        </template>
        <template #updated_at="{ row }">
          {{ new Date(row.updated_at * 1000).toLocaleString() }}
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style src="./overview/overview-view.css" scoped></style>
