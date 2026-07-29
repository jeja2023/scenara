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
  asset_id: string; kind: "image" | "video" | "document"; filename?: string; content_type: string;
  size_bytes: number; sha256: string; temporary: boolean; created_at: number;
}
export interface MediaSource { source_id: string; name: string; masked_url: string; created_at: number }
export interface Run {
  run_id: string; domain: Domain; pipeline: PipelineRef; asset_id?: string; source_id?: string;
  status: RunStatus; revision: number; progress: number; error_code?: string; termination_reason?: string;
  created_at: number; updated_at: number;
}
export interface RunPage { items: Run[]; offset: number; limit: number; total: number }
export interface VisionObject {
  object_id: string; object_type: string; score?: number;
  bbox?: { x: number; y: number; width: number; height: number };
  attributes: Record<string, unknown>;
}
export interface OcrBlock { block_id: string; text: string; score?: number; reading_order?: number }
export interface ResultEnvelope {
  run_id: string; domain: Domain; pipeline: PipelineRef;
  units: Array<{ unit_id: string; width: number; height: number; objects: VisionObject[] }>;
  domain_payload:
    | { domain: "portrait"; persons: VisionObject[]; faces: VisionObject[]; capabilities: string[] }
    | { domain: "ocr"; text: string; blocks: OcrBlock[]; language?: string };
  models: Array<{ capability: string; model_id: string; version: string; production_ready: boolean }>;
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
