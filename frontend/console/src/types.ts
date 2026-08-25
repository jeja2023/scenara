export type Domain = string;
export type MediaKind = "image" | "video" | "document" | "stream";
export type RunStatus =
  | "queued"
  | "running"
  | "pausing"
  | "paused"
  | "completed"
  | "failed"
  | "cancelling"
  | "cancelled";

export interface Envelope<T> {
  schema_version: "1.0";
  request_id: string;
  data: T;
}
export interface ApiErrorBody {
  request_id?: string;
  error?: { code: string; message: string; details?: unknown };
}
export interface PipelineRef {
  pipeline_id: string;
  version: string;
}
export type SampleStrategy =
  "interval" | "keyframe" | "scene_change" | "uniform";
export interface MediaTechnicalMetadata {
  format?: string | null;
  container?: string | null;
  codec?: string | null;
  width?: number | null;
  height?: number | null;
  fps?: number | null;
  frame_count?: number | null;
  duration_ms?: number | null;
  page_count?: number | null;
  sampled_units?: number | null;
  frames_read?: number | null;
  sample_interval_ms?: number | null;
  sample_strategy?: SampleStrategy | null;
  sample_start_ms?: number | null;
  sample_end_ms?: number | null;
  keyframe_count?: number | null;
  scene_change_count?: number | null;
  frame_max_edge?: number | null;
  decode_seek_used?: boolean | null;
  reconnect_count?: number | null;
  elapsed_ms?: number | null;
  timestamp_source?: "decoder_pts" | "position_msec" | "monotonic_clock" | null;
}
export interface MediaAsset {
  asset_id: string;
  kind: MediaKind;
  filename?: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  preview_object_key?: string | null;
  preview_content_type?: string | null;
  preview_sha256?: string | null;
  original_deleted_at?: number | null;
  metadata: MediaTechnicalMetadata;
  temporary: boolean;
  created_at: number;
}
export interface MediaSource {
  source_id: string;
  name: string;
  masked_url: string;
  metadata: Record<string, unknown>;
  created_at: number;
}
export interface MediaSourceProbe {
  source_id: string;
  reachable: boolean;
  latency_ms: number;
  metadata: MediaTechnicalMetadata;
  checked_at: number;
}

export type DatasetStatus = "draft" | "active" | "archived";
export type DatasetVersionStatus =
  "draft" | "validated" | "published" | "retired";

export interface DatasetRecord {
  dataset_id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  description: string;
  status: DatasetStatus;
  metadata: Record<string, unknown>;
  created_at: number;
  updated_at: number;
}

export interface DatasetVersion {
  version_id: string;
  dataset_id: string;
  tenant_id: string;
  project_id: string;
  version: string;
  status: DatasetVersionStatus;
  manifest_sha256: string;
  asset_ids: string[];
  item_count: number;
  quality_score: number | null;
  lineage: Record<string, unknown>;
  annotation_summary: Record<string, unknown>;
  created_by: string;
  created_at: number;
  updated_at: number;
}

export type TrajectoryStatus = "auto" | "confirmed" | "rejected";

export type TrajectoryMatchMethod = "new_identity" | "reid" | "manual";

export interface CameraTransition {
  from_camera_id: string;
  to_camera_id: string;
  min_seconds: number;
  max_seconds: number | null;
}

export interface CameraRecord {
  camera_id: string;
  tenant_id: string;
  project_id: string;
  display_name: string;
  location: string;
  auto_registered: boolean;
  metadata: Record<string, unknown>;
  created_at: number;
  updated_at: number;
}

export interface LongTermIdentity {
  identity_id: string;
  tenant_id: string;
  project_id: string;
  display_name: string;
  status: TrajectoryStatus;
  modalities: string[];
  feature_space_ids: Record<string, string>;
  camera_ids: string[];
  segment_count: number;
  first_seen_at: number;
  last_seen_at: number;
  last_camera_id: string;
  metadata: Record<string, unknown>;
  created_at: number;
  updated_at: number;
}

export interface TrajectorySegment {
  segment_id: string;
  identity_id: string;
  tenant_id: string;
  project_id: string;
  run_id: string;
  source_id: string;
  asset_id: string;
  camera_id: string;
  track_id: string;
  frame_count: number;
  track_quality: number;
  first_seen_at: number;
  last_seen_at: number;
  first_pts_ms: number | null;
  last_pts_ms: number | null;
  match_method: TrajectoryMatchMethod;
  match_score: number;
  match_scores: Record<string, number>;
  feature_ids: Record<string, string>;
  metadata: Record<string, unknown>;
  created_at: number;
}

export interface TimelineEntry {
  segment_id: string;
  camera_id: string;
  camera_name: string;
  run_id: string;
  first_seen_at: number;
  last_seen_at: number;
  duration_seconds: number;
  match_method: TrajectoryMatchMethod;
  match_score: number;
  transition_seconds: number | null;
}

export interface AuditEvent {
  event_id: string;
  tenant_id: string;
  project_id: string;
  principal_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  request_id: string | null;
  evidence: Record<string, unknown>;
  created_at: number;
}

export interface SavedSearch {
  saved_search_id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  description: string;
  mode: "text" | "portrait";
  definition: Record<string, unknown>;
  created_by: string;
  created_at: number;
  updated_at: number;
  last_run_at: number | null;
}
export interface ModelPackage {
  schema_version: "1.0";
  model_id: string;
  version: string;
  capability: string;
  adapter: string;
  runtime_model_id: string;
  sha256: string;
  source_uri: string;
  license_id: string;
  model_card: string;
  evaluation_evidence: string[];
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
export interface Run {
  run_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  asset_id?: string;
  source_id?: string;
  stream_session_id?: string | null;
  stream_segment_index?: number | null;
  previous_run_id?: string | null;
  next_run_id?: string | null;
  status: RunStatus;
  revision: number;
  progress: number;
  error_code?: string;
  termination_reason?: string;
  parameters: Record<string, unknown>;
  priority: number;
  created_at: number;
  updated_at: number;
  started_at?: number | null;
  completed_at?: number | null;
}
export interface RunPage {
  items: Run[];
  offset: number;
  limit: number;
  total: number;
}
export interface StreamSession {
  session_id: string;
  source_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  status: "active" | "completed" | "failed" | "cancelled";
  current_run_id: string;
  segment_count: number;
  created_at: number;
  updated_at: number;
}
export interface VisionObject {
  object_id: string;
  object_type: string;
  score?: number;
  bbox?: { x: number; y: number; width: number; height: number };
  polygon?: Array<{ x: number; y: number }>;
  track_id?: string;
  attributes: Record<string, unknown>;
  /** 该对象裁剪图在 ResultEnvelope.artifacts 中的标识。 */
  crop_artifact_id?: string | null;
}
export interface OcrBlock {
  block_id: string;
  text: string;
  score?: number;
  block_type: "text" | "title" | "paragraph" | "image" | "table";
  reading_order?: number;
  polygon?: Array<{ x: number; y: number }>;
}
export interface MediaUnitResult {
  unit_id: string;
  unit_type: "frame" | "page";
  index: number;
  pts_ms?: number;
  page_number?: number;
  width: number;
  height: number;
  objects: VisionObject[];
  /** 该单元完整原图在 ResultEnvelope.artifacts 中的标识。 */
  frame_artifact_id?: string | null;
}
export interface ResultArtifact {
  artifact_id: string;
  artifact_type: string;
  object_key: string;
  content_type: string;
  sha256: string;
}
export interface ModelProvenance {
  capability: string;
  model_id: string;
  version: string;
  sha256?: string;
  production_ready: boolean;
}
export interface ResultRelation {
  relation_type: string;
  source_object_id: string;
  target_object_id: string;
  score?: number;
}
export interface ResultProvenance {
  source_sha256?: string;
  generated_by: string;
  development_substitutes: string[];
}
export interface ResultEnvelope {
  run_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  asset_id?: string | null;
  source_id?: string | null;
  units: MediaUnitResult[];
  domain_payload: {
    domain: Domain;
    [key: string]: unknown;
  };
  relations: ResultRelation[];
  artifacts: ResultArtifact[];
  models: ModelProvenance[];
  provenance: ResultProvenance;
  timings: Record<string, number>;
  media_metadata: MediaTechnicalMetadata;
  warnings: string[];
  created_at: number;
}
export interface ResultPage {
  result: ResultEnvelope;
  unit_offset: number;
  unit_limit: number;
  unit_total: number;
}
export interface ResultSummary {
  result_id: string;
  run_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  status: RunStatus;
  asset_id?: string | null;
  source_id?: string | null;
  media_kind?: MediaKind | null;
  resource_name?: string | null;
  unit_count: number;
  object_count: number;
  person_count: number;
  face_count: number;
  ocr_block_count: number;
  text_length: number;
  warning_count: number;
  index_status: "ready" | "partial";
  created_at: number;
}
export interface ResultSummaryPage {
  items: ResultSummary[];
  offset: number;
  limit: number;
  total: number;
}
export interface Pipeline {
  pipeline_id: string;
  version: string;
  domain: string;
  status: string;
  pausable: boolean;
  nodes: Array<{ node_id: string; operator_id: string }>;
  allowed_parameters?: string[];
  parameter_schema?: Record<string, PipelineParameterDefinition>;
}
export interface PipelineParameterDefinition {
  label: string;
  control: "boolean" | "integer" | "number" | "select" | "text";
  default?: unknown;
  minimum?: number | null;
  maximum?: number | null;
  step?: number | null;
  options?: string[];
  placeholder?: string | null;
  advanced?: boolean;
  media_kinds?: MediaKind[];
}
export interface DomainManifest {
  domain_id: string;
  display_name: string;
  schema_version: string;
  capabilities: string[];
  console_route: string;
  description?: string;
  supported_media_kinds?: MediaKind[];
  default_pipeline_id?: string | null;
  navigation_order?: number;
}

export type ProductLayer =
  "product_module" | "control_plane" | "developer_surface" | "foundation";
export type ProductMaturity = "available" | "seed" | "planned" | "gated";
export type AccessCapabilityStatus = "available" | "seed" | "planned" | "gated";

export interface ProductCatalogItem {
  product_id: string;
  name: string;
  layer: ProductLayer;
  maturity: ProductMaturity;
  summary: string;
  current_scope: string[];
  not_in_scope_yet: string[];
  console_route?: string | null;
  api_paths: string[];
  depends_on: string[];
  next_gate: string;
}

export type RepositoryKind = "platform_integration" | "specialized_product";
export type RepositoryLifecycle = "current" | "external_existing" | "planned";
export type RepositoryBoundaryRule =
  | "versioned_contracts_only"
  | "no_shared_database"
  | "no_cross_repository_source_imports"
  | "immutable_artifact_references";
export type RepositoryContractTransport =
  "versioned_api" | "event" | "immutable_manifest";

export interface RepositoryTopologyItem {
  repository_id: string;
  name: string;
  kind: RepositoryKind;
  lifecycle: RepositoryLifecycle;
  current_repository: boolean;
  primary_product_ids: string[];
  integration_product_ids: string[];
  responsibilities: string[];
  excluded_responsibilities: string[];
  next_gate: string;
}

export interface RepositoryIntegrationContract {
  contract_id: string;
  producer_repository_id: string;
  consumer_repository_id: string;
  transport: RepositoryContractTransport;
  payload_type: string;
  release_version: string;
  schema_path: string;
  compatibility: "backward";
  invariants: string[];
}

export interface RepositoryTopology {
  schema_version: "1.0";
  current_repository_id: string;
  repositories: RepositoryTopologyItem[];
  integration_contracts: RepositoryIntegrationContract[];
  boundary_rules: RepositoryBoundaryRule[];
}

export interface AccessCapabilityItem {
  capability_id: string;
  name: string;
  status: AccessCapabilityStatus;
  summary: string;
  current_scope: string[];
  not_in_scope_yet: string[];
  next_gate: string;
}

export interface AccessFoundationStatus {
  schema_version: "1.0";
  auth_mode: "development_open" | "single_bearer_token";
  principal_source:
    "anonymous" | "api_token" | "service_account_api_key" | "header";
  tenant_id: string;
  project_id: string;
  principal_id: string;
  policy_provider: string;
  capabilities: AccessCapabilityItem[];
}

export type PortraitModuleMaturity =
  "available" | "partial" | "seed" | "planned" | "external";
export type PortraitCapabilityReadiness =
  "ready" | "fallback" | "placeholder" | "not_configured";

export interface PortraitCapabilityItem {
  capability_id: string;
  readiness: PortraitCapabilityReadiness;
  production_ready: boolean;
  current_model?: string | null;
  target_model?: string | null;
  embedding_dimension?: number | null;
  target_embedding_dimension?: number | null;
}

export interface PortraitModuleItem {
  module_id: string;
  name: string;
  maturity: PortraitModuleMaturity;
  summary: string;
  owner_repository_id: string;
  current_scope: string[];
  not_in_scope_yet: string[];
  next_gate: string;
}

export interface PortraitAssetItem {
  asset_id: string;
  name: string;
  maturity: PortraitModuleMaturity;
  summary: string;
  depends_on_modules: string[];
  next_gate: string;
}

export interface PortraitIntelligenceStatus {
  schema_version: "1.0";
  positioning: "portrait_intelligence_foundation_platform";
  modules: PortraitModuleItem[];
  assets: PortraitAssetItem[];
  capabilities: PortraitCapabilityItem[];
}

export interface Organization {
  tenant_id: string;
  display_name: string;
  created_at: number;
  updated_at: number;
}
export interface Project {
  tenant_id: string;
  project_id: string;
  display_name: string;
  created_at: number;
  updated_at: number;
}
export interface UserAccount {
  tenant_id: string;
  user_id: string;
  display_name: string;
  email?: string | null;
  disabled: boolean;
  created_at: number;
  updated_at: number;
}
export interface Role {
  tenant_id: string;
  role_id: string;
  display_name: string;
  scopes: string[];
  product_ids: string[];
  created_at: number;
  updated_at: number;
}
export interface Membership {
  tenant_id: string;
  project_id: string;
  principal_id: string;
  principal_type: "user" | "service_account";
  role_ids: string[];
  created_at: number;
  updated_at: number;
}
export interface ServiceAccount {
  tenant_id: string;
  project_id: string;
  service_account_id: string;
  display_name: string;
  scopes: string[];
  product_ids: string[];
  disabled: boolean;
  created_at: number;
  updated_at: number;
}
export interface ApiKeyRecord {
  tenant_id: string;
  project_id: string;
  key_id: string;
  service_account_id: string;
  name: string;
  token_prefix: string;
  scopes: string[];
  product_ids: string[];
  expires_at?: number | null;
  revoked_at?: number | null;
  last_used_at?: number | null;
  created_at: number;
}
export interface ProductEntitlement {
  tenant_id: string;
  project_id: string;
  product_id: string;
  status: "active" | "suspended";
  source: "manual" | "system";
  created_at: number;
  updated_at: number;
}
export interface IamInventory {
  organizations: number;
  projects: number;
  users: number;
  roles: number;
  memberships: number;
  service_accounts: number;
  api_keys: number;
  product_entitlements: number;
}
export interface IamSummary {
  schema_version: "1.0";
  tenant_id: string;
  project_id: string;
  inventory: IamInventory;
  default_admin_scopes: string[];
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
  status: "pending" | "approved" | "rejected";
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
  capability: string;
  runtime_model_id: string;
  package_sha256: string;
  evidence_refs: string[];
  status: "candidate" | "validated" | "approved" | "active" | "retired";
  created_by: string;
  created_at: number;
  updated_at: number;
  activated_at?: number | null;
  retired_at?: number | null;
}

export interface ModelDeploymentEvent {
  event_id: string;
  tenant_id: string;
  project_id: string;
  model_id: string;
  version: string;
  capability: string;
  runtime_model_id: string;
  package_sha256: string;
  action: string;
  from_status?: ModelRelease["status"] | null;
  to_status: ModelRelease["status"];
  reason: string;
  operator_id: string;
  audit_id: string;
  created_at: number;
}

export interface TableColumn<T = any> {
  key: string;
  label?: string;
  width?: string;
  minWidth?: string;
  align?: "left" | "center" | "right";
  headerAlign?: "left" | "center" | "right";
  class?: string;
  headerClass?: string;
  style?: Record<string, string | number> | string;
  formatter?: (value: any, row: T, index: number) => any;
}

