export type Domain = "portrait" | "ocr";
export type RunStatus =
  | "queued"
  | "running"
  | "pausing"
  | "paused"
  | "completed"
  | "failed"
  | "cancelling"
  | "cancelled";

export interface Envelope<T> { schema_version: "1.0"; request_id: string; data: T }
export interface ApiErrorBody { request_id?: string; error?: { code: string; message: string; details?: unknown } }
export interface PipelineRef { pipeline_id: string; version: string }
export interface MediaAsset {
  asset_id: string; kind: "image" | "video" | "document" | "stream"; filename?: string; content_type: string;
  size_bytes: number; sha256: string; preview_object_key?: string | null; preview_content_type?: string | null;
  preview_sha256?: string | null; original_deleted_at?: number | null; temporary: boolean; created_at: number;
}
export interface MediaSource { source_id: string; name: string; masked_url: string; created_at: number }
export interface ModelPackage {
  model_id: string; version: string; capability: string; adapter: string; sha256: string; source_uri: string;
  license_id: string; model_card: string; vram_mb: number; regression_samples: string[]; production_ready: boolean;
}
export interface WebhookSubscription {
  endpoint_id: string; name: string; url: string; event_types: string[]; enabled: boolean; created_at: number;
}
export interface WebhookDelivery {
  delivery_id: string; endpoint_id: string; event_id: string; event_type: string;
  status: "pending" | "delivering" | "delivered" | "dead_letter"; attempts: number;
  status_code?: number | null; last_error?: string | null; created_at: number; updated_at: number;
}
export interface Run {
  run_id: string; domain: Domain; pipeline: PipelineRef; asset_id?: string; source_id?: string;
  status: RunStatus; revision: number; progress: number; error_code?: string; termination_reason?: string;
  created_at: number; updated_at: number;
}
export interface RunPage { items: Run[]; offset: number; limit: number; total: number }
export interface VisionObject {
  object_id: string; object_type: string; score?: number;
  bbox?: { x: number; y: number; width: number; height: number };
  polygon?: Array<{ x: number; y: number }>;
  track_id?: string;
  attributes: Record<string, unknown>;
}
export interface OcrBlock { block_id: string; text: string; score?: number; block_type: "text" | "title" | "paragraph" | "image" | "table"; reading_order?: number }
export interface MediaUnitResult {
  unit_id: string; unit_type: "frame" | "page"; index: number; pts_ms?: number; page_number?: number;
  width: number; height: number; objects: VisionObject[];
}
export interface ModelProvenance {
  capability: string; model_id: string; version: string; sha256?: string; production_ready: boolean;
}
export interface ResultRelation {
  relation_type: string; source_object_id: string; target_object_id: string; score?: number;
}
export interface ResultProvenance {
  source_sha256?: string; generated_by: string; development_substitutes: string[];
}
export interface ResultEnvelope {
  run_id: string; domain: Domain; pipeline: PipelineRef;
  units: MediaUnitResult[];
  domain_payload:
    | { domain: "portrait"; persons: VisionObject[]; faces: VisionObject[]; tracks: Record<string, unknown>[]; capabilities: string[] }
    | { domain: "ocr"; text: string; blocks: OcrBlock[]; language?: string };
  relations: ResultRelation[];
  models: ModelProvenance[];
  provenance: ResultProvenance;
  timings: Record<string, number>;
  warnings: string[]; created_at: number;
}
export interface ResultPage { result: ResultEnvelope; unit_offset: number; unit_limit: number; unit_total: number }
export interface Pipeline {
  pipeline_id: string; version: string; domain: string; status: string; pausable: boolean;
  nodes: Array<{ node_id: string; operator_id: string }>;
}
export interface DomainManifest {
  domain_id: string; display_name: string; schema_version: string; capabilities: string[];
}

export interface FeedbackRecord {
  schema_version: "1.0"; feedback_id: string; kind: string; run_id: string; result_ref: string; media_ref: string;
  pipeline_id: string; pipeline_version: string; model_id: string; model_version: string;
  correction: Record<string, unknown>; authorized_for_training: boolean; deidentified: boolean;
  status: "pending" | "approved" | "rejected"; submitted_by: string; reviewed_by?: string | null;
  review_notes: string; created_at: number; updated_at: number;
}

export interface HardSampleManifest {
  schema_version: "1.0"; manifest_id: string; dataset_id: string; version: string;
  label_schema: string; split: "train" | "validation" | "test"; items: Record<string, unknown>[];
  sha256: string; created_by: string; created_at: number;
}

export interface ModelRelease {
  schema_version: "1.0"; model_id: string; version: string; package_sha256: string; evidence_refs: string[];
  status: "candidate" | "validated" | "approved" | "active" | "retired";
  created_by: string; created_at: number; updated_at: number;
  activated_at?: number | null; retired_at?: number | null;
}

export interface ModelDeploymentEvent {
  event_id: string; model_id: string; version: string; action: string;
  from_status?: ModelRelease["status"] | null; to_status: ModelRelease["status"];
  reason: string; operator_id: string; audit_id: string; created_at: number;
}
