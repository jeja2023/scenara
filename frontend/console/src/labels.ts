import type { Domain, RunStatus } from "./types";

const domainLabels: Record<Domain, string> = {
  portrait: "人像",
  ocr: "OCR 文档",
};

const capabilityLabels: Record<string, string> = {
  apparel_attributes: "服饰属性",
  body_reid: "人体重识别",
  face_alignment: "人脸对齐",
  face_detection: "人脸检测",
  face_embedding: "人脸特征",
  gait: "步态分析",
  human_parsing: "人体解析",
  image_region: "图片区域",
  person_detection: "人员检测",
  pose: "姿态估计",
  quality_fusion: "质量融合",
  reading_order: "阅读顺序",
  silhouette_segmentation: "轮廓分割",
  table_region: "表格区域",
  text_detection: "文字检测",
  text_recognition: "文字识别",
  title: "标题",
  paragraph: "段落",
  tracking: "目标跟踪",
};

const pipelineLabels: Record<string, string> = {
  "ocr.document": "OCR 文档识别",
  "portrait.analysis": "人像综合分析",
  "portrait.person-detection": "人员检测",
};

const operatorLabels: Record<string, string> = {
  "platform.media.decode": "媒体解码",
  "platform.media.decode-image": "图片解码",
  "ocr.document-recognition": "文档识别",
  "portrait.full-analysis": "人像综合分析",
  "portrait.person-detection": "人员检测",
};

const objectTypeLabels: Record<string, string> = {
  face: "人脸",
  person: "人员",
  silhouette: "轮廓",
  text: "文字",
  title: "标题",
  paragraph: "段落",
  image_region: "图片区域",
  table_region: "表格区域",
};

const runStatusLabels: Record<RunStatus, string> = {
  queued: "排队中",
  running: "运行中",
  pausing: "暂停中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  cancelling: "取消中",
  cancelled: "已取消",
};

const mediaKindLabels: Record<string, string> = {
  image: "图片",
  video: "视频",
  document: "文档",
  stream: "流",
};

const unitTypeLabels: Record<string, string> = {
  frame: "帧",
  page: "页",
};

const eventTypeLabels: Record<string, string> = {
  "result.available": "结果可用",
  "run.completed": "运行完成",
  "run.failed": "运行失败",
  "run.cancelled": "运行取消",
};

const deliveryStatusLabels: Record<string, string> = {
  pending: "待处理",
  delivering: "投递中",
  delivered: "已投递",
  dead_letter: "死信",
};

const pipelineStatusLabels: Record<string, string> = {
  active: "启用",
  inactive: "停用",
  draft: "草稿",
  validated: "已验证",
  approved: "已批准",
  retired: "已退役",
};

const feedbackKindLabels: Record<string, string> = {
  false_positive: "误检",
  false_negative: "漏检",
  wrong_attribute: "属性错误",
  wrong_identity: "身份匹配错误",
  ocr_correction: "文字更正",
};

const feedbackStatusLabels: Record<string, string> = {
  pending: "待审核",
  approved: "已批准",
  rejected: "已拒绝",
};

const modelReleaseStatusLabels: Record<string, string> = {
  candidate: "候选",
  validated: "已验证",
  approved: "已批准",
  active: "已激活",
  retired: "已退役",
};

const deploymentActionLabels: Record<string, string> = {
  transition: "状态迁移",
  superseded: "被新版本替代",
  rollback: "版本回滚",
  "rollback-retire": "回滚时退役",
};

const runtimeLabels: Record<string, string> = {
  development: "开发",
  production: "生产",
  test: "测试",
  memory: "内存",
  postgres: "PostgreSQL",
  local: "本地对象存储",
  s3: "S3 对象存储",
  inline: "进程内队列",
  redis: "Redis 队列",
};

const enterpriseStateLabels: Record<string, string> = {
  not_configured: "未配置",
  not_installed: "未安装",
  installed: "已安装",
  enabled: "已启用",
  disabled: "已停用",
};

const priorityLabels: Record<string, string> = {
  low: "低",
  normal: "普通",
  high: "高",
  urgent: "紧急",
};

const supportTierLabels: Record<string, string> = {
  basic: "基础",
  standard: "标准",
  premium: "高级",
  enterprise: "企业",
  silver: "银牌",
  gold: "金牌",
  platinum: "铂金",
};

const severityLabels: Record<string, string> = {
  sev1: "一级",
  sev2: "二级",
  sev3: "三级",
  sev4: "四级",
};

const caseStatusLabels: Record<string, string> = {
  open: "已创建",
  pending: "处理中",
  in_progress: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

const entitlementLabels: Record<string, string> = {
  "media_asset:create": "创建媒体资产",
  "enterprise_sla:read": "查看服务等级",
  "enterprise_incident:*": "管理企业事件",
  "enterprise_support:*": "管理支持工单",
  "enterprise_compliance:*": "管理合规证据",
};

const productLabels: Record<string, string> = {
  parse: "Scenara Parse",
  model: "Scenara Model",
  data: "Scenara Data",
  console: "Scenara Console",
  api: "Scenara API",
  sdk: "Scenara SDK",
  index: "Scenara Index",
  search: "Scenara Search",
  flow: "Scenara Flow",
  edge: "Scenara Edge",
  agent: "Scenara Agent",
};

const productSummaryLabels: Record<string, string> = {
  parse: "面向图片、文档、视频与实时流的视觉解析产品模块。",
  model: "提供模型准入、发布治理、回滚和部署证据管理。",
  data: "为视觉智能产品提供媒体、特征、反馈与难例数据闭环。",
  console: "平台运维与各产品模块共用的管理中心。",
  api: "面向平台集成的版本化开放接口。",
  sdk: "面向 Python 与 TypeScript 开发者的接口客户端。",
  index: "承载向量与特征能力，并逐步演进为通用索引底座。",
  search: "面向已解析视觉资产与索引的多模态检索产品。",
  flow: "面向运行、事件回调和人工审核的流程编排产品。",
  edge: "面向离线和设备侧部署的边缘推理产品。",
  agent: "协调解析、检索、流程和审核动作的智能执行层。",
};

const productGateLabels: Record<string, string> = {
  parse: "完成获批模型制品、目标 GPU 和正式评估证据后进入 1.0。",
  model: "明确数据集、实验和算力归属前，训练能力继续由外部平台承担。",
  data: "先建立一等数据集资源，再作为独立数据平台对外提供。",
  console: "持续完善共享身份、权限和产品授权管理。",
  api: "完善应用凭据、权限范围和接口弃用策略后再独立开放。",
  sdk: "保持与 OpenAPI 同步，待产品生命周期独立后再拆分命名空间。",
  index: "先建立租户级索引资源和完整构建生命周期。",
  search: "先完成通用索引资源，再从人像检索扩展到多模态检索。",
  flow: "先保持流水线契约稳定，再开放用户自定义流程。",
  edge: "等待服务端部署与发布证据稳定后启动。",
  agent: "等待流程、检索和可审计动作治理稳定后启动。",
};

const repositoryLabels: Record<string, string> = {
  scenara: "Scenara 平台集成仓库",
  "scenara-model": "Scenara Model 专业仓库",
  "scenara-data": "Scenara Data 专业仓库",
};

const repositorySummaryLabels: Record<string, string> = {
  scenara: "本仓库统一承载视觉解析、共享控制面、开放接口、开发工具包及平台运行底座。",
  "scenara-model": "现有独立仓库专注模型训练、实验、算力调度、评估与不可变模型制品。",
  "scenara-data": "达到拆分门禁后，独立承载数据集、标注、质量、血缘、授权与导出。",
};

const repositoryGateLabels: Record<string, string> = {
  scenara: "保持共享平台契约稳定，仅拆分具备独立负责人和版本化契约的专业负载。",
  "scenara-model": "向平台发布带摘要、模型卡、许可信息和评估证据的不可变模型制品清单。",
  "scenara-data": "数据集、版本、血缘、授权和导出形成稳定归属与契约后再创建独立仓库。",
};

const repositoryLifecycleLabels: Record<string, string> = {
  current: "当前仓库",
  external_existing: "已有独立仓库",
  planned: "规划拆分",
};

const repositoryResponsibilityLabels: Record<string, string> = {
  platform_runtime: "平台运行时",
  media_and_run_lifecycle: "媒体与运行生命周期",
  visual_domain_plugins: "视觉领域插件",
  pipeline_execution: "流水线执行",
  shared_console: "共享管理中心",
  shared_open_api: "共享开放接口",
  shared_sdks: "共享开发工具包",
  shared_iam_authorization_and_audit: "共享身份、授权与审计",
  shared_product_catalog: "共享产品目录",
  model_admission_release_and_deployment: "模型准入、发布与部署",
  operational_feedback_and_hard_sample_export: "业务反馈与难例导出",
  model_training_jobs: "模型训练作业",
  experiment_tracking: "实验跟踪",
  training_compute_scheduling: "训练算力调度",
  training_evaluation: "训练评估",
  immutable_model_artifact_generation: "不可变模型制品生成",
  dataset_catalog_and_versioning: "数据集目录与版本",
  data_labeling_and_review: "数据标注与审核",
  dataset_quality_and_lineage: "数据质量与血缘",
  dataset_authorization_and_export: "数据授权与导出",
  operational_media_run_and_result_storage: "业务媒体、运行与结果存储",
};

const repositoryBoundaryRuleLabels: Record<string, string> = {
  versioned_contracts_only: "仅通过版本化契约协作",
  no_shared_database: "禁止跨仓库共享数据库",
  no_cross_repository_source_imports: "禁止跨仓库源码导入",
  immutable_artifact_references: "制品必须使用不可变引用",
};

const repositoryContractLabels: Record<string, string> = {
  "model-package-admission": "模型制品准入",
  "hard-sample-handoff": "难例数据交接",
  "dataset-version-input": "训练数据版本输入",
  "deployment-feedback": "部署反馈事件",
};

const accessCapabilityLabels: Record<string, { name: string; summary: string; nextGate: string }> = {
  tenant_project_context: {
    name: "租户与项目上下文",
    summary: "每个请求和身份资源都受租户与项目标识约束。",
    nextGate: "租户开通规则稳定后，补充项目暂停和删除等生命周期控制。",
  },
  api_authentication: {
    name: "接口认证",
    summary: "生产环境支持平台根令牌和可撤销、可收窄权限的服务账号 API 密钥。",
    nextGate: "服务账号与 API 密钥管理稳定后，再接入单点登录和开放授权。",
  },
  policy_provider: {
    name: "权限策略",
    summary: "运行服务通过共享策略提供者执行授权和配额判断。",
    nextGate: "继续完善角色与产品授权分配，不把权限绑定在单一许可证文档中。",
  },
  product_entitlements: {
    name: "产品授权",
    summary: "项目产品授权和服务凭据的产品范围在共享策略边界统一执行。",
    nextGate: "要求后续每个产品模块登记资源与产品的策略映射。",
  },
  audit_trail: {
    name: "审计轨迹",
    summary: "平台服务会为敏感操作记录审计事件。",
    nextGate: "在控制台提供租户级审计检索、导出审批和保留策略。",
  },
  role_management: {
    name: "角色管理",
    summary: "用户、角色和项目成员关系由所有 Scenara 产品共享并持久化。",
    nextGate: "在交互式用户认证时解析角色绑定和有效权限。",
  },
  sso: {
    name: "单点登录",
    summary: "规划中的企业身份联合能力，面向操作人员和服务用户。",
    nextGate: "先完善角色管理和服务账号底座，再接入单点登录。",
  },
};

const scopeLabels: Record<string, string> = {
  "*": "全部权限",
  "iam:*": "管理身份与访问",
  "iam:read": "查看身份与访问",
  "platform:*": "管理平台",
  "media_asset:create": "创建媒体资产",
  "enterprise_sla:read": "查看服务等级",
  "enterprise_incident:*": "管理企业事件",
  "enterprise_support:*": "管理支持工单",
  "enterprise_compliance:*": "管理合规证据",
};

const runErrorLabels: Record<string, string> = {
  QUEUE_UNAVAILABLE: "运行队列不可用",
  DOMAIN_UNAVAILABLE: "所选领域不可用",
  PIPELINE_EXECUTION_FAILED: "流水线执行失败",
};

const terminationReasonLabels: Record<string, string> = {
  source_ended: "媒体源已结束",
  reconnect_exhausted: "媒体源重连次数已用尽",
  max_units_reached: "已达到最大处理单元数",
  cancelled_by_user: "已由用户取消",
};

export function labelDomain(value: Domain | string): string {
  return domainLabels[value as Domain] ?? "其他领域";
}

export function labelCapability(value: string): string {
  return capabilityLabels[value] ?? "未命名能力";
}

export function labelPipeline(value: string): string {
  return pipelineLabels[value] ?? "自定义流水线";
}

export function labelOperator(value: string): string {
  return operatorLabels[value] ?? "自定义处理节点";
}

export function labelObjectType(value: string): string {
  return objectTypeLabels[value] ?? "其他对象";
}

export function labelRunStatus(value: RunStatus | string): string {
  return runStatusLabels[value as RunStatus] ?? "未知状态";
}

export function labelMediaKind(value: string): string {
  return mediaKindLabels[value] ?? "其他媒体";
}

export function labelUnitType(value: string): string {
  return unitTypeLabels[value] ?? "其他单元";
}

export function labelEventType(value: string): string {
  return eventTypeLabels[value] ?? "其他事件";
}

export function labelDeliveryStatus(value: string): string {
  return deliveryStatusLabels[value] ?? "未知状态";
}

export function labelPipelineStatus(value: string): string {
  return pipelineStatusLabels[value] ?? "未知状态";
}

export function labelFeedbackKind(value: string): string {
  return feedbackKindLabels[value] ?? "其他问题";
}

export function labelFeedbackStatus(value: string): string {
  return feedbackStatusLabels[value] ?? "未知状态";
}

export function labelModelReleaseStatus(value: string): string {
  return modelReleaseStatusLabels[value] ?? "未知状态";
}

export function labelDeploymentAction(value: string): string {
  return deploymentActionLabels[value] ?? "其他操作";
}

export function labelRuntime(value: string): string {
  return runtimeLabels[value] ?? "未识别配置";
}

export function labelEnterpriseState(value: string): string {
  return enterpriseStateLabels[value] ?? "未知状态";
}

export function labelPriority(value: string): string {
  return priorityLabels[value] ?? "未指定";
}

export function labelSupportTier(value: string): string {
  return supportTierLabels[value] ?? "自定义等级";
}

export function labelSeverity(value: string): string {
  return severityLabels[value] ?? "未指定";
}

export function labelCaseStatus(value: string): string {
  return caseStatusLabels[value] ?? "未知状态";
}

export function labelEntitlement(value: string): string {
  return entitlementLabels[value] ?? "自定义权益";
}

export function labelProduct(value: string): string {
  return productLabels[value] ?? "Scenara 自定义产品";
}

export function labelProductSummary(value: string): string {
  return productSummaryLabels[value] ?? "该产品尚未提供中文说明。";
}

export function labelProductGate(value: string): string {
  return productGateLabels[value] ?? "等待产品负责人补充下一阶段门禁。";
}

export function labelRepository(value: string): string {
  return repositoryLabels[value] ?? "Scenara 专业仓库";
}

export function labelRepositorySummary(value: string): string {
  return repositorySummaryLabels[value] ?? "该仓库尚未提供中文职责说明。";
}

export function labelRepositoryGate(value: string): string {
  return repositoryGateLabels[value] ?? "等待仓库负责人补充下一阶段门禁。";
}

export function labelRepositoryLifecycle(value: string): string {
  return repositoryLifecycleLabels[value] ?? "状态待定";
}

export function labelRepositoryResponsibility(value: string): string {
  return repositoryResponsibilityLabels[value] ?? "待定义职责";
}

export function labelRepositoryBoundaryRule(value: string): string {
  return repositoryBoundaryRuleLabels[value] ?? "遵循平台仓库边界";
}

export function labelRepositoryContract(value: string): string {
  return repositoryContractLabels[value] ?? "版本化集成契约";
}

export function labelAccessCapability(value: string): { name: string; summary: string; nextGate: string } {
  return accessCapabilityLabels[value] ?? {
    name: "未命名访问能力",
    summary: "该能力尚未提供中文说明。",
    nextGate: "等待平台负责人补充下一阶段门禁。",
  };
}

export function labelPolicyProvider(value: string): string {
  if (value === "development-open") return "开发开放策略";
  if (value.startsWith("enterprise-license:")) return "企业许可证策略";
  return "自定义权限策略";
}

export function labelEntitlementSource(value: string): string {
  return ({ manual: "手动配置", enterprise_license: "企业许可证", system: "系统配置" } as Record<string, string>)[value]
    ?? "其他来源";
}

export function labelScope(value: string): string {
  return scopeLabels[value] ?? "自定义权限";
}

export function labelRunError(value: string): string {
  return runErrorLabels[value] ?? "运行失败";
}

export function labelTerminationReason(value?: string | null): string {
  if (!value) return "未提供原因";
  if (terminationReasonLabels[value]) return terminationReasonLabels[value];
  return /[\u3400-\u9fff]/u.test(value) ? value : "运行因技术原因提前结束";
}

export function labelWarning(value: string): string {
  if (value === "gait_requires_at_least_8_frames") return "步态分析至少需要 8 帧画面";
  if (value.startsWith("development_substitute:")) {
    return `使用开发替代能力：${labelCapability(value.slice("development_substitute:".length))}`;
  }
  if (value.startsWith("development_substitutes:")) {
    return `使用开发替代能力：${value.slice("development_substitutes:".length).split(",").map(labelCapability).join("、")}`;
  }
  if (value.startsWith("media_termination:")) {
    return `媒体处理提前结束：${labelTerminationReason(value.slice("media_termination:".length))}`;
  }
  return /[\u3400-\u9fff]/u.test(value) ? value : "运行产生技术告警，请查看原始结果";
}

export function labelSystemReason(value: string): string {
  return /[\u3400-\u9fff]/u.test(value) ? value : "系统执行状态变更";
}

export function labelVersion(value: string): string {
  const development = value.match(/^(\d+\.\d+\.\d+)(?:\.dev|-dev\.)(\d+)$/u);
  return development ? `${development[1]} 开发版${development[2] === "0" ? "" : ` ${development[2]}`}` : value;
}
