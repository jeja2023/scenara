import {
  Activity,
  Boxes,
  FileSearch,
  Images,
  LayoutDashboard,
  MessageSquareText,
  PlaySquare,
  ScanSearch,
  Settings2,
  ShieldCheck,
  Workflow,
} from "@lucide/vue";
import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "overview",
    component: () => import("./views/OverviewView.vue"),
    meta: { title: "总览", icon: LayoutDashboard, section: "工作台" },
  },
  {
    path: "/parse",
    name: "parse",
    component: () => import("./views/ParseView.vue"),
    meta: { title: "解析", icon: ScanSearch, section: "工作台" },
  },
  {
    path: "/parse/:domain",
    name: "parse-domain",
    component: () => import("./views/ParseView.vue"),
    meta: {
      title: "解析",
      icon: ScanSearch,
      section: "工作台",
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
      section: "工作台",
      hideFromNavigation: true,
    },
  },
  {
    path: "/assets",
    name: "assets",
    component: () => import("./views/MediaView.vue"),
    meta: { title: "数据资产", icon: Images, section: "数据" },
  },
  {
    path: "/media",
    redirect: "/assets",
  },
  {
    path: "/runs",
    name: "runs",
    component: () => import("./views/RunsView.vue"),
    meta: { title: "运行", icon: PlaySquare, section: "工作台" },
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
    meta: { title: "解析结果", icon: FileSearch, section: "结果" },
  },
  {
    path: "/capabilities",
    name: "capabilities",
    component: () => import("./views/CapabilitiesView.vue"),
    meta: { title: "领域与能力", icon: ScanSearch, section: "配置" },
  },
  {
    path: "/pipelines",
    name: "pipelines",
    component: () => import("./views/PipelinesView.vue"),
    meta: { title: "流水线", icon: Workflow, section: "配置" },
  },
  {
    path: "/models",
    name: "models",
    component: () => import("./views/ModelsView.vue"),
    meta: { title: "模型", icon: Boxes, section: "配置" },
  },
  {
    path: "/feedback",
    name: "feedback",
    component: () => import("./views/FeedbackView.vue"),
    meta: { title: "反馈与发布", icon: MessageSquareText, section: "治理" },
  },
  {
    path: "/access",
    name: "access",
    component: () => import("./views/AccessView.vue"),
    meta: { title: "接入", icon: Settings2, section: "配置" },
  },
  {
    path: "/operations",
    name: "operations",
    component: () => import("./views/OperationsView.vue"),
    meta: { title: "运维", icon: Activity, section: "治理" },
  },
  {
    path: "/enterprise",
    name: "enterprise",
    component: () => import("./views/EnterpriseWorkspaceView.vue"),
    meta: { title: "企业", icon: ShieldCheck, section: "治理" },
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});
router.afterEach((to) => {
  document.title = `${String(to.meta.title)} · Scenara 景枢`;
});

export { routes };
export default router;
