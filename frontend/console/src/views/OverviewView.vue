<script setup lang="ts">
import { Play, RefreshCw } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { api, userFacingError } from "../api";
import {
  labelCapability,
  labelDomain,
  labelPipeline,
  labelPortraitAsset,
  labelPortraitAssetGate,
  labelPortraitAssetSummary,
  labelPortraitCapability,
  labelPortraitMaturity,
  labelPortraitModule,
  labelPortraitModuleGate,
  labelPortraitModuleSummary,
  labelPortraitReadiness,
  labelProduct,
  labelProductGate,
  labelProductSummary,
  labelRepository,
  labelRepositoryBoundaryRule,
  labelRepositoryContract,
  labelRepositoryGate,
  labelRepositoryLifecycle,
  labelRepositoryResponsibility,
  labelRepositorySummary,
  labelRunStatus,
} from "../labels";
import type {
  DomainManifest,
  Pipeline,
  PortraitIntelligenceStatus,
  ProductCatalogItem,
  ProductLayer,
  ProductMaturity,
  RepositoryTopology,
  RunPage,
} from "../types";

const loading = ref(false);
const error = ref("");
const runs = ref<RunPage>({ items: [], offset: 0, limit: 10, total: 0 });
const domains = ref<DomainManifest[]>([]);
const pipelines = ref<Pipeline[]>([]);
const products = ref<ProductCatalogItem[]>([]);
const repositoryTopology = ref<RepositoryTopology>({
  schema_version: "1.0",
  current_repository_id: "scenara",
  repositories: [],
  integration_contracts: [],
  boundary_rules: [],
});
const portraitIntelligence = ref<PortraitIntelligenceStatus | null>(null);

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
const productModules = computed(() =>
  products.value.filter((product) => product.layer === "product_module"),
);
const foundationProducts = computed(() =>
  products.value.filter((product) => product.layer === "foundation"),
);
const sharedProducts = computed(() =>
  products.value.filter(
    (product) =>
      product.layer === "control_plane" ||
      product.layer === "developer_surface",
  ),
);

const maturityLabels: Record<ProductMaturity, string> = {
  available: "可用",
  seed: "种子能力",
  planned: "规划中",
  gated: "门禁中",
};

const layerLabels: Record<ProductLayer, string> = {
  product_module: "产品模块",
  control_plane: "共享控制面",
  developer_surface: "开发者平台",
  foundation: "基础底座",
};

function labelMaturity(value: ProductMaturity): string {
  return maturityLabels[value];
}

function labelLayer(value: ProductLayer): string {
  return layerLabels[value];
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    [
      runs.value,
      domains.value,
      pipelines.value,
      products.value,
      repositoryTopology.value,
      portraitIntelligence.value,
    ] = await Promise.all([
      api<RunPage>("/api/v1/runs?limit=10"),
      api<DomainManifest[]>("/api/v1/domains"),
      api<Pipeline[]>("/api/v1/pipelines"),
      api<ProductCatalogItem[]>("/api/v1/platform/products"),
      api<RepositoryTopology>("/api/v1/platform/repositories"),
      api<PortraitIntelligenceStatus>("/api/v1/platform/portrait-intelligence"),
    ]);
  } catch (caught) {
    error.value = userFacingError(caught, "总览加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

function domainLabel(value: string): string {
  return (
    domains.value.find((item) => item.domain_id === value)?.display_name ||
    labelDomain(value)
  );
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>总览</h1>
        <p>最近运行、启用领域与 Scenara 产品矩阵状态。</p>
      </div>
      <div class="toolbar">
        <RouterLink class="button primary" to="/parse">
          <Play :size="16" />新建解析
        </RouterLink>
        <button class="button secondary" :disabled="loading" @click="refresh">
          <RefreshCw :size="16" />刷新
        </button>
      </div>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="stats">
      <div class="stat teal">
        <span>运行</span><strong>{{ runs.total }}</strong
        ><small>当前项目</small>
      </div>
      <div class="stat green">
        <span>活跃</span><strong>{{ activeRuns }}</strong
        ><small>队列与执行中</small>
      </div>
      <div class="stat coral">
        <span>需关注</span><strong>{{ failedRuns }}</strong
        ><small>失败或取消</small>
      </div>
      <div class="stat">
        <span>产品模块</span><strong>{{ productModules.length }}</strong
        ><small>{{ products.length }} 个目录项</small>
      </div>
    </div>

    <section class="panel product-matrix">
      <div class="panel-header">
        <h2>Scenara 产品矩阵</h2>
        <span class="badge">{{ products.length }} 项</span>
      </div>
      <div class="product-grid">
        <article
          v-for="product in productModules"
          :key="product.product_id"
          class="product-card"
        >
          <div class="product-title">
            <strong>{{ labelProduct(product.product_id) }}</strong>
            <span class="badge" :class="product.maturity">{{
              labelMaturity(product.maturity)
            }}</span>
          </div>
          <p>{{ labelProductSummary(product.product_id) }}</p>
          <small
            >{{ labelLayer(product.layer) }} ·
            {{ labelProductGate(product.product_id) }}</small
          >
        </article>
        <article
          v-for="product in foundationProducts"
          :key="product.product_id"
          class="product-card foundation"
        >
          <div class="product-title">
            <strong>{{ labelProduct(product.product_id) }}</strong>
            <span class="badge" :class="product.maturity">{{
              labelMaturity(product.maturity)
            }}</span>
          </div>
          <p>{{ labelProductSummary(product.product_id) }}</p>
          <small
            >{{ labelLayer(product.layer) }} ·
            {{ labelProductGate(product.product_id) }}</small
          >
        </article>
      </div>
      <div class="shared-row">
        <span v-for="product in sharedProducts" :key="product.product_id">
          {{ labelProduct(product.product_id) }} ·
          {{ labelLayer(product.layer) }} ·
          {{ labelMaturity(product.maturity) }}
        </span>
      </div>
    </section>

    <section v-if="portraitIntelligence" class="panel portrait-intelligence">
      <div class="panel-header">
        <div>
          <h2>人像智能基础平台</h2>
          <p>
            六大核心模块、三项战略资产与七项能力就绪度。内容反映当前成熟度意图，不代表已部署的模型质量。
          </p>
        </div>
        <span class="badge"
          >契约 {{ portraitIntelligence.schema_version }}</span
        >
      </div>

      <div class="pi-modules">
        <article
          v-for="mod in portraitIntelligence.modules"
          :key="mod.module_id"
          class="pi-module-card"
        >
          <div class="pi-card-header">
            <strong>{{ labelPortraitModule(mod.module_id) }}</strong>
            <span class="badge" :class="`pi-${mod.maturity}`">{{
              labelPortraitMaturity(mod.maturity)
            }}</span>
          </div>
          <p>{{ labelPortraitModuleSummary(mod.module_id) }}</p>
          <small class="pi-gate">{{
            labelPortraitModuleGate(mod.module_id)
          }}</small>
        </article>
      </div>

      <div class="pi-capabilities">
        <div class="pi-cap-header">
          <strong>能力就绪度</strong>
          <span class="badge">
            {{
              portraitIntelligence.capabilities.filter(
                (c) => c.readiness === "ready",
              ).length
            }}
            / {{ portraitIntelligence.capabilities.length }} 已就绪
          </span>
        </div>
        <div class="pi-cap-grid">
          <div
            v-for="cap in portraitIntelligence.capabilities"
            :key="cap.capability_id"
            class="pi-cap-row"
          >
            <span class="pi-cap-name">{{
              labelPortraitCapability(cap.capability_id)
            }}</span>
            <span class="badge" :class="`pi-${cap.readiness}`">{{
              labelPortraitReadiness(cap.readiness)
            }}</span>
          </div>
        </div>
      </div>

      <div class="pi-assets">
        <article
          v-for="asset in portraitIntelligence.assets"
          :key="asset.asset_id"
          class="pi-asset-card"
        >
          <div class="pi-card-header">
            <strong>{{ labelPortraitAsset(asset.asset_id) }}</strong>
            <span class="badge" :class="`pi-${asset.maturity}`">{{
              labelPortraitMaturity(asset.maturity)
            }}</span>
          </div>
          <p>{{ labelPortraitAssetSummary(asset.asset_id) }}</p>
          <small class="pi-gate">{{
            labelPortraitAssetGate(asset.asset_id)
          }}</small>
        </article>
      </div>
    </section>

    <section class="panel repository-topology">
      <div class="panel-header">
        <div>
          <h2>仓库拓扑</h2>
          <p>
            平台集成能力留在当前仓库，模型训练与未来数据治理按专业边界独立演进。
          </p>
        </div>
        <span class="badge">契约 {{ repositoryTopology.schema_version }}</span>
      </div>
      <div class="repository-list">
        <article
          v-for="repository in repositoryTopology.repositories"
          :key="repository.repository_id"
          class="repository-row"
          :class="{ current: repository.current_repository }"
        >
          <div class="repository-name">
            <strong>{{ labelRepository(repository.repository_id) }}</strong>
            <span class="badge" :class="repository.lifecycle">{{
              labelRepositoryLifecycle(repository.lifecycle)
            }}</span>
            <small>{{
              repository.primary_product_ids.map(labelProduct).join(" · ")
            }}</small>
          </div>
          <div class="repository-scope">
            <p>{{ labelRepositorySummary(repository.repository_id) }}</p>
            <dl>
              <dt>负责</dt>
              <dd>
                {{
                  repository.responsibilities
                    .map(labelRepositoryResponsibility)
                    .join("、")
                }}
              </dd>
              <dt>不负责</dt>
              <dd>
                {{
                  repository.excluded_responsibilities
                    .map(labelRepositoryResponsibility)
                    .join("、")
                }}
              </dd>
            </dl>
          </div>
          <div class="repository-gate">
            <span>下一道门禁</span>
            <p>{{ labelRepositoryGate(repository.repository_id) }}</p>
          </div>
        </article>
      </div>
      <div class="repository-contracts">
        <div>
          <strong>跨仓库契约</strong>
          <span
            v-for="contract in repositoryTopology.integration_contracts"
            :key="contract.contract_id"
          >
            {{ labelRepositoryContract(contract.contract_id) }}
          </span>
        </div>
        <div>
          <strong>强制边界</strong>
          <span v-for="rule in repositoryTopology.boundary_rules" :key="rule">
            {{ labelRepositoryBoundaryRule(rule) }}
          </span>
        </div>
      </div>
    </section>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h2>最近运行</h2>
          <RouterLink class="button secondary" to="/runs">队列</RouterLink>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>运行</th>
                <th>领域</th>
                <th>状态</th>
                <th>流水线</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs.items" :key="run.run_id">
                <td class="mono">
                  <RouterLink
                    :to="{ path: '/parse', query: { run: run.run_id } }"
                  >
                    {{ run.run_id }}
                  </RouterLink>
                </td>
                <td>{{ domainLabel(run.domain) }}</td>
                <td>
                  <span class="badge" :class="run.status">{{
                    labelRunStatus(run.status)
                  }}</span>
                </td>
                <td class="truncate">
                  {{ labelPipeline(run.pipeline.pipeline_id) }} ·
                  {{ run.pipeline.version }}
                </td>
                <td>{{ new Date(run.updated_at * 1000).toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!runs.items.length" class="empty">暂无运行记录</div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header"><h2>已安装领域</h2></div>
        <div class="panel-body">
          <div
            v-for="domain in domains"
            :key="domain.domain_id"
            class="domain-row"
          >
            <strong>{{ domain.display_name }}</strong>
            <span>{{
              domain.capabilities.map(labelCapability).join(" · ")
            }}</span>
          </div>
          <div v-if="!domains.length" class="empty">未读取到领域注册信息</div>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.product-matrix {
  margin-bottom: 16px;
}
.product-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}
.product-card {
  min-width: 0;
  display: grid;
  gap: 9px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--teal);
  border-radius: 5px;
  background: #fff;
}
.product-card.foundation {
  border-top-color: var(--amber);
}
.product-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.product-title strong {
  min-width: 0;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.product-card p {
  margin: 0;
  color: #45534f;
  font-size: 12px;
  line-height: 1.45;
}
.product-card small {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
}
.badge.available {
  background: #e4f2e9;
  color: #226a42;
}
.badge.seed {
  background: var(--teal-soft);
  color: #08636c;
}
.badge.planned {
  background: #edf0ef;
  color: #45534f;
}
.badge.gated {
  background: #fbf0de;
  color: #8b5a14;
}
.shared-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 16px;
}
.shared-row span {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #f7f8f8;
  color: var(--muted);
  font-size: 12px;
}

/* 人像智能面板 */
.portrait-intelligence {
  margin-bottom: 16px;
}
.portrait-intelligence .panel-header > div {
  display: grid;
  gap: 4px;
}
.portrait-intelligence .panel-header p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.pi-modules {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}
.pi-module-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid #8b6fd4;
  border-radius: 5px;
  background: #fff;
}
.pi-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.pi-card-header strong {
  min-width: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.pi-module-card p {
  margin: 0;
  color: #45534f;
  font-size: 12px;
  line-height: 1.45;
}
.pi-gate {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
}
.badge.pi-available {
  background: #e4f2e9;
  color: #226a42;
}
.badge.pi-partial {
  background: #e8f4fd;
  color: #1a5a8b;
}
.badge.pi-seed {
  background: var(--teal-soft);
  color: #08636c;
}
.badge.pi-planned {
  background: #edf0ef;
  color: #45534f;
}
.badge.pi-external {
  background: #f3f0f9;
  color: #6b4fa0;
}
.badge.pi-ready {
  background: #e4f2e9;
  color: #226a42;
}
.badge.pi-fallback {
  background: #fbf0de;
  color: #8b5a14;
}
.badge.pi-placeholder {
  background: #fde8e8;
  color: #8b1a1a;
}
.badge.pi-not_configured {
  background: #edf0ef;
  color: #45534f;
}
.pi-capabilities {
  padding: 0 16px 16px;
  border-top: 1px solid var(--line);
}
.pi-cap-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 0 10px;
}
.pi-cap-header strong {
  font-size: 13px;
}
.pi-cap-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px 16px;
}
.pi-cap-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 5px 0;
  border-bottom: 1px solid var(--line);
}
.pi-cap-name {
  font-size: 12px;
  color: #25332f;
}
.pi-assets {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--line);
}
.pi-asset-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--amber);
  border-radius: 5px;
  background: #fff;
}

.repository-topology {
  margin-bottom: 16px;
}
.repository-topology .panel-header > div {
  display: grid;
  gap: 4px;
}
.repository-topology .panel-header p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.repository-list {
  padding: 0 16px;
}
.repository-row {
  display: grid;
  grid-template-columns: minmax(180px, 0.75fr) minmax(320px, 2fr) minmax(
      220px,
      1fr
    );
  gap: 20px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
}
.repository-row:last-child {
  border-bottom: 0;
}
.repository-row.current {
  box-shadow: inset 3px 0 0 var(--teal);
  padding-left: 12px;
}
.repository-name,
.repository-gate {
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 7px;
  min-width: 0;
}
.repository-name strong {
  font-size: 14px;
  overflow-wrap: anywhere;
}
.repository-name small {
  color: var(--muted);
  line-height: 1.5;
}
.repository-scope {
  min-width: 0;
}
.repository-scope > p,
.repository-gate p {
  margin: 0;
  color: #45534f;
  font-size: 12px;
  line-height: 1.55;
}
.repository-scope dl {
  display: grid;
  grid-template-columns: 48px 1fr;
  gap: 5px 8px;
  margin: 9px 0 0;
  font-size: 11px;
  line-height: 1.5;
}
.repository-scope dt {
  color: var(--muted);
  font-weight: 700;
}
.repository-scope dd {
  min-width: 0;
  margin: 0;
  color: #45534f;
  overflow-wrap: anywhere;
}
.repository-gate > span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
}
.badge.current {
  background: var(--teal-soft);
  color: #08636c;
}
.badge.external_existing {
  background: #e4f2e9;
  color: #226a42;
}
.repository-contracts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 24px;
  padding: 13px 16px;
  border-top: 1px solid var(--line);
  background: #f7f8f8;
}
.repository-contracts > div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px 12px;
  min-width: 0;
}
.repository-contracts strong {
  color: #25332f;
  font-size: 12px;
}
.repository-contracts span {
  color: var(--muted);
  font-size: 11px;
}
.domain-row {
  display: grid;
  gap: 5px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}
.domain-row:last-child {
  border-bottom: 0;
}
.domain-row span {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-size: 12px;
}
@media (max-width: 1180px) {
  .product-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pi-modules {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pi-cap-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pi-assets {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 900px) {
  .repository-row {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .repository-contracts {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 560px) {
  .product-grid {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .pi-modules {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .pi-cap-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pi-assets {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .repository-list {
    padding: 0 12px;
  }
  .repository-row.current {
    padding-left: 9px;
  }
  .repository-contracts {
    padding: 12px;
  }
}
</style>
