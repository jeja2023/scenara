import type {
  FeedbackRecord,
  HardSampleManifest,
  ModelDeploymentEvent,
  ModelRelease,
  TableColumn,
} from "../../types";

export const feedbackColumns: TableColumn<FeedbackRecord>[] = [
  { key: "kind", label: "问题类型", width: "140px" },
  { key: "run_id", label: "运行标识", class: "mono", width: "160px" },
  { key: "model", label: "关联模型", width: "200px" },
  { key: "compliance", label: "合规状态", width: "150px" },
  {
    key: "status",
    label: "审核状态",
    width: "110px",
    align: "center",
    headerAlign: "center",
  },
  {
    key: "actions",
    label: "审批操作",
    width: "120px",
    align: "right",
    headerAlign: "right",
  },
];

export const manifestColumns: TableColumn<HardSampleManifest>[] = [
  { key: "dataset", label: "数据集标识", width: "180px" },
  { key: "version", label: "版本", class: "mono", width: "100px" },
  { key: "split", label: "数据用途", width: "110px" },
  { key: "items", label: "样本条目数", width: "110px" },
  { key: "sha256", label: "校验指纹 (SHA256)", class: "mono", width: "180px" },
  { key: "created_at", label: "生成时间" },
];

export const releaseColumns: TableColumn<ModelRelease>[] = [
  { key: "model_id", label: "模型名称", width: "220px" },
  { key: "version", label: "版本", class: "mono", width: "100px" },
  {
    key: "status",
    label: "准入状态",
    width: "120px",
    align: "center",
    headerAlign: "center",
  },
  { key: "evidence_refs", label: "详情引用", width: "160px" },
  {
    key: "actions",
    label: "准入流转 / 回滚",
    width: "160px",
    align: "right",
    headerAlign: "right",
  },
];

export const eventColumns: TableColumn<ModelDeploymentEvent>[] = [
  { key: "action", label: "操作动作", width: "130px" },
  { key: "model_version", label: "模型与版本", width: "220px" },
  { key: "status_change", label: "状态迁移", width: "190px" },
  { key: "reason", label: "迁移原因说明", width: "200px" },
  { key: "created_at", label: "记录时间" },
];
