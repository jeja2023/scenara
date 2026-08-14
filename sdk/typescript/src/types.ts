export type Domain = "portrait" | "ocr";
export type MediaKind = "image" | "video" | "document" | "stream";
export type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";
export type RunStatus = "queued" | "running" | "pausing" | "paused" | "completed" | "failed" | "cancelling" | "cancelled";
export type FeedbackStatus = "pending" | "approved" | "rejected";
export type ModelReleaseStatus = "candidate" | "validated" | "approved" | "active" | "retired";
export type ProductLayer = "product_module" | "control_plane" | "developer_surface" | "foundation";
export type ProductMaturity = "available" | "seed" | "planned" | "gated";
export type AccessCapabilityStatus = "available" | "seed" | "planned" | "gated";

export interface PipelineRef {
  pipeline_id: string;
  version: string;
}

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
  stream_segment_duration_ms?: number | null;
  stream_segment_index?: number | null;
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
  kind: "image" | "video" | "document";
  filename?: string | null;
  content_type: string;
  size_bytes: number;
  sha256: string;
  preview_object_key?: string | null;
  preview_content_type?: string | null;
  preview_sha256?: string | null;
  metadata: MediaTechnicalMetadata;
  original_deleted_at?: number | null;
  temporary: boolean;
  created_at: number;
}

export interface MediaAssetPage {
  items: MediaAsset[];
  offset: number;
  limit: number;
  total: number;
}

export interface MediaSource {
  source_id: string;
  kind: "stream";
  name: string;
  masked_url: string;
  metadata: Record<string, unknown>;
  created_at: number;
}

export interface MediaSourcePage {
  items: MediaSource[];
  offset: number;
  limit: number;
  total: number;
}

export interface MediaSourceProbe {
  source_id: string;
  reachable: boolean;
  latency_ms: number;
  metadata: MediaTechnicalMetadata;
  checked_at: number;
}

export type DatasetStatus = "draft" | "active" | "archived";
export type DatasetVersionStatus = "draft" | "validated" | "published" | "retired";

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

export interface PresignedMediaUpload {
  upload_id: string;
  upload_token: string;
  method: "PUT";
  url: string;
  headers: Record<string, string>;
  expires_at: number;
}

export interface PresignedMediaDownload {
  method: "GET";
  url: string;
  headers: Record<string, string>;
  expires_at: number;
}

export interface AuditEventPage {
  items: AuditEvent[];
  offset: number;
  limit: number;
  total: number;
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

export interface SavedSearchPage {
  items: SavedSearch[];
  offset: number;
  limit: number;
  total: number;
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

export interface ProductCatalogItem {
  product_id: string;
  name: string;
  layer: ProductLayer;
  maturity: ProductMaturity;
  summary: string;
  current_scope: string[];
  not_in_scope_yet: string[];
  console_route: string | null;
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
export type RepositoryContractTransport = "versioned_api" | "event" | "immutable_manifest";

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

export interface RepositoryContractArtifact {
  contract_id: string;
  payload_type: string;
  release_version: string;
  payload_schema_version: string;
  producer_repository_id: string;
  consumer_repository_id: string;
  transport: RepositoryContractTransport;
  compatibility: "backward";
  schema_path: string;
  schema_sha256: string;
  example_path: string;
  example_sha256: string;
}

export interface RepositoryContractCatalog {
  schema_version: "1.0";
  release_version: string;
  package_name: string;
  contracts: RepositoryContractArtifact[];
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
  principal_source: "anonymous" | "api_token" | "service_account_api_key" | "header";
  tenant_id: string;
  project_id: string;
  principal_id: string;
  policy_provider: string;
  capabilities: AccessCapabilityItem[];
}

export type PortraitModuleMaturity = "available" | "partial" | "seed" | "planned" | "external";
export type PortraitCapabilityReadiness = "ready" | "fallback" | "placeholder" | "not_configured";

export interface PortraitCapabilityItem {
  capability_id: string;
  readiness: PortraitCapabilityReadiness;
  production_ready: boolean;
  current_model: string | null;
  target_model: string | null;
  embedding_dimension: number | null;
  target_embedding_dimension: number | null;
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
  email: string | null;
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
  expires_at: number | null;
  revoked_at: number | null;
  last_used_at: number | null;
  created_at: number;
}

export interface CreateApiKeyResponse {
  record: ApiKeyRecord;
  api_key: string;
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
  capability: string;
  runtime_model_id: string;
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
  tenant_id: string;
  project_id: string;
  model_id: string;
  version: string;
  capability: string;
  runtime_model_id: string;
  package_sha256: string;
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
  stream_session_id?: string | null;
  stream_segment_index?: number | null;
  previous_run_id?: string | null;
  next_run_id?: string | null;
  parameters: Record<string, unknown>;
  priority: number;
  status: RunStatus;
  revision: number;
  progress: number;
  error_code?: string | null;
  termination_reason?: string | null;
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

export interface ResultEnvelope {
  schema_version: string;
  run_id: string;
  domain: Domain;
  pipeline: PipelineRef;
  asset_id: string | null;
  source_id: string | null;
  units: Record<string, unknown>[];
  domain_payload: Record<string, unknown>;
  relations: Record<string, unknown>[];
  artifacts: Record<string, unknown>[];
  models: Record<string, unknown>[];
  timings: Record<string, number>;
  media_metadata: MediaTechnicalMetadata;
  warnings: string[];
  provenance: Record<string, unknown>;
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

export interface ParseVideoResponse {
  asset: MediaAsset;
  run: Run;
  result: ResultEnvelope | null;
}

export interface ParseDocumentResponse {
  asset: MediaAsset;
  run: Run;
  result: ResultEnvelope | null;
}

export interface PortraitInputSummary {
  face_count: number;
  selected_face_index: number;
  selected_face_box?: number[] | null;
  quality_score?: number | null;
  model_id: string;
  model_version: string;
  embedding_dimension: number;
  fallback: boolean;
  metadata: Record<string, unknown>;
}

export interface PortraitCompareResponse {
  feature_space_id: string;
  score: number;
  distance: number;
  threshold?: number | null;
  matched?: boolean | null;
  mode: "vector" | "image" | "asset" | "mixed";
  comparison_id?: string | null;
  left?: PortraitInputSummary | null;
  right?: PortraitInputSummary | null;
}

export interface IndexDefinition {
  index_id: string;
  schema_version: string;
  domain: string;
  record_kind: "vector" | "text" | "multimodal";
  vector_dimension?: number | null;
  vector_model_id?: string | null;
  vector_model_version?: string | null;
  distance_metric?: string | null;
  threshold?: number | null;
  text_analyzer?: string | null;
  created_at: number;
}

export interface IndexRecordView {
  record_id: string;
  index_id: string;
  domain: string;
  kind: "vector" | "text" | "multimodal";
  source: Record<string, unknown>;
  feature_id?: string | null;
  has_vector: boolean;
  text_snippet?: string | null;
  metadata: Record<string, unknown>;
  status: "ready" | "pending" | "failed" | "deleted";
  created_at: number;
  expires_at?: number | null;
  deleted_at?: number | null;
}

export interface IndexHit {
  record_id: string;
  index_id: string;
  domain: string;
  source: Record<string, unknown>;
  feature_id?: string | null;
  score?: number | null;
  distance?: number | null;
  text_snippet?: string | null;
  metadata: Record<string, unknown>;
}

export interface SearchImageInputSummary {
  face_count: number;
  selected_face_index: number;
  quality_score?: number | null;
  feature_space_id: string;
  model_id: string;
  model_version: string;
  embedding_dimension: number;
  fallback: boolean;
}

export interface SearchResultHit {
  record_id: string;
  index_id: string;
  domain: string;
  source: Record<string, unknown>;
  score?: number | null;
  distance?: number | null;
  text_snippet?: string | null;
  metadata: Record<string, unknown>;
  media_kind?: MediaKind | null;
  resource_name?: string | null;
}

export interface SearchResponse {
  search_id: string;
  mode: "text" | "portrait";
  query?: string | null;
  feature_space_id?: string | null;
  query_summary?: SearchImageInputSummary | null;
  hits: SearchResultHit[];
  total: number;
  searched_indexes: string[];
}
