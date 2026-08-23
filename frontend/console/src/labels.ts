import type { Domain, RunStatus } from "./types";

const domainLabels: Record<string, string> = {
  portrait: "人像",
  ocr: "OCR 文档",
  behavior: "行为识别",
  fashion: "服饰风格",
};

const domainDescriptionLabels: Record<string, string> = {
  portrait: "检测人员并分析人像相关的视觉特征。",
  ocr: "从图片、视频和文档中提取文字、版面结构与阅读顺序。",
  behavior: "识别视频中的人物动作和行为模式,支持50+常见行为类别。",
  fashion: "识别 Cosplay 角色、服装风格(JK、Lolita、汉服等)和配饰,支持二次元文化和时尚分析。",
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
  action_recognition: "动作识别",
  activity_detection: "活动检测",
  temporal_segmentation: "时序分割",
  anomaly_detection: "异常检测",
  cosplay_recognition: "Cosplay 识别",
  clothing_style_detection: "服装风格检测",
  accessory_detection: "配饰识别",
  fashion_attribute_analysis: "服饰属性分析",
};

const pipelineLabels: Record<string, string> = {
  "ocr.document": "OCR 文档识别",
  "portrait.analysis": "人像综合分析",
  "portrait.person-detection": "人员检测",
  "behavior.recognition": "行为识别",
  "fashion.recognition": "服饰风格识别",
};

const operatorLabels: Record<string, string> = {
  "platform.media.decode": "媒体解码",
  "platform.media.decode-image": "图片解码",
  "ocr.document-recognition": "文档识别",
  "portrait.full-analysis": "人像综合分析",
  "portrait.person-detection": "人员检测",
  "behavior.action-recognition": "行为动作识别",
  "fashion.style-recognition": "服饰风格识别",
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
  stream: "视频流",
};

const unitTypeLabels: Record<string, string> = {
  frame: "帧",
  page: "页",
};

const eventTypeLabels: Record<string, string> = {
  "result.delta": "增量结果",
  "stream.segment.started": "流分段开始",
  "stream.segment.completed": "流分段完成",
  "stream.session.error": "流会话异常",
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
  console: "Scenara 控制台",
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
  scenara:
    "本仓库统一承载视觉解析、共享控制面、开放接口、开发工具包及平台运行底座。",
  "scenara-model":
    "现有独立仓库专注模型训练、实验、算力调度、评估与不可变模型制品。",
  "scenara-data":
    "现有独立仓库专注数据集目录与版本、标注审核、质量血缘、授权与难例数据闭环。",
};

const repositoryGateLabels: Record<string, string> = {
  scenara: "保持共享平台契约稳定，仅拆分具备独立负责人和版本化契约的专业负载。",
  "scenara-model":
    "向平台发布带摘要、模型卡、许可信息和评估证据的不可变模型制品清单。",
  "scenara-data":
    "完成数据迁移影子读核验、不可变版本摘要及服务切流门禁后接入生产流量。",
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

const accessCapabilityLabels: Record<
  string,
  { name: string; summary: string; nextGate: string }
> = {
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
  max_units_reached: "历史运行达到旧版处理单元上限",
  sample_window_completed: "已完成指定采样时间窗口",
  segment_window_completed: "已完成当前流分段并自动接续",
  cancelled_by_user: "已由用户取消",
};

const sampleStrategyLabels: Record<string, string> = {
  interval: "固定间隔",
  keyframe: "关键帧",
  scene_change: "场景切换",
  uniform: "均匀分布",
};

const portraitMaturityLabels: Record<string, string> = {
  available: "可用",
  partial: "部分可用",
  seed: "种子能力",
  planned: "规划中",
  external: "外部仓库承担",
};

const portraitReadinessLabels: Record<string, string> = {
  ready: "已就绪",
  fallback: "开发替代",
  placeholder: "占位实现",
  not_configured: "未配置",
};

const portraitModuleLabels: Record<string, string> = {
  data_governance: "数据治理",
  annotation: "标注平台",
  training: "模型训练",
  algorithms: "人像算法",
  vector_retrieval: "向量检索",
  mlops: "模型运维",
};

const portraitModuleSummaryLabels: Record<string, string> = {
  data_governance: "建立版本不可变、血缘完整的人像训练与评估数据资产。",
  annotation: "支持图片、视频和流截帧的标注与质量复核，打通难例闭环。",
  training: "统一训练框架覆盖检测、识别、姿态、行人重识别与属性任务。",
  algorithms:
    "构建完整人像能力矩阵：人员检测、人脸检测与识别、姿态、步态与外观属性。",
  vector_retrieval: "支撑海量人像库的高速近似检索、跨摄像头关联与聚类。",
  mlops: "覆盖实验、准入、部署、监控与反馈的模型全生命周期治理。",
};

const portraitModuleGateLabels: Record<string, string> = {
  data_governance:
    "数据集、版本、血缘、授权与导出形成稳定归属后再创建独立数据仓库。",
  annotation: "先完成数据治理底座，标注工具集成属于独立数据仓库的职责范围。",
  training: "由训练仓库发布带摘要、模型卡和评估证据的不可变模型制品清单。",
  algorithms: "通过模型准入接口提交全部能力的正式制品，附摘要与模型卡。",
  vector_retrieval: "把既有向量后端迁移为平台特征存储协议的标准实现。",
  mlops: "先以单节点推理完成 1.0 资格验证，再接入高并发推理服务。",
};

const portraitAssetLabels: Record<string, string> = {
  data_lake: "人像数据湖",
  foundation_model: "人像基础模型",
  intelligence_engine: "人像智能引擎",
};

const portraitAssetSummaryLabels: Record<string, string> = {
  data_lake: "统一管理原始媒体、标注结果、特征向量、质量标签与版本血缘。",
  foundation_model:
    "持续训练覆盖检测、识别、属性、姿态、重识别与步态的多任务模型，替代割裂的小模型。",
  intelligence_engine:
    "融合检索、聚类、知识图谱、事件分析与持续学习，形成可持续演进的平台能力。",
};

const portraitAssetGateLabels: Record<string, string> = {
  data_lake:
    "先建成数据治理与标注能力，数据湖从稳定的数据集版本与血缘归属中沉淀。",
  foundation_model:
    "先让各独立任务模型全部达到就绪，再在后续版本收敛为共享骨干网络。",
  intelligence_engine: "先完成向量后端迁移并交付人脸与人体多模态融合检索。",
};

const portraitCapabilityLabels: Record<string, string> = {
  person_detection: "人员检测",
  body_embedding: "人体重识别特征",
  face_detection: "人脸检测",
  face_embedding: "人脸识别特征",
  pose: "姿态估计",
  gait: "步态识别",
  appearance: "外观属性",
};

export function labelPortraitMaturity(value: string): string {
  return portraitMaturityLabels[value] ?? "未知成熟度";
}

export function labelPortraitReadiness(value: string): string {
  return portraitReadinessLabels[value] ?? "未知状态";
}

export function labelPortraitModule(value: string): string {
  return portraitModuleLabels[value] ?? "其他能力模块";
}

export function labelPortraitModuleSummary(value: string): string {
  return portraitModuleSummaryLabels[value] ?? "该模块尚未提供中文说明。";
}

export function labelPortraitModuleGate(value: string): string {
  return portraitModuleGateLabels[value] ?? "等待模块负责人补充下一阶段门禁。";
}

export function labelPortraitAsset(value: string): string {
  return portraitAssetLabels[value] ?? "其他平台资产";
}

export function labelPortraitAssetSummary(value: string): string {
  return portraitAssetSummaryLabels[value] ?? "该资产尚未提供中文说明。";
}

export function labelPortraitAssetGate(value: string): string {
  return portraitAssetGateLabels[value] ?? "等待资产负责人补充下一阶段门禁。";
}

export function labelPortraitCapability(value: string): string {
  return portraitCapabilityLabels[value] ?? "未命名能力";
}

function humanizeIdentifier(value: string): string {
  const words = value
    .replace(/[_.-]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return words.length
    ? words.map((word) => word[0]?.toUpperCase() + word.slice(1)).join(" ")
    : "未命名";
}

export function labelDomain(value: Domain | string): string {
  return domainLabels[value] ?? humanizeIdentifier(value);
}

export function labelDomainDisplayName(
  value: Domain | string,
  displayName?: string,
): string {
  if (domainLabels[value]) return domainLabels[value];
  return displayName && /[\u3400-\u9fff]/u.test(displayName)
    ? displayName
    : "自定义领域";
}

export function labelDomainDescription(
  value: Domain | string,
  description?: string,
): string {
  if (domainDescriptionLabels[value]) return domainDescriptionLabels[value];
  return description && /[\u3400-\u9fff]/u.test(description)
    ? description
    : "该领域已接入统一解析工作区，可通过已启用的流水线处理支持的数据类型。";
}

export function labelCapability(value: string): string {
  return capabilityLabels[value] ?? "未命名能力";
}

export function labelPipeline(value: string): string {
  return pipelineLabels[value] ?? humanizeIdentifier(value);
}

export function labelPipelineDisplayName(value: string): string {
  return pipelineLabels[value] ?? "自定义解析流水线";
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
  return mediaKindLabels[value] ?? "其他类型";
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

export function labelAccessCapability(value: string): {
  name: string;
  summary: string;
  nextGate: string;
} {
  return (
    accessCapabilityLabels[value] ?? {
      name: "未命名访问能力",
      summary: "该能力尚未提供中文说明。",
      nextGate: "等待平台负责人补充下一阶段门禁。",
    }
  );
}

export function labelPolicyProvider(value: string): string {
  if (value === "development-open") return "开发开放策略";
  if (value.startsWith("enterprise-license:")) return "企业许可证策略";
  return "自定义权限策略";
}

export function labelEntitlementSource(value: string): string {
  return (
    (
      {
        manual: "手动配置",
        enterprise_license: "企业许可证",
        system: "系统配置",
      } as Record<string, string>
    )[value] ?? "其他来源"
  );
}

export function labelScope(value: string): string {
  return scopeLabels[value] ?? "自定义权限";
}

export function labelRunError(value: string): string {
  return runErrorLabels[value] ?? "运行失败";
}

export function labelSampleStrategy(value?: string | null): string {
  if (!value) return "固定间隔";
  return sampleStrategyLabels[value] ?? "自定义采样策略";
}

export function labelTerminationReason(value?: string | null): string {
  if (!value) return "未提供原因";
  if (terminationReasonLabels[value]) return terminationReasonLabels[value];
  return /[\u3400-\u9fff]/u.test(value) ? value : "运行因技术原因提前结束";
}

export function labelWarning(value: string): string {
  if (value === "gait_requires_at_least_8_frames")
    return "步态分析至少需要 8 帧画面";
  if (value === "artifact_crop_quota_reached") {
    return "特征裁剪图片数量已达到本次运行的上限，部分对象没有生成裁剪图；如需完整覆盖，请提高特征图片配额或缩小分析范围。";
  }
  if (value === "artifact_frame_quota_reached") {
    return "该历史运行创建时仍启用了结果帧数量上限，部分单元没有保存回放图；新运行已取消此上限，请重新解析以生成完整结果帧。";
  }
  if (value === "artifact_quota_reached") {
    return "特征图片数量已达到本次运行的上限，部分对象没有生成裁剪图；如需完整覆盖，请提高特征图片配额或缩小分析范围。";
  }
  if (value === "artifact_storage_unavailable") {
    return "特征图片写入对象存储失败，解析结果不受影响，但部分裁剪图无法查看。";
  }
  if (value === "media_termination:max_units_reached") {
    return "该历史运行创建时仍启用了处理单元数量上限；新运行已取消此限制，请重新解析以处理完整输入。";
  }
  if (value === "media_termination:source_ended") {
    return "媒体源已正常读完，本次任务已完成全部可读取内容。";
  }
  if (value === "media_termination:segment_window_completed") {
    return "当前实时流时间窗口已归档，系统正在同一会话中接续下一段。";
  }
  if (value.startsWith("development_substitute:")) {
    return `使用开发替代能力：${labelCapability(value.slice("development_substitute:".length))}`;
  }
  if (value.startsWith("development_substitutes:")) {
    return `使用开发替代能力：${value.slice("development_substitutes:".length).split(",").map(labelCapability).join("、")}`;
  }
  if (value.startsWith("media_termination:")) {
    return `媒体处理提前结束：${labelTerminationReason(value.slice("media_termination:".length))}`;
  }
  return /[\u3400-\u9fff]/u.test(value)
    ? value
    : "运行产生技术告警，请查看原始结果";
}

export function labelSystemReason(value: string): string {
  return /[\u3400-\u9fff]/u.test(value) ? value : "系统执行状态变更";
}

export function labelVersion(value: string): string {
  const development = value.match(/^(\d+\.\d+\.\d+)(?:\.dev|-dev\.)(\d+)$/u);
  return development
    ? `${development[1]} 开发版${development[2] === "0" ? "" : ` ${development[2]}`}`
    : value;
}
