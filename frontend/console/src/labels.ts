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
