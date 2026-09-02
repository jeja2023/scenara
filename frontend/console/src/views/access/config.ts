import { BellPlus, KeyRound, Shield, ShieldCheck, Users } from "@lucide/vue";

import type { DisplayProduct, AccessTabDefinition } from "./types";

export const defaultProductsList: DisplayProduct[] = [
  {
    id: "parse",
    name: "智能视觉与文档解析",
    domain: "视觉解析与OCR",
    summary:
      "面向图片、文档、视频与实时流的多模态解析，含人像、OCR、行为与服饰等核心 AI 能力",
    layer: "product_module",
    maturity: "available",
    scopes: [
      "媒体接入",
      "运行生命周期",
      "版本化流水线",
      "OCR 文档解析",
      "人像分析",
      "行为动作",
      "服饰风格",
    ],
  },
  {
    id: "search",
    name: "综合与多模态检索",
    domain: "图文检索与布控",
    summary: "面向视觉资产、结果索引与布控名单的多模态图文与人像检索",
    layer: "product_module",
    maturity: "available",
    scopes: [
      "人像特征检索",
      "文档全文检索",
      "多模态过滤",
      "布控预警联动",
      "保存的检索定义",
    ],
  },
  {
    id: "model",
    name: "AI 模型管理与准入",
    domain: "模型准入与发布",
    summary: "模型准入评估、版本发布治理、运行参数调优与不可变制品回滚",
    layer: "product_module",
    maturity: "available",
    scopes: ["模型制品准入", "版本生命周期", "部署状态变更", "反馈回溯评估"],
  },
  {
    id: "data",
    name: "数据资产与数据集治理",
    domain: "数据资产与标注",
    summary: "为视觉 AI 提供媒体素材、特征存储、标注数据集与难例数据闭环",
    layer: "product_module",
    maturity: "available",
    scopes: [
      "媒体素材资产",
      "特征向量存储",
      "数据集版本管理",
      "难例清单闭环",
      "质量评分血缘",
    ],
  },
  {
    id: "flow",
    name: "智能分析流水线编排",
    domain: "跨领域编排调度",
    summary: "类型化流水线引擎、多领域算法节点串联、条件分支与审批执行",
    layer: "product_module",
    maturity: "available",
    scopes: ["流水线引擎执行", "算法节点编排", "审批分支门禁", "调度并发控制"],
  },
  {
    id: "index",
    name: "特征与向量索引底座",
    domain: "向量特征底座",
    summary: "面向解析结果和特征向量的租户级多模态索引基础设施",
    layer: "foundation",
    maturity: "available",
    scopes: [
      "特征向量索引",
      "多模态检索底座",
      "生命周期软删除",
      "Qdrant/向量存储适配",
    ],
  },
  {
    id: "api",
    name: "开放应用接口",
    domain: "系统开放接口",
    summary: "面向平台集成的版本化 OpenAPI、REST 接口与 Webhook 实时回调",
    layer: "developer_surface",
    maturity: "available",
    scopes: [
      "OpenAPI v1 契约",
      "Webhook 回调推送",
      "接口访问令牌鉴权",
      "系统运行探针",
    ],
  },
  {
    id: "sdk",
    name: "多语言开发工具包",
    domain: "开发者客户端",
    summary: "面向 Python 与 TypeScript 开发者的标准客户端库",
    layer: "developer_surface",
    maturity: "available",
    scopes: [
      "Python SDK 客户端",
      "TypeScript SDK 客户端",
      "OpenAPI 类型化定义",
    ],
  },
  {
    id: "console",
    name: "平台共享控制台",
    domain: "共享管理中心",
    summary: "租户运维、用户身份权限、审计治理与多模块共用管理控制台",
    layer: "control_plane",
    maturity: "available",
    scopes: [
      "多租户工作区隔离",
      "IAM 身份权限管理",
      "系统运维监控",
      "全局合规审计",
    ],
  },
];

export const scopePresets = [
  { id: "*", label: "全部操作权限", summary: "完全控制平台所有资源与服务" },
  {
    id: "iam:*",
    label: "管理身份与权限",
    summary: "管理组织、用户、角色与成员",
  },
  {
    id: "iam:read",
    label: "只读查看身份",
    summary: "仅允许读取身份与授权配置",
  },
  {
    id: "platform:*",
    label: "平台全局管理",
    summary: "租户架构与基础设施管理",
  },
  {
    id: "media_asset:create",
    label: "创建与上传媒体",
    summary: "上传媒体素材并触发解析",
  },
  {
    id: "enterprise_incident:*",
    label: "安全告警与事件",
    summary: "企业安全告警与事件处置",
  },
];

export const eventOptions = [
  "result.available",
  "run.completed",
  "run.failed",
  "run.cancelled",
];
export const tabs: AccessTabDefinition[] = [
  { id: "foundation", label: "访问底座", icon: Shield },
  { id: "identity", label: "成员与角色", icon: Users },
  { id: "credentials", label: "服务凭据", icon: KeyRound },
  { id: "products", label: "产品授权", icon: ShieldCheck },
  { id: "events", label: "事件回调", icon: BellPlus },
];
