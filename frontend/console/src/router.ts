import {
  Activity,
  Boxes,
  Database,
  FileSearch,
  FileClock,
  FileText,
  Images,
  LayoutDashboard,
  MessageSquareText,
  PlaySquare,
  Route,
  Search,
  ScanSearch,
  ScanFace,
  Settings2,
  ShieldCheck,
  Workflow,
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
    meta: { title: "总览", icon: LayoutDashboard, section: "核心工作区" },
  },
  {
    path: "/parse/portrait",
    name: "portrait-parse",
    component: () => import("./views/ParseView.vue"),
    props: { initialDomain: "portrait" },
    meta: { title: "人像解析", icon: ScanSearch, section: "核心工作区" },
  },
  {
    path: "/parse/ocr",
    name: "ocr-parse",
    component: () => import("./views/ParseView.vue"),
    props: { initialDomain: "ocr" },
    meta: { title: "OCR 文档解析", icon: FileText, section: "核心工作区" },
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
      icon: ScanSearch,
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
      icon: ScanSearch,
      section: "核心工作区",
      hideFromNavigation: true,
    },
  },
  {
    path: "/assets",
    name: "assets",
    component: () => import("./views/MediaView.vue"),
    meta: { title: "数据资产", icon: Images, section: "数据与分析" },
  },
  {
    path: "/datasets",
    name: "datasets",
    component: () => import("./views/DatasetView.vue"),
    meta: { title: "数据集治理", icon: Database, section: "数据与分析" },
  },
  {
    path: "/media",
    redirect: "/assets",
  },
  {
    path: "/runs",
    name: "runs",
    component: () => import("./views/RunsView.vue"),
    meta: { title: "运行历史", icon: PlaySquare, section: "核心工作区" },
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
    path: "/results",
    name: "results",
    component: () => import("./views/ResultsView.vue"),
    meta: { title: "解析结果", icon: FileSearch, section: "数据与分析" },
  },
  {
    path: "/search",
    name: "search",
    component: () => import("./views/SearchView.vue"),
    meta: { title: "综合检索", icon: Search, section: "智能检索" },
  },
  {
    path: "/search/portrait-compare",
    name: "portrait-compare",
    component: () => import("./views/PortraitCompareView.vue"),
    meta: { title: "人像比对", icon: ScanFace, section: "智能检索" },
  },
  {
    path: "/search/trajectories",
    name: "trajectories",
    component: () => import("./views/TrajectoryView.vue"),
    meta: { title: "长期轨迹", icon: Route, section: "智能检索" },
  },
  {
    path: "/capabilities",
    name: "capabilities",
    component: () => import("./views/CapabilitiesView.vue"),
    meta: { title: "领域与能力", icon: ScanSearch, section: "AI 引擎与模型" },
  },
  {
    path: "/pipelines",
    name: "pipelines",
    component: () => import("./views/PipelinesView.vue"),
    meta: { title: "流水线", icon: Workflow, section: "AI 引擎与模型" },
  },
  {
    path: "/models",
    name: "models",
    component: () => import("./views/ModelsView.vue"),
    meta: { title: "模型管理", icon: Boxes, section: "AI 引擎与模型" },
  },
  {
    path: "/feedback",
    name: "feedback",
    component: () => import("./views/FeedbackView.vue"),
    meta: {
      title: "反馈与发布",
      icon: MessageSquareText,
      section: "AI 引擎与模型",
    },
  },
  {
    path: "/access",
    name: "access",
    component: () => import("./views/AccessView.vue"),
    meta: { title: "接入与权限", icon: Settings2, section: "平台治理与系统" },
  },
  {
    path: "/operations",
    name: "operations",
    component: () => import("./views/OperationsView.vue"),
    meta: { title: "系统运维", icon: Activity, section: "平台治理与系统" },
  },
  {
    path: "/audit",
    name: "audit",
    component: () => import("./views/AuditView.vue"),
    meta: { title: "审计中心", icon: FileClock, section: "平台治理与系统" },
  },
  {
    path: "/enterprise",
    name: "enterprise",
    component: () => import("./views/EnterpriseWorkspaceView.vue"),
    meta: {
      title: "企业专区",
      icon: ShieldCheck,
      section: "平台治理与系统",
    },
  },
  {
    path: "/governance",
    name: "governance",
    component: () => import("./views/GovernanceView.vue"),
    meta: {
      title: "平台治理",
      icon: ShieldCheck,
      section: "平台治理与系统",
    },
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

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
  document.title = `${String(to.meta.title)} · Scenara 景枢`;
});

export { routes };
export default router;
