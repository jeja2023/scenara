import {
  Boxes,
  Cpu,
  Database,
  FileCheck,
  FileClock,
  FileText,
  History,
  KeyRound,
  Layers,
  LayoutDashboard,
  MessageSquarePlus,
  Route,
  Radar,
  ScanFace,
  Search,
  Server,
} from "@lucide/vue";
import { createRouter, createWebHistory } from "vue-router";

import { isSignedIn } from "./auth";

const routes = [
  {
    path: "/login",
    name: "login",
    component: () => import("./views/LoginView.vue"),
    meta: {
      title: "登录",
      public: true,
      layout: "auth",
      hideFromNavigation: true,
    },
  },
  {
    path: "/",
    name: "overview",
    component: () => import("./views/OverviewView.vue"),
    meta: {
      title: "总览",
      description: "聚合全局核心资源指标与各领域最新运行动态。",
      icon: LayoutDashboard,
      section: "核心工作区",
    },
  },
  {
    path: "/parse/portrait",
    name: "portrait-parse",
    component: () => import("./views/ParseView.vue"),
    props: { initialDomain: "portrait" },
    meta: {
      title: "人像解析",
      description: "检测人员并分析人像相关的视觉特征。",
      icon: ScanFace,
      section: "核心工作区",
    },
  },
  {
    path: "/parse/ocr",
    name: "ocr-parse",
    component: () => import("./views/ParseView.vue"),
    props: { initialDomain: "ocr" },
    meta: {
      title: "OCR 文档解析",
      description: "识别并分析文档中的文字、结构和关键信息。",
      icon: FileText,
      section: "核心工作区",
    },
  },
  {
    path: "/parse",
    redirect: "/parse/portrait",
  },
  {
    path: "/parse/:domain",
    name: "parse-domain",
    component: () => import("./views/ParseView.vue"),
    meta: {
      title: "解析",
      description: "AI 引擎与多模态解析工作区。",
      icon: ScanFace,
      section: "核心工作区",
      hideFromNavigation: true,
    },
  },
  {
    path: "/parse/:domain/:mediaKind",
    name: "parse-media",
    component: () => import("./views/ParseView.vue"),
    meta: {
      title: "解析",
      description: "AI 引擎与多模态解析工作区。",
      icon: ScanFace,
      section: "核心工作区",
      hideFromNavigation: true,
    },
  },
  {
    path: "/runs",
    name: "runs",
    component: () => import("./views/RunsView.vue"),
    meta: {
      title: "运行历史",
      description: "全局解析任务运行状态跟踪与调试。",
      icon: History,
      section: "核心工作区",
    },
  },
  {
    path: "/portrait",
    redirect: "/parse/portrait/image",
  },
  {
    path: "/ocr",
    redirect: "/parse/ocr/document",
  },
  {
    path: "/search",
    name: "search",
    component: () => import("./views/search/SearchLayout.vue"),
    meta: {
      title: "智能检索",
      description: "统一进行文本、人像检索与人像 1:1 比对。",
      icon: Search,
      section: "智能检索",
    },
    children: [
      {
        path: "",
        name: "search-root",
        redirect: { name: "search-query" },
      },
      {
        path: "query",
        name: "search-query",
        component: () => import("./views/SearchView.vue"),
        meta: {
          title: "智能检索",
          description: "跨图像、人像与特征的统一图文检索引擎。",
          hideFromNavigation: true,
        },
      },
      {
        path: "compare",
        name: "search-compare",
        component: () => import("./views/PortraitCompareView.vue"),
        meta: {
          title: "人像 1:1 比对",
          description: "两张人像的同人关联概率判断。",
          hideFromNavigation: true,
        },
      },
    ],
  },
  {
    path: "/search/portrait-compare",
    name: "portrait-compare",
    redirect: { name: "search-compare" },
  },
  {
    path: "/search/trajectories",
    name: "trajectories",
    component: () => import("./views/TrajectoryView.vue"),
    meta: {
      title: "长期轨迹",
      description: "查看同一个人在跨摄像头场景下的时间轨迹与频次分布。",
      icon: Route,
      section: "智能检索",
    },
  },
  {
    path: "/surveillance",
    name: "surveillance",
    component: () => import("./views/surveillance/SurveillanceLayout.vue"),
    meta: {
      title: "布控预警",
      description: "统一管理布控名单、任务、实时告警与人工研判。",
      icon: Radar,
      section: "智能检索",
    },
    children: [
      {
        path: "",
        name: "surveillance-root",
        redirect: { name: "surveillance-live" },
      },
      {
        path: "watchlists",
        name: "surveillance-watchlists",
        component: () => import("./views/surveillance/WatchlistManagement.vue"),
        meta: {
          title: "布控名单",
          description: "管理引用既有人像身份的布控名单与成员有效期。",
          hideFromNavigation: true,
        },
      },
      {
        path: "tasks",
        name: "surveillance-tasks",
        component: () => import("./views/surveillance/TaskManagement.vue"),
        meta: {
          title: "布控任务",
          description: "配置名单、视频源、摄像头、阈值与告警冷却策略。",
          hideFromNavigation: true,
        },
      },
      {
        path: "live",
        name: "surveillance-live",
        component: () => import("./views/surveillance/LiveAlertCenter.vue"),
        meta: {
          title: "实时预警",
          description: "订阅已持久化的实时匹配告警并支持断线恢复。",
          hideFromNavigation: true,
        },
      },
      {
        path: "alerts",
        name: "surveillance-alerts",
        component: () => import("./views/surveillance/AlertHistory.vue"),
        meta: {
          title: "告警研判",
          description: "筛选历史告警、核验抓拍并完成确认、误报或忽略处置。",
          hideFromNavigation: true,
        },
      },
    ],
  },
  {
    path: "/results",
    name: "results",
    component: () => import("./views/ResultsView.vue"),
    meta: {
      title: "解析结果",
      description: "跨领域历史解析结果汇总与按特征检索。",
      icon: FileCheck,
      section: "数据与分析",
    },
  },
  {
    path: "/assets",
    name: "assets",
    component: () => import("./views/MediaView.vue"),
    meta: {
      title: "数据资产",
      description: "全局文件与视频流资产治理。",
      icon: Layers,
      section: "数据与分析",
    },
  },
  {
    path: "/datasets",
    name: "datasets",
    component: () => import("./views/DatasetView.vue"),
    meta: {
      title: "数据集治理",
      description: "数据集中集管理、版本切换与生命周期治理。",
      icon: Database,
      section: "数据与分析",
      platform: "data",
    },
  },
  {
    path: "/media",
    redirect: "/assets",
  },
  {
    path: "/capabilities",
    name: "capabilities",
    component: () => import("./views/CapabilitiesView.vue"),
    meta: {
      title: "领域与能力",
      description: "统一查看与管理系统领域模块及核心视觉 AI 能力。",
      icon: Cpu,
      section: "AI 引擎与模型",
    },
  },
  {
    path: "/pipelines",
    redirect: "/capabilities",
  },
  {
    path: "/models",
    component: () => import("./views/models/ModelLifecycleLayout.vue"),
    meta: {
      title: "模型生命周期",
      description: "统一管理模型包、准入、发布、回滚与部署证据。",
      icon: Boxes,
      section: "AI 引擎与模型",
      platform: "model",
    },
    children: [
      {
        path: "",
        redirect: { name: "model-catalog" },
      },
      {
        path: "catalog",
        name: "model-catalog",
        component: () => import("./views/ModelsView.vue"),
        meta: {
          title: "模型生命周期",
          description: "查看已登记模型包及其准入状态。",
          hideFromNavigation: true,
        },
      },
      {
        path: "releases",
        name: "model-releases",
        component: () => import("./views/FeedbackView.vue"),
        props: { initialTab: "releases", allowedTabs: ["releases"] },
        meta: {
          title: "模型发布与准入",
          description: "管理候选版本、发布流转、回滚和部署审计。",
          hideFromNavigation: true,
        },
      },
    ],
  },
  {
    path: "/feedback",
    name: "feedback",
    component: () => import("./views/FeedbackView.vue"),
    props: { initialTab: "feedback", allowedTabs: ["feedback", "manifests"] },
    meta: {
      title: "反馈与难例",
      description: "管理解析纠错反馈、审核与版本化难例清单。",
      icon: MessageSquarePlus,
      section: "AI 引擎与模型",
    },
  },
  {
    path: "/access",
    name: "access",
    component: () => import("./views/AccessView.vue"),
    meta: {
      title: "接入与权限",
      description: "API 密钥、会话与多租户权限配置。",
      icon: KeyRound,
      section: "平台治理与系统",
    },
  },
  {
    path: "/operations",
    component: () => import("./views/operations/OperationsLayout.vue"),
    meta: {
      title: "系统运维",
      description: "监控平台核心服务与外部适配器运行状态。",
      icon: Server,
      section: "平台治理与系统",
    },
    children: [
      {
        path: "",
        name: "operations",
        component: () => import("./views/OperationsView.vue"),
        meta: {
          title: "系统运维",
          description: "监控平台核心服务与关键基础设施运行状态。",
          hideFromNavigation: true,
        },
      },
      {
        path: "integrations",
        name: "operations-integrations",
        component: () => import("./views/GovernanceView.vue"),
        props: { initialTab: "adapters", allowedTabs: ["adapters"] },
        meta: {
          title: "集成适配器",
          description: "查看外部身份、标注、索引和重排适配器的健康状态。",
          hideFromNavigation: true,
        },
      },
    ],
  },
  {
    path: "/audit",
    component: () => import("./views/audit/AuditLayout.vue"),
    meta: {
      title: "审计中心",
      description: "查看审计日志、导出证据包与保留策略。",
      icon: FileClock,
      section: "平台治理与系统",
    },
    children: [
      {
        path: "",
        name: "audit",
        component: () => import("./views/AuditView.vue"),
        meta: {
          title: "审计中心",
          description: "查看全局审计日志并导出证据包。",
          hideFromNavigation: true,
        },
      },
      {
        path: "retention",
        name: "audit-retention",
        component: () => import("./views/GovernanceView.vue"),
        props: { initialTab: "retention", allowedTabs: ["retention"] },
        meta: {
          title: "审计保留策略",
          description: "配置审计事件与合规证据的保留策略。",
          hideFromNavigation: true,
        },
      },
    ],
  },
  {
    path: "/access/lifecycle",
    name: "access-lifecycle",
    component: () => import("./views/GovernanceView.vue"),
    props: { initialTab: "lifecycle", allowedTabs: ["lifecycle"] },
    meta: {
      title: "项目生命周期",
      description: "管理项目停用、恢复和删除申请。",
      hideFromNavigation: true,
    },
  },
  { path: "/governance", redirect: "/operations/integrations" },
  { path: "/enterprise", redirect: "/operations" },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

import { labelDomain } from "./labels";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});
router.beforeEach((to) => {
  if (!to.meta.public && !isSignedIn()) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && isSignedIn()) return { name: "overview" };
  return true;
});
router.afterEach((to) => {
  let title = String(to.meta.title);
  const domain = (to.params.domain ||
    to.query.domain ||
    (to.name === "portrait-parse"
      ? "portrait"
      : to.name === "ocr-parse"
        ? "ocr"
        : "")) as string;
  if (to.path.startsWith("/parse") && domain) {
    if (domain === "portrait") {
      title = "人像解析";
    } else if (domain === "ocr") {
      title = "OCR 文档解析";
    } else {
      const name = labelDomain(domain);
      title = name.endsWith("解析") ? name : `${name}解析`;
    }
  }
  document.title = `${title} · Scenara 景枢`;
});

export { routes };
export default router;
