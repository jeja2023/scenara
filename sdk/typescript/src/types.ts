export type Domain = "portrait" | "ocr";
export type RunStatus = "queued" | "running" | "pausing" | "paused" | "completed" | "failed" | "cancelling" | "cancelled";
export type FeedbackStatus = "pending" | "approved" | "rejected";
export type ModelReleaseStatus = "candidate" | "validated" | "approved" | "active" | "retired";

export interface PipelineRef {
  pipeline_id: string;
  version: string;
}

export interface MediaAsset {
  asset_id: string;
  kind: "image" | "video" | "document";
  filename?: string | null;
  content_type: string;
  size_bytes: number;
  sha256: string;
  preview_object_key?: string | null;
  preview_content_type?: string | null;
  preview_sha256?: string | null;
  original_deleted_at?: number | null;
  temporary: boolean;
  created_at: number;
}

export interface ModelPackage {
  model_id: string;
  version: string;
  capability: string;
  adapter: string;
  sha256: string;
  source_uri: string;
  license_id: string;
  model_card: string;
  vram_mb: number;
  regression_samples: string[];
  production_ready: boolean;
}

export interface WebhookSubscription {
  endpoint_id: string;
  name: string;
  url: string;
  event_types: string[];
  enabled: boolean;
  created_at: number;
}

export interface WebhookDelivery {
  delivery_id: string;
  endpoint_id: string;
  event_id: string;
  event_type: string;
  status: "pending" | "delivering" | "delivered" | "dead_letter";
  attempts: number;
  status_code?: number | null;
  last_error?: string | null;
  created_at: number;
  updated_at: number;
}

export interface FeedbackRecord {
  schema_version: "1.0";
  feedback_id: string;
  kind: string;
  run_id: string;
  result_ref: string;
  media_ref: string;
  pipeline_id: string;
  pipeline_version: string;
  model_id: string;
  model_version: string;
  correction: Record<string, unknown>;
  authorized_for_training: boolean;
  deidentified: boolean;
  status: FeedbackStatus;
  submitted_by: string;
  reviewed_by?: string | null;
  review_notes: string;
  created_at: number;
  updated_at: number;
}

export interface HardSampleManifest {
  schema_version: "1.0";
  manifest_id: string;
  dataset_id: string;
  version: string;
  label_schema: string;
  split: "train" | "validation" | "test";
  items: Record<string, unknown>[];
  sha256: string;
  created_by: string;
  created_at: number;
}

export interface ModelRelease {
  schema_version: "1.0";
  model_id: string;
  version: string;
  package_sha256: string;
  evidence_refs: string[];
  status: ModelReleaseStatus;
  created_by: string;
  created_at: number;
  updated_at: number;
  activated_at?: number | null;
  retired_at?: number | null;
}

export interface ModelDeploymentEvent {
  schema_version: "1.0";
  event_id: string;
  model_id: string;
  version: string;
  action: string;
  from_status?: ModelReleaseStatus | null;
  to_status: ModelReleaseStatus;
  reason: string;
  operator_id: string;
  audit_id: string;
  created_at: number;
}

export interface Run {
  run_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  asset_id?: string | null;
  source_id?: string | null;
  status: RunStatus;
  revision: number;
  progress: number;
  error_code?: string | null;
  termination_reason?: string | null;
  created_at: number;
  updated_at: number;
}

export interface RunPage {
  items: Run[];
  offset: number;
  limit: number;
  total: number;
}

export interface ResultEnvelope {
  schema_version: string;
  run_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  units: Record<string, unknown>[];
  domain_payload: Record<string, unknown>;
  models: Record<string, unknown>[];
  timings: Record<string, number>;
  warnings: string[];
  created_at: number;
}

export interface ResultPage {
  result: ResultEnvelope;
  unit_offset: number;
  unit_limit: number;
  unit_total: number;
}

export interface ParseImageResponse {
  asset: MediaAsset;
  run: Run;
  result: ResultEnvelope | null;
}
