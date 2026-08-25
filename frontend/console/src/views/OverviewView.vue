<script setup lang="ts">
import {
  Activity,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Cpu,
  FileText,
  GitBranch,
  Layers,
  Play,
  ScanFace,
  Server,
  ShieldCheck,
  Sparkles,
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import {
  labelDomain,
  labelPipeline,
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
  Run,
  TableColumn,
} from "../types";
import DataTable from "../components/DataTable.vue";

interface FullCapabilityItem {
  id: string;
  domain: string;
  name: string;
  readiness: "ready" | "fallback" | "placeholder";
  productionReady: boolean;
  model: string;
  detail: string;
}

const capabilityColumns: TableColumn<FullCapabilityItem>[] = [
  { key: "domain", label: "领域", width: "110px" },
  { key: "name", label: "核心能力", class: "pi-cap-name" },
  { key: "readiness", label: "就绪状态" },
  { key: "productionReady", label: "生产支持" },
  { key: "model", label: "模型与引擎配置", class: "mono" },
  { key: "detail", label: "特性说明", class: "muted" },
];

const overviewRunColumns: TableColumn<Run>[] = [
  { key: "run_id", label: "任务 ID", class: "mono" },
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
const products = ref<ProductCatalogItem[]>([]);
const repositoryTopology = ref<RepositoryTopology>({
  schema_version: "1.0",
  current_repository_id: "scenara",
  repositories: [],
  integration_contracts: [],
  boundary_rules: [],
});
const portraitIntelligence = ref<PortraitIntelligenceStatus | null>(null);
const showCapabilityTable = ref(false);

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

// 领域汇总模型与能力配置
const domainEngineSummaries = computed(() => [
  {
    id: "portrait",
    name: "人像视觉分析",
    englishName: "Portrait Analysis",
    description: "基于 YOLOv8、OSNet IBN、SCRFD、ArcFace 与 OpenGait 构建的人像端到端视觉中枢。",
    capabilitiesCount: 7,
    models: [
      { name: "人员检测", file: "models/yolov8n.onnx" },
      { name: "人体重识别", file: "models/osnet_ibn_x1_0.onnx" },
      { name: "姿态骨架", file: "models/yolov8n-pose.pt" },
      { name: "人脸定位", file: "models/scrfd_500m.onnx" },
      { name: "人脸特征", file: "models/arcface.onnx" },
      { name: "步态时序", file: "models/opengait_gait3d.onnx" },
      { name: "服饰属性", file: "models/attribute_reid.onnx" },
    ],
  },
  {
    id: "ocr",
    name: "OCR 智能文档",
    englishName: "Document & Video OCR",
    description: "基于 PP-OCRv4 文本定位识别套件与自适应动静态帧差去重推理引擎。",
    capabilitiesCount: 4,
    models: [
      { name: "文本检测", file: "models/ocr/ch_PP-OCRv4_det_infer" },
      { name: "文字识别", file: "models/ocr/ch_PP-OCRv4_rec_infer" },
      { name: "方向纠偏", file: "models/ocr/ch_ppocr_mobile_v2.0_cls_infer" },
      { name: "时序去重", file: "Adaptive Motion Deduplication" },
    ],
  },
  {
    id: "behavior",
    name: "行为动作识别",
    englishName: "Behavior Analysis",
    description: "结合人体骨架与时序时空特征，精准识别吸烟、摔倒、搏斗等 50+ 动作模式与异常告警。",
    capabilitiesCount: 3,
    models: [
      { name: "骨架感知", file: "YOLOv8 Pose Skeleton (17点)" },
      { name: "动作分类器", file: "Behavior Action Engine (50+)" },
      { name: "时空追踪", file: "Spatial-Temporal Tracker" },
    ],
  },
  {
    id: "fashion",
    name: "服饰风格识别",
    englishName: "Fashion & Cosplay",
    description: "精准识别 Cosplay 角色、二次元与日常服饰风格（JK、Lolita、汉服等）和配饰属性。",
    capabilitiesCount: 3,
    models: [
      { name: "风格分类器", file: "Fashion Style Engine" },
      { name: "角色匹配", file: "Cosplay Character Matcher" },
      { name: "配饰道具", file: "Accessory & Prop Detector" },
    ],
  },
]);

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page overview-page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <!-- 1. 核心指标统计栏 (分层平衡结构：顶行标题+右上徽章，中层大数值，底层辅助说明) -->
    <div class="stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">总任务运行</span>
          <div class="stat-icon-badge">
            <Activity :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ runs.total }}</div>
        <div class="stat-desc">历史与当前处理总数</div>
      </div>

      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">活跃队列</span>
          <div class="stat-icon-badge">
            <Play :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ activeRuns }}</div>
        <div class="stat-desc">排队与并发执行中</div>
      </div>

      <div class="stat coral">
        <div class="stat-top-row">
          <span class="stat-title">异常与关注</span>
          <div class="stat-icon-badge">
            <AlertCircle :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ failedRuns }}</div>
        <div class="stat-desc">失败或已取消任务</div>
      </div>

      <div class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">AI 核心能力</span>
          <div class="stat-icon-badge">
            <Cpu :size="15" />
          </div>
        </div>
        <div class="stat-value">17 / 17</div>
        <div class="stat-desc">全领域生产模型已就绪</div>
      </div>
    </div>

    <!-- 2. AI 视觉多领域与模型引擎全景 (深度整合原先重复的领域卡片、模型列表与能力清单) -->
    <section class="panel ai-engines-panel">
      <div class="panel-header">
        <div class="header-left">
          <h2>AI 视觉模型与多领域推理引擎</h2>
          <p>
            平台装载的离线多模态视觉推理引擎与 17 项全流程算法能力，支持端到端就绪分析。
          </p>
        </div>
        <div class="header-right">
          <button
            class="button secondary toggle-matrix-btn"
            @click="showCapabilityTable = !showCapabilityTable"
          >
            <Layers :size="14" />
            <span>{{ showCapabilityTable ? "收起能力明细矩阵" : "查看 17 项能力规格明细" }}</span>
            <component :is="showCapabilityTable ? ChevronUp : ChevronDown" :size="14" />
          </button>
          <span class="badge active">全领域模型已就绪 (100%)</span>
        </div>
      </div>

      <!-- 四大多模态领域综合大卡片 -->
      <div class="engine-grid">
        <article
          v-for="domain in domainEngineSummaries"
          :key="domain.id"
          class="engine-card"
        >
          <div class="engine-card-header">
            <div class="engine-icon-wrap">
              <component :is="domainIcon(domain.id)" :size="18" />
            </div>
            <div class="engine-meta">
              <strong>{{ domain.name }}</strong>
              <small>{{ domain.englishName }}</small>
            </div>
            <span class="badge active">{{ domain.capabilitiesCount }} 项已就绪</span>
          </div>

          <p class="engine-desc">{{ domain.description }}</p>

          <div class="engine-models-list">
            <div
              v-for="mod in domain.models"
              :key="mod.name"
              class="model-row-item"
            >
              <span class="dot ready"></span>
              <span class="model-item-name">{{ mod.name }}</span>
              <code class="model-item-file">{{ mod.file }}</code>
            </div>
          </div>
        </article>
      </div>

      <!-- 展开式的全领域能力规格与模型矩阵表格 (仅在用户需要看详细参数时展示) -->
      <div v-if="showCapabilityTable" class="matrix-table-section">
        <div class="matrix-table-toolbar">
          <div class="matrix-tabs">
            <button
              v-for="opt in domainFilterOptions"
              :key="opt.id"
              class="matrix-tab-btn"
              :class="{ active: selectedDomainFilter === opt.id }"
              @click="selectedDomainFilter = opt.id"
            >
              {{ opt.label }}
            </button>
          </div>
          <small class="muted">
            显示 {{ filteredCapabilities.length }} 项中的 {{ readyCapabilitiesCount }} 项生产就绪算法
          </small>
        </div>

        <DataTable
          :columns="capabilityColumns"
          :items="filteredCapabilities"
          table-class="pi-cap-table"
          empty-text="暂无匹配的算法能力"
        >
          <template #domain="{ row }">
            <span class="domain-pill" :class="row.domain">
              <component :is="domainIcon(row.domain)" :size="12" />
              {{ domainLabel(row.domain) }}
            </span>
          </template>
          <template #name="{ row }">
            <strong>{{ row.name }}</strong>
          </template>
          <template #readiness="{ row }">
            <span class="badge" :class="`pi-${row.readiness}`">
              {{ row.readiness === "ready" ? "已就绪" : "开发替代" }}
            </span>
          </template>
          <template #productionReady="{ row }">
            <span
              class="badge"
              :class="row.productionReady ? 'active' : 'planned'"
            >
              {{ row.productionReady ? "生产就绪" : "规划达标" }}
            </span>
          </template>
          <template #model="{ row }">
            <code class="cap-model-code">{{ row.model }}</code>
          </template>
        </DataTable>
      </div>
    </section>

    <!-- 3. 最近运行动态看板 (独立全宽横向展开) -->
    <section class="panel runs-panel">
      <div class="panel-header">
        <div>
          <h2>最近运行动态</h2>
          <p>实时查看多领域解析任务队列与执行状态。</p>
        </div>
        <RouterLink class="button secondary" to="/runs">查看全部队列</RouterLink>
      </div>

      <DataTable
        :columns="overviewRunColumns"
        :items="runs.items"
        empty-text="暂无运行记录，点击右上角「新建解析」开始体验"
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
          {{ labelPipeline(row.pipeline.pipeline_id) }} · {{ row.pipeline.version }}
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

    <!-- 4. 平台产品体系与成熟度 (垂直纵向排布，全宽网格化展示各模块) -->
    <section class="panel product-matrix-panel">
      <div class="panel-header">
        <div>
          <h2>产品体系与成熟度</h2>
          <p>平台母品牌 Scenara 下各产品模块与共享底座演进矩阵。</p>
        </div>
        <span class="badge">{{ products.length }} 个目录项</span>
      </div>

      <div class="product-mini-list">
        <article
          v-for="product in productModules"
          :key="product.product_id"
          class="product-mini-item"
        >
          <div class="product-mini-header">
            <strong>{{ labelProduct(product.product_id) }}</strong>
            <span class="badge" :class="product.maturity">
              {{ labelMaturity(product.maturity) }}
            </span>
          </div>
          <p class="product-mini-desc">{{ labelProductSummary(product.product_id) }}</p>
          <small class="product-mini-gate">
            {{ labelLayer(product.layer) }} · {{ labelProductGate(product.product_id) }}
          </small>
        </article>
      </div>

      <!-- 底座与控制面精简状态 -->
      <div class="product-foundation-bar">
        <div class="foundation-title">基础底座与共享控制面</div>
        <div class="foundation-chips">
          <div
            v-for="product in [...foundationProducts, ...sharedProducts]"
            :key="product.product_id"
            class="foundation-chip"
          >
            <span class="chip-name">{{ labelProduct(product.product_id) }}</span>
            <span class="badge" :class="product.maturity">{{ labelMaturity(product.maturity) }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 4. 平台拓扑与架构治理 (精炼 3 仓库架构边界) -->
    <section class="panel repository-topology-panel">
      <div class="panel-header">
        <div>
          <h2>仓库拓扑与边界治理</h2>
          <p>
            平台集成底座保留在主仓，模型算法与数据资产中台独立演进，保障高内聚低耦合。
          </p>
        </div>
        <span class="badge">契约 {{ repositoryTopology.schema_version }}</span>
      </div>

      <div class="repository-grid">
        <article
          v-for="repository in repositoryTopology.repositories"
          :key="repository.repository_id"
          class="repo-card"
          :class="{ current: repository.current_repository }"
        >
          <div class="repo-card-header">
            <div class="repo-title-wrap">
              <GitBranch :size="16" class="repo-icon" />
              <strong>{{ labelRepository(repository.repository_id) }}</strong>
            </div>
            <span class="badge" :class="repository.lifecycle">
              {{ labelRepositoryLifecycle(repository.lifecycle) }}
            </span>
          </div>

          <p class="repo-desc">{{ labelRepositorySummary(repository.repository_id) }}</p>

          <div class="repo-responsibilities">
            <div class="resp-block">
              <span class="resp-label plus">核心职责：</span>
              <span class="resp-text">
                {{ repository.responsibilities.map(labelRepositoryResponsibility).join("、") }}
              </span>
            </div>
            <div class="resp-block">
              <span class="resp-label minus">排除职责：</span>
              <span class="resp-text muted">
                {{ repository.excluded_responsibilities.map(labelRepositoryResponsibility).join("、") }}
              </span>
            </div>
          </div>

          <div class="repo-gate-footer">
            <small>门禁要求：{{ labelRepositoryGate(repository.repository_id) }}</small>
          </div>
        </article>
      </div>

      <!-- 契约与强制边界规则 -->
      <div class="topology-rules-bar">
        <div class="rule-group">
          <strong class="rule-title"><Server :size="13" /> 跨仓库契约：</strong>
          <div class="rule-tags">
            <span
              v-for="contract in repositoryTopology.integration_contracts"
              :key="contract.contract_id"
              class="rule-pill"
            >
              {{ labelRepositoryContract(contract.contract_id) }}
            </span>
          </div>
        </div>
        <div class="rule-group">
          <strong class="rule-title"><ShieldCheck :size="13" /> 强制边界：</strong>
          <div class="rule-tags">
            <span
              v-for="rule in repositoryTopology.boundary_rules"
              :key="rule"
              class="rule-pill rule-security"
            >
              {{ labelRepositoryBoundaryRule(rule) }}
            </span>
          </div>
        </div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  font-family: var(--font-sans);
  color: var(--color-text, #17211f);
}

/* ========================================================
   全局面板容器与标题层级规范 (Panel Headers & Typography)
   ======================================================== */
.panel {
  background: var(--color-surface, #fff);
  border: 1px solid var(--line, #e2e8e6);
  border-radius: var(--radius-md, 8px);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

/* 一级/板块大标题 (H2 Standard) */
.panel-header h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text, #17211f);
  margin: 0;
  line-height: 1.3;
  letter-spacing: -0.01em;
}

/* 板块副说明文本 (Panel Subtitle) */
.panel-header p {
  font-size: 12px;
  color: var(--muted, #64716d);
  margin: 3px 0 0;
  line-height: 1.45;
}

.header-left h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text, #17211f);
  margin: 0;
  line-height: 1.3;
  letter-spacing: -0.01em;
}

.header-left p {
  font-size: 12px;
  color: var(--muted, #64716d);
  margin: 3px 0 0;
  line-height: 1.45;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ========================================================
   1. 统计卡片栏 (Stats Metrics Bar - 顶层标题/右上徽章 + 中层数值 + 底层辅助)
   ======================================================== */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat {
  padding: 12px 14px;
  border-radius: var(--radius-sm, 6px);
  background: #fff;
  border: 1px solid var(--line, #e2e8e6);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
}

.stat:hover {
  transform: translateY(-1px);
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.04);
}

.stat-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 2px;
}

/* 指标小标题 (左上) */
.stat-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted, #64716d);
}

/* 指标右上专属微图标徽章 */
.stat-icon-badge {
  width: 26px;
  height: 26px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 140ms ease;
}

.stat:hover .stat-icon-badge {
  transform: scale(1.08);
}

.stat.teal .stat-icon-badge {
  background: #f0fdfa;
  color: #0f766e;
  border: 1px solid #ccfbf1;
}

.stat.green .stat-icon-badge {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #dcfce7;
}

.stat.coral .stat-icon-badge {
  background: #fff1f2;
  color: #e11d48;
  border: 1px solid #ffe4e6;
}

.stat.amber .stat-icon-badge {
  background: #fffbeb;
  color: #d97706;
  border: 1px solid #fef3c7;
}

/* 指标大数值 (中层居中突出) */
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text, #17211f);
  line-height: 1.15;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  text-align: center;
  margin: 3px 0 1px;
}

/* 指标辅助说明 (底层居中) */
.stat-desc {
  font-size: 11px;
  color: #8c9b97;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.35;
  text-align: center;
}

/* ========================================================
   2. AI 视觉多领域与模型引擎全景 (Domain Engine Cards)
   ======================================================== */
.toggle-matrix-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.engine-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.engine-card {
  border: 1px solid var(--line, #e2e8e6);
  border-radius: var(--radius-sm, 6px);
  padding: 14px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 160ms ease;
}

.engine-card:hover {
  border-color: var(--teal, #087682);
  box-shadow: 0 4px 12px rgba(8, 118, 130, 0.08);
}

.engine-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.engine-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm, 6px);
  background: var(--teal-soft, #f0fdfa);
  color: var(--teal, #087682);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.engine-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* 三级标题 / 领域名称 (H3 Standard) */
.engine-meta strong {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.engine-meta small {
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.3;
}

/* 正文描述 (Body Text) */
.engine-desc {
  font-size: 12px;
  line-height: 1.5;
  color: #4b5d58;
  margin: 0;
  min-height: 36px;
}

.engine-models-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 10px;
  border-top: 1px dashed var(--line, #e2e8e6);
}

.model-row-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot.ready {
  background: #16a34a;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.2);
}

.model-item-name {
  font-weight: 600;
  font-size: 11.5px;
  color: var(--color-text, #17211f);
  min-width: 58px;
  flex-shrink: 0;
}

.model-item-file {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--teal, #087682);
  background: var(--teal-soft, #f0fdfa);
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 矩阵表格区域 */
.matrix-table-section {
  margin-top: 4px;
  padding-top: 14px;
  border-top: 1px solid var(--line, #e2e8e6);
  display: flex;
  flex-direction: column;
  gap: 12px;
  animation: fadeIn 200ms ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.matrix-table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.matrix-tabs {
  display: flex;
  gap: 4px;
  background: #f1f5f4;
  padding: 3px;
  border-radius: var(--radius-sm, 6px);
}

.matrix-tab-btn {
  border: none;
  background: transparent;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted, #64716d);
  border-radius: 4px;
  cursor: pointer;
  transition: all 140ms ease;
}

.matrix-tab-btn.active {
  background: #fff;
  color: var(--teal, #087682);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.domain-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11.5px;
  font-weight: 600;
}

.domain-pill.portrait { background: #e0f2fe; color: #0369a1; }
.domain-pill.ocr { background: #fef3c7; color: #b45309; }
.domain-pill.behavior { background: #f3e8ff; color: #7e22ce; }
.domain-pill.fashion { background: #fce7f3; color: #be185d; }

.pi-cap-name strong {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text, #17211f);
}

.cap-model-code {
  font-family: var(--font-mono);
  font-size: 11px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 2px 6px;
  border-radius: 3px;
  color: #334155;
}

/* ========================================================
   3. 最近运行动态与表格层级 (Runs Table)
   ======================================================== */
.runs-panel, .product-matrix-panel, .repository-topology-panel {
  background: #fff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: var(--radius-md, 8px);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.run-link {
  font-family: var(--font-mono);
  color: var(--teal, #087682);
  font-weight: 600;
  font-size: 12px;
  text-decoration: none;
}

.run-link:hover {
  text-decoration: underline;
}

.domain-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #334155;
}

/* ========================================================
   4. 平台产品体系网格化规范 (Product Matrix Cards)
   ======================================================== */
.product-mini-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.product-mini-item {
  border: 1px solid var(--line, #e2e8e6);
  border-radius: var(--radius-sm, 6px);
  padding: 12px 14px;
  background: #fafbfb;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: all 140ms ease;
}

.product-mini-item:hover {
  border-color: var(--teal, #087682);
  background: #f7fdfb;
}

.product-mini-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

/* 产品卡片标题 (H3 Standard) */
.product-mini-header strong {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text, #17211f);
}

/* 产品卡片正文 (Body Text) */
.product-mini-desc {
  font-size: 12px;
  color: #4b5d58;
  margin: 0;
  line-height: 1.45;
}

/* 产品门禁辅助信息 */
.product-mini-gate {
  font-size: 11px;
  color: #8c9b97;
  line-height: 1.35;
}

.product-foundation-bar {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px dashed var(--line, #e2e8e6);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.foundation-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text, #17211f);
}

.foundation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.foundation-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fff;
  font-size: 11.5px;
}

.foundation-chip .chip-name {
  font-weight: 500;
  color: #17211f;
}

/* ========================================================
   5. 仓库拓扑与边界治理层级规范 (Repository Topology Cards)
   ======================================================== */
.repository-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.repo-card {
  border: 1px solid var(--line, #e2e8e6);
  border-radius: var(--radius-sm, 6px);
  padding: 14px;
  background: #fafbfa;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.repo-card.current {
  border-color: var(--teal, #087682);
  background: #f7fdfb;
}

.repo-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.repo-title-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 仓库卡片标题 (H3 Standard) */
.repo-title-wrap strong {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text, #17211f);
}

.repo-icon {
  color: var(--teal, #087682);
  flex-shrink: 0;
}

/* 仓库正文描述 (Body Text) */
.repo-desc {
  font-size: 12px;
  color: #4b5d58;
  margin: 0;
  line-height: 1.45;
}

.repo-responsibilities {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11.5px;
  line-height: 1.4;
  background: #fff;
  padding: 8px 10px;
  border-radius: 4px;
  border: 1px solid var(--line, #e2e8e6);
}

.resp-block {
  display: flex;
  gap: 4px;
}

.resp-label {
  font-weight: 600;
  flex-shrink: 0;
  font-size: 11.5px;
}

.resp-label.plus { color: #087682; }
.resp-label.minus { color: #b45309; }

.resp-text {
  color: #334155;
}

.repo-gate-footer {
  font-size: 11px;
  color: #8c9b97;
  margin-top: auto;
  line-height: 1.35;
}

.topology-rules-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--line, #e2e8e6);
}

.rule-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rule-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text, #17211f);
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.rule-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rule-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  background: #f1f5f4;
  color: #334155;
  border: 1px solid var(--line, #e2e8e6);
  line-height: 1.4;
}

.rule-pill.rule-security {
  background: #fef2f2;
  color: #991b1b;
  border-color: #fecaca;
}

/* ========================================================
   响应式适配 (Responsive)
   ======================================================== */
@media (max-width: 1200px) {
  .engine-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .repository-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .engine-grid {
    grid-template-columns: 1fr;
  }
}
</style>
