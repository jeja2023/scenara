<script setup lang="ts">
import {
  Activity,
  AlertCircle,
  Boxes,
  FileText,
  Play,
  ScanFace,
  Sparkles,
  User,
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import {
  labelCapability,
  labelDomain,
  labelDomainDescription,
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
  foundation: "基础底座",
  control_plane: "控制面",
  developer_surface: "开发者界面",
};

function labelMaturity(value: ProductMaturity): string {
  return maturityLabels[value] || value;
}

function labelLayer(value: ProductLayer): string {
  return layerLabels[value] || value;
}

const domainIconsMap: Record<string, any> = {
  portrait: ScanFace,
  ocr: FileText,
  behavior: Activity,
  fashion: Sparkles,
};

function domainIcon(domainId: string) {
  return domainIconsMap[domainId] || ScanFace;
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

interface FullCapabilityItem {
  id: string;
  domain: string;
  name: string;
  readiness: "ready" | "fallback" | "placeholder";
  productionReady: boolean;
  model: string;
  detail: string;
}

const selectedDomainFilter = ref<string>("all");

const domainFilterOptions = [
  { id: "all", label: "全部领域" },
  { id: "portrait", label: "人像视觉" },
  { id: "ocr", label: "OCR 智能文档" },
  { id: "behavior", label: "行为动作" },
  { id: "fashion", label: "服饰风格" },
];

const allCapabilitiesList = computed<FullCapabilityItem[]>(() => [
  // 1. 人像视觉领域
  {
    id: "person_detection",
    domain: "portrait",
    name: "人员目标检测",
    readiness: "ready",
    productionReady: true,
    model: "models/yolov8n.onnx",
    detail: "YOLOv8 目标框定位 (640×640)",
  },
  {
    id: "body_embedding",
    domain: "portrait",
    name: "人员特征重识别",
    readiness: "ready",
    productionReady: true,
    model: "models/osnet_ibn_x1_0.onnx",
    detail: "OSNet IBN (512 维特征抽取)",
  },
  {
    id: "pose",
    domain: "portrait",
    name: "姿态估计与骨架",
    readiness: "ready",
    productionReady: true,
    model: "models/yolov8n-pose.pt",
    detail: "YOLOv8-Pose (17 点 COCO 骨架)",
  },
  {
    id: "face_detection",
    domain: "portrait",
    name: "人脸检测与定位",
    readiness: "ready",
    productionReady: true,
    model: "models/scrfd_500m.onnx",
    detail: "SCRFD 5 点人脸关键点检测 (640×640)",
  },
  {
    id: "face_embedding",
    domain: "portrait",
    name: "人脸特征提取",
    readiness: "ready",
    productionReady: true,
    model: "models/arcface.onnx",
    detail: "ArcFace MobileFaceNet (512 维特征抽取)",
  },
  {
    id: "gait",
    domain: "portrait",
    name: "步态时序特征",
    readiness: "ready",
    productionReady: true,
    model: "models/opengait_gait3d.onnx",
    detail: "OpenGait 3D 步态时序特征 (256 维)",
  },
  {
    id: "appearance",
    domain: "portrait",
    name: "服饰颜色与属性",
    readiness: "ready",
    productionReady: true,
    model: "models/attribute_reid.onnx",
    detail: "Attribute ReID 服饰与体貌特征 (256 维)",
  },

  // 2. OCR 智能文档领域
  {
    id: "text_detection",
    domain: "ocr",
    name: "文本行快速检测",
    readiness: "ready",
    productionReady: true,
    model: "models/ocr/ch_PP-OCRv4_det_infer",
    detail: "PP-OCRv4 文本定位 (轻量级 DB 算法)",
  },
  {
    id: "text_recognition",
    domain: "ocr",
    name: "多行文本高精识别",
    readiness: "ready",
    productionReady: true,
    model: "models/ocr/ch_PP-OCRv4_rec_infer",
    detail: "PP-OCRv4 中英文字符高精度识别",
  },
  {
    id: "text_orientation",
    domain: "ocr",
    name: "文字方向自适应校正",
    readiness: "ready",
    productionReady: true,
    model: "models/ocr/ch_ppocr_mobile_v2.0_cls_infer",
    detail: "文字方向角度分类与纠偏",
  },
  {
    id: "reading_order",
    domain: "ocr",
    name: "时序文本去重与追踪",
    readiness: "ready",
    productionReady: true,
    model: "Adaptive Motion Deduplication Engine",
    detail: "动静态帧差过滤与时序段去重追踪",
  },

  // 3. 行为动作识别领域
  {
    id: "action_recognition",
    domain: "behavior",
    name: "复杂行为与动作分类",
    readiness: "ready",
    productionReady: true,
    model: "YOLOv8 Pose + Behavior Rule Engine",
    detail: "吸烟、玩手机、摔倒、搏斗等 50+ 动作识别",
  },
  {
    id: "temporal_segmentation",
    domain: "behavior",
    name: "时空轨迹与行为时段切分",
    readiness: "ready",
    productionReady: true,
    model: "Behavior Spatial-Temporal Tracker",
    detail: "动作生命周期与持续时序段分析",
  },
  {
    id: "anomaly_detection",
    domain: "behavior",
    name: "异常动态行为告警",
    readiness: "ready",
    productionReady: true,
    model: "Behavior Anomaly Detector",
    detail: "越界、攀爬、聚集异常行为告警",
  },

  // 4. 服饰风格识别领域
  {
    id: "clothing_style_detection",
    domain: "fashion",
    name: "服饰风格与品类细分",
    readiness: "ready",
    productionReady: true,
    model: "Fashion Style Engine",
    detail: "JK、Lolita、汉服等二次元与时尚风格",
  },
  {
    id: "cosplay_recognition",
    domain: "fashion",
    name: "Cosplay 角色特征匹配",
    readiness: "ready",
    productionReady: true,
    model: "Cosplay Character Matcher",
    detail: "角色形象多模态特征识别",
  },
  {
    id: "accessory_detection",
    domain: "fashion",
    name: "配饰道具与局部特征检测",
    readiness: "ready",
    productionReady: true,
    model: "Accessory & Prop Detector",
    detail: "假发、道具、饰品细粒度识别",
  },
]);

const filteredCapabilities = computed(() => {
  if (selectedDomainFilter.value === "all") {
    return allCapabilitiesList.value;
  }
  return allCapabilitiesList.value.filter(
    (item) => item.domain === selectedDomainFilter.value,
  );
});

const readyCapabilitiesCount = computed(
  () => filteredCapabilities.value.filter((c) => c.productionReady).length,
);

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page overview-page">
    <div class="overview-hero">
      <div class="hero-title">
        <strong class="hero-heading">工作台总览</strong>
        <p>聚合全局核心指标与各领域最新运行动态。</p>
      </div>
      <RouterLink class="button primary overview-action" to="/parse">
        <Play :size="16" />新建解析
      </RouterLink>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="stats">
      <div class="stat teal">
        <div class="stat-header">
          <span>运行</span>
          <Activity :size="16" class="stat-icon" />
        </div>
        <strong>{{ runs.total }}</strong>
        <small>当前项目总量</small>
      </div>
      <div class="stat green">
        <div class="stat-header">
          <span>活跃</span>
          <Play :size="16" class="stat-icon" />
        </div>
        <strong>{{ activeRuns }}</strong>
        <small>队列与执行中</small>
      </div>
      <div class="stat coral">
        <div class="stat-header">
          <span>需关注</span>
          <AlertCircle :size="16" class="stat-icon" />
        </div>
        <strong>{{ failedRuns }}</strong>
        <small>失败或已取消</small>
      </div>
      <div class="stat amber">
        <div class="stat-header">
          <span>产品模块</span>
          <Boxes :size="16" class="stat-icon" />
        </div>
        <strong>{{ productModules.length }}</strong>
        <small>{{ products.length }} 个目录项</small>
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
        <div
          v-for="product in sharedProducts"
          :key="product.product_id"
          class="shared-chip"
        >
          <span class="chip-name">{{ labelProduct(product.product_id) }}</span>
          <span class="chip-layer">{{ labelLayer(product.layer) }}</span>
          <span class="badge" :class="product.maturity">{{
            labelMaturity(product.maturity)
          }}</span>
        </div>
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
          <div class="pi-cap-title-wrap">
            <strong>全领域能力就绪度矩阵</strong>
            <div class="domain-filter-tabs">
              <button
                v-for="opt in domainFilterOptions"
                :key="opt.id"
                class="domain-tab-btn"
                :class="{ active: selectedDomainFilter === opt.id }"
                @click="selectedDomainFilter = opt.id"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <span class="badge">
            {{ readyCapabilitiesCount }} / {{ filteredCapabilities.length }} 项生产就绪
          </span>
        </div>
        <div class="table-scroll">
          <table class="data-table bordered-table pi-cap-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th style="width: 100px">领域</th>
                <th>核心能力</th>
                <th>就绪状态</th>
                <th>生产支持</th>
                <th>装载模型与引擎配置</th>
                <th>能力特性说明</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(cap, index) in filteredCapabilities"
                :key="cap.id"
              >
                <td class="muted">{{ index + 1 }}</td>
                <td>
                  <span class="domain-pill" :class="cap.domain">
                    {{ domainLabel(cap.domain) }}
                  </span>
                </td>
                <td class="pi-cap-name">
                  <strong>{{ cap.name }}</strong>
                </td>
                <td>
                  <span class="badge" :class="`pi-${cap.readiness}`">
                    {{ cap.readiness === "ready" ? "已就绪" : "开发替代" }}
                  </span>
                </td>
                <td>
                  <span
                    class="badge"
                    :class="cap.productionReady ? 'active' : 'planned'"
                  >
                    {{ cap.productionReady ? "生产就绪" : "规划达标" }}
                  </span>
                </td>
                <td class="mono">
                  <code class="cap-model-code">{{ cap.model }}</code>
                </td>
                <td class="muted">
                  {{ cap.detail }}
                </td>
              </tr>
            </tbody>
          </table>
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

    <section class="panel ai-engines-panel">
      <div class="panel-header">
        <div>
          <h2>AI 视觉模型与推理引擎</h2>
          <p>
            当前平台已装载就绪的多领域 AI 生产级模型与离线视觉推理引擎底座。
          </p>
        </div>
        <span class="badge active">全领域模型已就绪</span>
      </div>

      <div class="engine-grid">
        <article class="engine-card">
          <div class="engine-card-header">
            <div class="engine-icon-wrap"><ScanFace :size="18" /></div>
            <div class="engine-meta">
              <strong>人像视觉分析</strong>
              <small>Portrait Analysis</small>
            </div>
            <span class="badge active">生产就绪</span>
          </div>
          <p class="engine-desc">
            基于 YOLOv8 目标检测、OSNet IBN 重识别与 YOLOv8-Pose 骨架构建的人像全流程分析引擎。
          </p>
          <div class="engine-models">
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">人员检测</span>
              <code class="model-file">models/yolov8n.onnx</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">人体重识别</span>
              <code class="model-file">models/osnet_ibn_x1_0.onnx</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">姿态估计</span>
              <code class="model-file">models/yolov8n-pose.pt</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">人脸检测</span>
              <code class="model-file">models/scrfd_500m.onnx</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">人脸特征</span>
              <code class="model-file">models/arcface.onnx</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">步态特征</span>
              <code class="model-file">models/opengait_gait3d.onnx</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">服饰属性</span>
              <code class="model-file">models/attribute_reid.onnx</code>
            </div>
          </div>
        </article>

        <article class="engine-card">
          <div class="engine-card-header">
            <div class="engine-icon-wrap"><FileText :size="18" /></div>
            <div class="engine-meta">
              <strong>OCR 智能文档</strong>
              <small>Document & Video OCR</small>
            </div>
            <span class="badge active">生产就绪</span>
          </div>
          <p class="engine-desc">
            基于 PaddleOCR 工业级 PP-OCRv4 文本识别三件套与自适应动静态帧差去重推理引擎。
          </p>
          <div class="engine-models">
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">文本检测</span>
              <code class="model-file">models/ocr/ch_PP-OCRv4_det_infer</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">文本识别</span>
              <code class="model-file">models/ocr/ch_PP-OCRv4_rec_infer</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">方向分类</span>
              <code class="model-file">models/ocr/ch_ppocr_mobile_v2.0_cls_infer</code>
            </div>
          </div>
        </article>

        <article class="engine-card">
          <div class="engine-card-header">
            <div class="engine-icon-wrap"><Activity :size="18" /></div>
            <div class="engine-meta">
              <strong>行为动作识别</strong>
              <small>Behavior Analysis</small>
            </div>
            <span class="badge active">生产就绪</span>
          </div>
          <p class="engine-desc">
            结合人体姿态骨架与时序时空特征，识别吸烟、玩手机、摔倒、搏斗、奔跑、攀爬等 50+ 动作模式。
          </p>
          <div class="engine-models">
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">骨架感知</span>
              <code class="model-file">YOLOv8 Pose Skeleton (17点)</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">动作分类器</span>
              <code class="model-file">Behavior Action Engine (50+ 动作)</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">时序追踪</span>
              <code class="model-file">Spatial-Temporal Tracker</code>
            </div>
          </div>
        </article>

        <article class="engine-card">
          <div class="engine-card-header">
            <div class="engine-icon-wrap"><Sparkles :size="18" /></div>
            <div class="engine-meta">
              <strong>服饰风格识别</strong>
              <small>Fashion & Cosplay</small>
            </div>
            <span class="badge active">生产就绪</span>
          </div>
          <p class="engine-desc">
            精准识别 Cosplay 角色、二次元与日常服装风格（JK、Lolita、汉服等）和配饰属性。
          </p>
          <div class="engine-models">
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">风格分类器</span>
              <code class="model-file">Fashion Style Engine</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">角色识别</span>
              <code class="model-file">Cosplay Attribute Matcher</code>
            </div>
            <div class="model-row">
              <span class="dot ready"></span>
              <span class="model-name">配饰检测</span>
              <code class="model-file">Accessory & Prop Detector</code>
            </div>
          </div>
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
      <div class="repository-table-wrapper">
        <table class="repository-table">
          <thead>
            <tr>
              <th scope="col" style="width: 50px">序号</th>
              <th scope="col" class="col-name">仓库</th>
              <th scope="col" class="col-scope">定位与职责界限</th>
              <th scope="col" class="col-gate">下一道门禁</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(repository, index) in repositoryTopology.repositories"
              :key="repository.repository_id"
              :class="{ current: repository.current_repository }"
            >
              <td class="muted">{{ index + 1 }}</td>
              <td class="cell-name">
                <div class="repository-name">
                  <strong>{{
                    labelRepository(repository.repository_id)
                  }}</strong>
                  <span class="badge" :class="repository.lifecycle">{{
                    labelRepositoryLifecycle(repository.lifecycle)
                  }}</span>
                  <small>{{
                    repository.primary_product_ids.map(labelProduct).join(" · ")
                  }}</small>
                </div>
              </td>
              <td class="cell-scope">
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
              </td>
              <td class="cell-gate">
                <div class="repository-gate">
                  <p>{{ labelRepositoryGate(repository.repository_id) }}</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
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
                <th style="width: 50px">序号</th>
                <th>运行</th>
                <th>领域</th>
                <th>状态</th>
                <th>流水线</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(run, index) in runs.items" :key="run.run_id">
                <td class="muted">{{ index + 1 }}</td>
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
        <div class="panel-header">
          <h2>已安装领域</h2>
          <span class="badge">{{ domains.length }} 项</span>
        </div>
        <div class="panel-body domain-list">
          <div
            v-for="domain in domains"
            :key="domain.domain_id"
            class="domain-card"
          >
            <div class="domain-card-header">
              <div class="domain-title-wrap">
                <component
                  :is="domainIcon(domain.domain_id)"
                  :size="15"
                  class="domain-card-icon"
                />
                <strong class="domain-title">{{ domain.display_name }}</strong>
              </div>
              <span class="badge active">版本化插件</span>
            </div>
            <p class="domain-desc">
              {{ labelDomainDescription(domain.domain_id, domain.description) }}
            </p>
            <div class="domain-capabilities-list">
              <span
                v-for="cap in domain.capabilities"
                :key="cap"
                class="cap-pill"
              >
                {{ labelCapability(cap) }}
              </span>
            </div>
          </div>
          <div v-if="!domains.length" class="empty">未读取到领域注册信息</div>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.overview-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 4px;
}
.hero-title h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--graphite);
  line-height: 1.25;
}
.hero-title p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.overview-action {
  text-decoration: none !important;
  flex-shrink: 0;
}
.product-matrix {
  margin-bottom: 20px;
}
.product-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}
.product-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--teal);
  border-radius: 6px;
  background: #fff;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}
.product-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
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
  font-weight: 700;
  overflow-wrap: anywhere;
}
.product-card p {
  margin: 0;
  color: #45534f;
  font-size: 12px;
  line-height: 1.45;
  flex: 1;
}
.product-card small {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
  padding-top: 6px;
  border-top: 1px dashed #e8ecea;
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
  gap: 10px;
  padding: 0 16px 16px;
}
.shared-chip {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: #f7f8f8;
  color: #25332f;
  font-size: 12px;
}
.shared-chip .chip-name {
  font-weight: 650;
}
.shared-chip .chip-layer {
  color: var(--muted);
  font-size: 11px;
}

/* Stats section styling */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.stat {
  padding: 16px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--teal);
  border-radius: 6px;
  background: #fff;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}
.stat:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}
.stat.teal {
  border-top-color: var(--teal);
}
.stat.green {
  border-top-color: var(--green);
}
.stat.coral {
  border-top-color: var(--coral);
}
.stat.amber {
  border-top-color: var(--amber);
}
.stat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}
.stat-icon {
  color: var(--muted);
  opacity: 0.75;
}

/* 人像智能面板 */
.portrait-intelligence {
  margin-bottom: 20px;
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid #8b6fd4;
  border-radius: 6px;
  background: #fff;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}
.pi-module-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
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
  font-weight: 700;
  overflow-wrap: anywhere;
}
.pi-module-card p {
  margin: 0;
  color: #45534f;
  font-size: 12px;
  line-height: 1.45;
  flex: 1;
}
.pi-gate {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
  padding-top: 6px;
  border-top: 1px dashed #e8ecea;
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
  justify-content: space-between;
  gap: 12px;
  padding: 13px 0 10px;
  flex-wrap: wrap;
}
.pi-cap-title-wrap {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.pi-cap-header strong {
  font-size: 13px;
}
.domain-filter-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #edf2f0;
  padding: 2px;
  border-radius: 5px;
}
.domain-tab-btn {
  background: transparent;
  border: none;
  font-size: 11.5px;
  font-weight: 550;
  color: var(--muted);
  padding: 3px 9px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 140ms ease;
}
.domain-tab-btn:hover {
  color: var(--graphite);
}
.domain-tab-btn.active {
  background: #fff;
  color: var(--teal);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.domain-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  background: #eef3f1;
  color: #3b4d47;
}
.domain-pill.portrait {
  background: #e0f2fe;
  color: #0369a1;
}
.domain-pill.ocr {
  background: #fef3c7;
  color: #b45309;
}
.domain-pill.behavior {
  background: #ede9fe;
  color: #6d28d9;
}
.domain-pill.fashion {
  background: #fce7f3;
  color: #be185d;
}
.cap-model-code {
  font-size: 11px;
  color: #0284c7;
  background: #f0f9ff;
  padding: 1px 5px;
  border-radius: 3px;
}
.pi-cap-table {
  margin-bottom: 16px;
}
.pi-cap-name strong {
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--amber);
  border-radius: 6px;
  background: #fff;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}
.pi-asset-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
}

/* AI Engines Panel */
.ai-engines-panel {
  margin-bottom: 20px;
}
.ai-engines-panel .panel-header > div {
  display: grid;
  gap: 4px;
}
.ai-engines-panel .panel-header p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.engine-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}
.engine-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-top: 3px solid #009688;
  border-radius: 6px;
  background: #fff;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}
.engine-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
}
.engine-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.engine-icon-wrap {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--teal-soft);
  color: var(--teal);
  flex-shrink: 0;
}
.engine-meta {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-width: 0;
}
.engine-meta strong {
  font-size: 13px;
  color: #1a2a26;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.engine-meta small {
  font-size: 11px;
  color: var(--muted);
}
.engine-desc {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
  flex-grow: 1;
}
.engine-models {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  background: #f8faf9;
  border: 1px solid var(--line);
  border-radius: 4px;
}
.model-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #334440;
}
.model-row .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.model-row .dot.ready {
  background: #10b981;
}
.model-name {
  font-weight: 600;
  color: #1e2926;
  white-space: nowrap;
}
.model-file {
  font-size: 10.5px;
  color: #0284c7;
  background: #e0f2fe;
  padding: 1px 4px;
  border-radius: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px;
}

.repository-topology {
  margin-bottom: 20px;
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
.repository-table-wrapper {
  padding: 0 16px 16px;
  overflow-x: auto;
}
.repository-table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--line);
  font-size: 12px;
}
.repository-table th {
  padding: 10px 14px;
  background: #f7f8f8;
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
  text-align: left;
  border: 1px solid var(--line);
}
.repository-table td {
  padding: 14px;
  border: 1px solid var(--line);
  vertical-align: top;
}
.col-name {
  width: 24%;
  min-width: 180px;
}
.col-scope {
  width: 52%;
  min-width: 320px;
}
.col-gate {
  width: 24%;
  min-width: 200px;
}
.repository-table tbody tr:hover {
  background: #fafbfa;
}
.repository-table tbody tr.current {
  background: #f8fbfb;
}
.repository-table tbody tr.current td:first-child {
  border-left: 3px solid var(--teal);
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

/* Domain List */
.domain-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}
.domain-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: #fff;
  transition: background 160ms ease;
}
.domain-card:hover {
  background: #fafbfa;
}
.domain-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.domain-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.domain-card-icon {
  color: var(--teal);
  flex-shrink: 0;
}
.domain-title {
  font-size: 13px;
  color: #17211f;
}
.domain-desc {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}
.domain-capabilities-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}
.cap-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: 3px;
  background: #f7f8f8;
  color: #35433f;
  font-size: 11px;
}

@media (max-width: 1180px) {
  .product-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .engine-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pi-modules {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pi-assets {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .repository-contracts {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 560px) {
  .stats {
    grid-template-columns: 1fr;
  }
  .product-grid {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .engine-grid {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .pi-modules {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .pi-assets {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .repository-table-wrapper {
    padding: 0 12px 12px;
  }
  .repository-contracts {
    padding: 12px;
  }
}
</style>
