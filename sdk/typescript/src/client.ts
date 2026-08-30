import type {
  AccessFoundationStatus,
  AuditEventPage,
  ApiKeyRecord,
  CreateApiKeyResponse,
  DatasetRecord,
  DatasetVersion,
  Domain,
  FeedbackRecord,
  HardSampleManifest,
  IamSummary,
  MediaAsset,
  MediaAssetPage,
  MediaSource,
  MediaSourcePage,
  MediaSourceProbe,
  Membership,
  ModelDeploymentEvent,
  ModelPackage,
  ModelRelease,
  Organization,
  ParseDocumentResponse,
  ParseImageResponse,
  ParseVideoResponse,
  PresignedMediaDownload,
  PresignedMediaUpload,
  PortraitCompareResponse,
  IndexDefinition,
  IndexHit,
  IndexRecordView,
  SearchResponse,
  SavedSearch,
  SavedSearchPage,
  PortraitIntelligenceStatus,
  ProductCatalogItem,
  ProductEntitlement,
  Project,
  RepositoryContractCatalog,
  RepositoryTopology,
  ResultEnvelope,
  ResultPage,
  Run,
  RunPage,
  RunStatus,
  SampleStrategy,
  Role,
  ServiceAccount,
  UserAccount,
  WebhookDelivery,
  WebhookSubscription,
} from "./types.js";
import type { OpenApi } from "./generated.js";

export type ScenaraTransport = <T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  options?: { body?: unknown; idempotencyKey?: string },
) => Promise<T>;

export type ControlPlaneRecord = Record<string, unknown>;

export interface CreateRunInput {
  domain: Domain;
  pipelineId: string;
  pipelineVersion: string;
  assetId?: string;
  sourceId?: string;
  parameters?: Record<string, unknown>;
  priority?: number;
  waitMs?: number;
  idempotencyKey?: string;
}

export interface ScenaraClientOptions {
  transport: ScenaraTransport;
}

export interface ParseFileInput {
  file: Blob;
  filename: string;
  domain?: Domain;
  pipelineId?: string;
  pipelineVersion?: string;
  idempotencyKey?: string;
}

export interface ParseVideoInput extends ParseFileInput {
  sampleIntervalMs?: number;
  sampleStrategy?: SampleStrategy;
  sampleStartMs?: number;
  sampleEndMs?: number;
  sceneChangeThreshold?: number;
  frameMaxEdge?: number;
  pageScale?: number;
  cameraId?: string;
  recordingStartedAt?: number;
  waitMs?: number;
}

export interface ParseDocumentInput extends ParseFileInput {
  pageScale?: number;
  waitMs?: number;
}

export interface ParseStreamInput {
  sourceId: string;
  domain?: Domain;
  pipelineId?: string;
  pipelineVersion?: string;
  sampleIntervalMs?: number;
  sampleStrategy?: SampleStrategy;
  sampleStartMs?: number;
  sampleEndMs?: number;
  streamSegmentDurationMs?: number;
  sceneChangeThreshold?: number;
  frameMaxEdge?: number;
  maxReconnectAttempts?: number;
  connectTimeoutMs?: number;
  readTimeoutMs?: number;
  priority?: number;
  waitMs?: number;
  idempotencyKey?: string;
}

export class ScenaraError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ScenaraError";
  }
}

export class ScenaraClient {
  private readonly transport: ScenaraTransport;

  constructor(options: ScenaraClientOptions) {
    this.transport = options.transport;
  }

  controlPlane<T = ControlPlaneRecord>(
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    body?: ControlPlaneRecord,
  ): Promise<T> {
    return this.transport<T>(
      method,
      path,
      body === undefined ? undefined : { body },
    );
  }

  getRun(runId: string): Promise<Run> {
    return this.transport<Run>(
      "GET",
      "/api/v1/runs/" + encodeURIComponent(runId),
    );
  }

  listRuns(
    filters: { status?: RunStatus; domain?: Domain; limit?: number } = {},
  ): Promise<RunPage> {
    const query = new URLSearchParams();
    if (filters.status) query.set("status", filters.status);
    if (filters.domain) query.set("domain", filters.domain);
    query.set("limit", String(filters.limit ?? 50));
    return this.transport<RunPage>("GET", "/api/v1/runs?" + query.toString());
  }

  createRun(input: CreateRunInput): Promise<Run> {
    return this.transport<Run>("POST", "/api/v1/runs", {
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
      body: {
        domain: input.domain,
        pipeline: {
          pipeline_id: input.pipelineId,
          version: input.pipelineVersion,
        },
        asset_id: input.assetId,
        source_id: input.sourceId,
        parameters: input.parameters ?? {},
        priority: input.priority ?? 0,
        wait_ms: input.waitMs ?? 0,
      },
    });
  }

  cancelRun(runId: string): Promise<Run> {
    return this.transport<Run>(
      "POST",
      "/api/v1/runs/" + encodeURIComponent(runId) + "/cancel",
    );
  }

  async getResult(runId: string): Promise<ResultEnvelope> {
    const page = await this.getResultPage(runId, 0, 1000);
    const units = [...page.result.units];
    let total = page.unit_total;
    while (units.length < total) {
      const next = await this.getResultPage(runId, units.length, 1000);
      if (!next.result.units.length) break;
      units.push(...next.result.units);
      total = Math.max(total, next.unit_total);
    }
    return { ...page.result, units };
  }

  getResultPage(
    runId: string,
    unitOffset = 0,
    unitLimit = 100,
  ): Promise<ResultPage> {
    const query = new URLSearchParams({
      unit_offset: String(unitOffset),
      unit_limit: String(unitLimit),
    });
    return this.transport<ResultPage>(
      "GET",
      "/api/v1/runs/" +
        encodeURIComponent(runId) +
        "/result?" +
        query.toString(),
    );
  }

  /**
   * Download one derived image declared by a run result: a feature crop
   * (`crop_artifact_id` on a detected object) or a full unit image
   * (`frame_artifact_id` on a media unit).
   */
  getResultArtifact(runId: string, artifactId: string): Promise<Uint8Array> {
    return this.transport<Uint8Array>(
      "GET",
      "/api/v1/runs/" +
        encodeURIComponent(runId) +
        "/artifacts/" +
        encodeURIComponent(artifactId),
    );
  }

  pauseRun(runId: string): Promise<Run> {
    return this.transport<Run>(
      "POST",
      "/api/v1/runs/" + encodeURIComponent(runId) + "/pause",
    );
  }

  resumeRun(runId: string): Promise<Run> {
    return this.transport<Run>(
      "POST",
      "/api/v1/runs/" + encodeURIComponent(runId) + "/resume",
    );
  }

  listAssets(offset = 0, limit = 50): Promise<MediaAssetPage> {
    return this.transport<MediaAssetPage>(
      "GET",
      "/api/v1/media/assets?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  uploadAsset(input: {
    file: Blob;
    filename: string;
    kind?: "image" | "video" | "document";
  }): Promise<MediaAsset> {
    const form = new FormData();
    form.append("file", input.file, input.filename);
    form.append("kind", input.kind ?? "image");
    return this.transport<MediaAsset>("POST", "/api/v1/media/assets", {
      body: form,
    });
  }

  async uploadAssetDirect(input: {
    file: Blob;
    filename: string;
    kind?: "image" | "video" | "document";
  }): Promise<MediaAsset> {
    const digest = await crypto.subtle.digest(
      "SHA-256",
      await input.file.arrayBuffer(),
    );
    const sha256 = Array.from(new Uint8Array(digest), (value) =>
      value.toString(16).padStart(2, "0"),
    ).join("");
    const request = {
      filename: input.filename,
      content_type: input.file.type || "application/octet-stream",
      kind: input.kind ?? "video",
      size_bytes: input.file.size,
      sha256,
    };
    const upload = await this.transport<PresignedMediaUpload>(
      "POST",
      "/api/v1/media/uploads/presign",
      {
        body: request,
      },
    );
    const response = await fetch(upload.url, {
      method: upload.method,
      headers: upload.headers,
      body: input.file,
    });
    if (!response.ok)
      throw new ScenaraError(
        "OBJECT_UPLOAD_FAILED",
        `Object upload failed with ${response.status}`,
      );
    return this.transport<MediaAsset>(
      "POST",
      "/api/v1/media/uploads/complete",
      {
        body: {
          ...request,
          upload_id: upload.upload_id,
          upload_token: upload.upload_token,
          expires_at: upload.expires_at,
        },
      },
    );
  }

  getAssetDownloadUrl(
    assetId: string,
    expiresIn?: number,
  ): Promise<PresignedMediaDownload> {
    const query =
      expiresIn === undefined ? "" : "?expires_in=" + String(expiresIn);
    return this.transport<PresignedMediaDownload>(
      "GET",
      "/api/v1/media/assets/" +
        encodeURIComponent(assetId) +
        "/download-url" +
        query,
    );
  }

  parseImage(input: ParseFileInput): Promise<ParseImageResponse> {
    const form = new FormData();
    form.append("file", input.file, input.filename);
    form.append("domain", input.domain ?? "portrait");
    if (input.pipelineId) form.append("pipeline_id", input.pipelineId);
    if (input.pipelineVersion)
      form.append("pipeline_version", input.pipelineVersion);
    return this.transport<ParseImageResponse>("POST", "/api/v1/parse/image", {
      body: form,
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
    });
  }

  parseVideo(input: ParseVideoInput): Promise<ParseVideoResponse> {
    const form = new FormData();
    form.append("file", input.file, input.filename);
    form.append("domain", input.domain ?? "portrait");
    if (input.pipelineId) form.append("pipeline_id", input.pipelineId);
    if (input.pipelineVersion)
      form.append("pipeline_version", input.pipelineVersion);
    form.append("sample_interval_ms", String(input.sampleIntervalMs ?? 1000));
    form.append("sample_strategy", input.sampleStrategy ?? "interval");
    form.append("sample_start_ms", String(input.sampleStartMs ?? 0));
    if (input.sampleEndMs !== undefined)
      form.append("sample_end_ms", String(input.sampleEndMs));
    form.append(
      "scene_change_threshold",
      String(input.sceneChangeThreshold ?? 0.35),
    );
    if (input.frameMaxEdge !== undefined)
      form.append("frame_max_edge", String(input.frameMaxEdge));
    form.append("page_scale", String(input.pageScale ?? 1.5));
    if (input.cameraId) form.append("camera_id", input.cameraId);
    if (input.recordingStartedAt !== undefined)
      form.append("recording_started_at", String(input.recordingStartedAt));
    form.append("wait_ms", String(input.waitMs ?? 0));
    return this.transport<ParseVideoResponse>("POST", "/api/v1/parse/video", {
      body: form,
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
    });
  }

  parseDocument(input: ParseDocumentInput): Promise<ParseDocumentResponse> {
    const form = new FormData();
    form.append("file", input.file, input.filename);
    form.append("domain", input.domain ?? "ocr");
    if (input.pipelineId) form.append("pipeline_id", input.pipelineId);
    if (input.pipelineVersion)
      form.append("pipeline_version", input.pipelineVersion);
    form.append("page_scale", String(input.pageScale ?? 1.5));
    form.append("wait_ms", String(input.waitMs ?? 0));
    return this.transport<ParseDocumentResponse>(
      "POST",
      "/api/v1/parse/document",
      {
        body: form,
        idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
      },
    );
  }

  parseStream(input: ParseStreamInput): Promise<Run> {
    const domain = input.domain ?? "portrait";
    const pipelineId =
      input.pipelineId ??
      (domain === "portrait" ? "portrait.person-detection" : "ocr.document");
    const pipeline = {
      pipeline_id: pipelineId,
      ...(input.pipelineVersion === undefined
        ? {}
        : { version: input.pipelineVersion }),
    };
    return this.transport<Run>("POST", "/api/v1/parse/stream", {
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
      body: {
        source_id: input.sourceId,
        domain,
        pipeline,
        parameters: {
          sample_interval_ms: input.sampleIntervalMs ?? 1000,
          sample_strategy: input.sampleStrategy ?? "interval",
          sample_start_ms: input.sampleStartMs ?? 0,
          ...(input.sampleEndMs === undefined
            ? {}
            : { sample_end_ms: input.sampleEndMs }),
          scene_change_threshold: input.sceneChangeThreshold ?? 0.35,
          ...(input.frameMaxEdge === undefined
            ? {}
            : { frame_max_edge: input.frameMaxEdge }),
          max_reconnect_attempts: input.maxReconnectAttempts ?? 3,
          connect_timeout_ms: input.connectTimeoutMs ?? 10000,
          read_timeout_ms: input.readTimeoutMs ?? 10000,
          ...(input.streamSegmentDurationMs === undefined
            ? {}
            : { stream_segment_duration_ms: input.streamSegmentDurationMs }),
        },
        priority: input.priority ?? 0,
        wait_ms: input.waitMs ?? 0,
      },
    });
  }

  deleteAsset(assetId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/media/assets/" + encodeURIComponent(assetId),
    );
  }

  getAssetPreview(assetId: string): Promise<Uint8Array> {
    return this.transport<Uint8Array>(
      "GET",
      "/api/v1/media/assets/" + encodeURIComponent(assetId) + "/preview",
    );
  }

  listSources(offset = 0, limit = 50): Promise<MediaSourcePage> {
    return this.transport<MediaSourcePage>(
      "GET",
      "/api/v1/media/sources?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  createSource(input: {
    name: string;
    url: string;
    metadata?: Record<string, unknown>;
  }): Promise<MediaSource> {
    return this.transport<MediaSource>("POST", "/api/v1/media/sources", {
      body: {
        name: input.name,
        url: input.url,
        metadata: input.metadata ?? {},
      },
    });
  }

  getSource(sourceId: string): Promise<MediaSource> {
    return this.transport<MediaSource>(
      "GET",
      "/api/v1/media/sources/" + encodeURIComponent(sourceId),
    );
  }

  probeSource(sourceId: string, timeoutMs = 10000): Promise<MediaSourceProbe> {
    return this.transport<MediaSourceProbe>(
      "POST",
      "/api/v1/media/sources/" +
        encodeURIComponent(sourceId) +
        "/probe?timeout_ms=" +
        String(timeoutMs),
    );
  }

  deleteSource(sourceId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/media/sources/" + encodeURIComponent(sourceId),
    );
  }

  listPipelines(): Promise<Record<string, unknown>[]> {
    return this.transport<Record<string, unknown>[]>(
      "GET",
      "/api/v1/pipelines",
    );
  }

  listDomains(): Promise<Record<string, unknown>[]> {
    return this.transport<Record<string, unknown>[]>("GET", "/api/v1/domains");
  }

  listProducts(): Promise<ProductCatalogItem[]> {
    return this.transport<ProductCatalogItem[]>(
      "GET",
      "/api/v1/platform/products",
    );
  }

  getRepositoryTopology(): Promise<RepositoryTopology> {
    return this.transport<RepositoryTopology>(
      "GET",
      "/api/v1/platform/repositories",
    );
  }

  getRepositoryContracts(): Promise<RepositoryContractCatalog> {
    return this.transport<RepositoryContractCatalog>(
      "GET",
      "/api/v1/platform/contracts",
    );
  }

  getAccessFoundation(): Promise<AccessFoundationStatus> {
    return this.transport<AccessFoundationStatus>(
      "GET",
      "/api/v1/platform/access-foundation",
    );
  }

  /**
   * Returns the Portrait Intelligence Foundation Platform contract: the six
   * strategic capability modules, three core assets, and per-capability
   * readiness state for the portrait domain.
   */
  getPortraitIntelligence(): Promise<PortraitIntelligenceStatus> {
    return this.transport<PortraitIntelligenceStatus>(
      "GET",
      "/api/v1/platform/portrait-intelligence",
    );
  }

  getIamSummary(): Promise<IamSummary> {
    return this.transport<IamSummary>("GET", "/api/v1/platform/iam/summary");
  }

  createOrganization(displayName: string): Promise<Organization> {
    return this.transport<Organization>(
      "POST",
      "/api/v1/platform/organizations",
      {
        body: { display_name: displayName },
      },
    );
  }

  listOrganizations(): Promise<Organization[]> {
    return this.transport<Organization[]>(
      "GET",
      "/api/v1/platform/organizations",
    );
  }

  createProject(input: {
    displayName: string;
    projectId?: string;
  }): Promise<Project> {
    return this.transport<Project>("POST", "/api/v1/platform/projects", {
      body: { display_name: input.displayName, project_id: input.projectId },
    });
  }

  listProjects(): Promise<Project[]> {
    return this.transport<Project[]>("GET", "/api/v1/platform/projects");
  }

  createUser(input: {
    displayName: string;
    userId?: string;
    email?: string;
  }): Promise<UserAccount> {
    return this.transport<UserAccount>("POST", "/api/v1/platform/users", {
      body: {
        display_name: input.displayName,
        user_id: input.userId,
        email: input.email,
      },
    });
  }

  listUsers(): Promise<UserAccount[]> {
    return this.transport<UserAccount[]>("GET", "/api/v1/platform/users");
  }

  createRole(input: {
    displayName: string;
    scopes: string[];
    productIds?: string[];
    roleId?: string;
  }): Promise<Role> {
    return this.transport<Role>("POST", "/api/v1/platform/roles", {
      body: {
        display_name: input.displayName,
        role_id: input.roleId,
        scopes: input.scopes,
        product_ids: input.productIds ?? [],
      },
    });
  }

  listRoles(): Promise<Role[]> {
    return this.transport<Role[]>("GET", "/api/v1/platform/roles");
  }

  createMembership(input: {
    principalId: string;
    principalType: "user" | "service_account";
    roleIds: string[];
    projectId?: string;
  }): Promise<Membership> {
    return this.transport<Membership>("POST", "/api/v1/platform/memberships", {
      body: {
        principal_id: input.principalId,
        principal_type: input.principalType,
        role_ids: input.roleIds,
        project_id: input.projectId,
      },
    });
  }

  listMemberships(): Promise<Membership[]> {
    return this.transport<Membership[]>("GET", "/api/v1/platform/memberships");
  }

  createServiceAccount(input: {
    displayName: string;
    scopes: string[];
    productIds?: string[];
    serviceAccountId?: string;
  }): Promise<ServiceAccount> {
    return this.transport<ServiceAccount>(
      "POST",
      "/api/v1/platform/service-accounts",
      {
        body: {
          display_name: input.displayName,
          service_account_id: input.serviceAccountId,
          scopes: input.scopes,
          product_ids: input.productIds ?? [],
        },
      },
    );
  }

  listServiceAccounts(): Promise<ServiceAccount[]> {
    return this.transport<ServiceAccount[]>(
      "GET",
      "/api/v1/platform/service-accounts",
    );
  }

  createApiKey(input: {
    serviceAccountId: string;
    name: string;
    scopes?: string[];
    productIds?: string[];
    expiresAt?: number;
  }): Promise<CreateApiKeyResponse> {
    return this.transport<CreateApiKeyResponse>(
      "POST",
      "/api/v1/platform/service-accounts/" +
        encodeURIComponent(input.serviceAccountId) +
        "/api-keys",
      {
        body: {
          name: input.name,
          scopes: input.scopes,
          product_ids: input.productIds,
          expires_at: input.expiresAt,
        },
      },
    );
  }

  listApiKeys(): Promise<ApiKeyRecord[]> {
    return this.transport<ApiKeyRecord[]>("GET", "/api/v1/platform/api-keys");
  }

  revokeApiKey(keyId: string): Promise<ApiKeyRecord> {
    return this.transport<ApiKeyRecord>(
      "POST",
      "/api/v1/platform/api-keys/" + encodeURIComponent(keyId) + "/revoke",
    );
  }

  createProductEntitlement(input: {
    productId: string;
    status?: "active" | "suspended";
    source?: "manual" | "enterprise_license" | "system";
    projectId?: string;
  }): Promise<ProductEntitlement> {
    return this.transport<ProductEntitlement>(
      "POST",
      "/api/v1/platform/product-entitlements",
      {
        body: {
          product_id: input.productId,
          status: input.status ?? "active",
          source: input.source ?? "manual",
          project_id: input.projectId,
        },
      },
    );
  }

  listProductEntitlements(): Promise<ProductEntitlement[]> {
    return this.transport<ProductEntitlement[]>(
      "GET",
      "/api/v1/platform/product-entitlements",
    );
  }

  updateProductEntitlement(input: {
    productId: string;
    status: "active" | "suspended";
    source?: "manual" | "enterprise_license" | "system";
  }): Promise<ProductEntitlement> {
    return this.transport<ProductEntitlement>(
      "PUT",
      "/api/v1/platform/product-entitlements/" +
        encodeURIComponent(input.productId),
      { body: { status: input.status, source: input.source ?? "manual" } },
    );
  }

  listModels(): Promise<ModelPackage[]> {
    return this.transport<ModelPackage[]>("GET", "/api/v1/models");
  }

  createWebhookSubscription(input: {
    name: string;
    url: string;
    secret: string;
    eventTypes: string[];
  }): Promise<WebhookSubscription> {
    return this.transport<WebhookSubscription>(
      "POST",
      "/api/v1/webhooks/subscriptions",
      {
        body: {
          name: input.name,
          url: input.url,
          secret: input.secret,
          event_types: input.eventTypes,
        },
      },
    );
  }

  listWebhookSubscriptions(): Promise<WebhookSubscription[]> {
    return this.transport<WebhookSubscription[]>(
      "GET",
      "/api/v1/webhooks/subscriptions",
    );
  }

  deleteWebhookSubscription(endpointId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/webhooks/subscriptions/" + encodeURIComponent(endpointId),
    );
  }

  listWebhookDeliveries(limit = 100): Promise<WebhookDelivery[]> {
    return this.transport<WebhookDelivery[]>(
      "GET",
      "/api/v1/webhooks/deliveries?limit=" + String(limit),
    );
  }

  createPortraitIdentity(
    displayName: string,
    metadata: Record<string, unknown> = {},
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/identities",
      {
        body: { display_name: displayName, metadata },
      },
    );
  }

  deletePortraitIdentity(identityId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/portrait/identities/" + encodeURIComponent(identityId),
    );
  }

  enrollPortraitIdentity(
    identityId: string,
    enrollment: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/identities/" +
        encodeURIComponent(identityId) +
        "/enrollments",
      { body: enrollment },
    );
  }

  searchPortrait(
    query: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/search",
      { body: query },
    );
  }

  comparePortrait(
    comparison: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/compare",
      {
        body: comparison,
      },
    );
  }

  getStreamSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "GET",
      "/api/v1/stream-sessions/" + encodeURIComponent(sessionId),
    );
  }

  cancelStreamSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/stream-sessions/" + encodeURIComponent(sessionId) + "/cancel",
    );
  }

  createIdentityProvider(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/identity-providers",
      input,
    );
  }

  listIdentityProviders(): Promise<ControlPlaneRecord[]> {
    return this.controlPlane<ControlPlaneRecord[]>(
      "GET",
      "/api/v1/platform/identity-providers",
    );
  }

  probeIdentityProvider(providerId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/identity-providers/" +
        encodeURIComponent(providerId) +
        "/probe",
    );
  }

  requestProjectLifecycle(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/projects/lifecycle-requests",
      input,
    );
  }

  decideProjectLifecycle(
    requestId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/projects/lifecycle-requests/" +
        encodeURIComponent(requestId) +
        "/decide",
      input,
    );
  }

  setAuditRetention(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("PUT", "/api/v1/platform/audit/retention", input);
  }

  purgeAudit(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/audit/purge", input);
  }

  createSession(input: {
    userId: string;
    ttlSeconds?: number;
  }): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/sessions", {
      user_id: input.userId,
      ttl_seconds: input.ttlSeconds ?? 3600,
    });
  }

  setUserDisabled(userId: string, disabled: boolean): Promise<UserAccount> {
    const action = disabled ? "disable" : "restore";
    return this.transport<UserAccount>(
      "POST",
      "/api/v1/platform/users/" + encodeURIComponent(userId) + "/" + action,
    );
  }

  createQuotaPlan(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/quotas/plans", input);
  }

  checkQuota(metric: string, amount = 1): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/quotas/check", {
      metric,
      amount,
    });
  }

  createAnnotationTask(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/data/annotation-tasks", input);
  }

  registerAnnotationProvider(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/data/annotation-providers",
      input,
    );
  }

  probeAnnotationProvider(providerId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/data/annotation-providers/" +
        encodeURIComponent(providerId) +
        "/probe",
    );
  }

  reviewAnnotationTask(
    taskId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/data/annotation-tasks/" + encodeURIComponent(taskId) + "/review",
      input,
    );
  }

  createFlow(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/flows", input);
  }

  executeFlow(
    flowId: string,
    input: ControlPlaneRecord = {},
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/flows/" + encodeURIComponent(flowId) + "/execute",
      input,
    );
  }

  decideFlowApproval(
    approvalId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/flows/approvals/" + encodeURIComponent(approvalId) + "/decide",
      input,
    );
  }

  createSearchRankingProfile(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/ranking-profiles", input);
  }

  evaluateSearch(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/evaluations", input);
  }

  rebuildIndex(indexId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/indexes/rebuild", {
      index_id: indexId,
    });
  }

  createIndex(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/indexes", input);
  }

  registerIndexBackend(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/index-backends", input);
  }

  probeIndexBackend(backendId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/search/index-backends/" +
        encodeURIComponent(backendId) +
        "/probe",
    );
  }

  registerSearchReranker(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/rerankers", input);
  }

  probeSearchReranker(rerankerId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/search/rerankers/" + encodeURIComponent(rerankerId) + "/probe",
    );
  }

  registerEdgeDevice(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/edge/devices", input);
  }

  heartbeatEdgeDevice(
    deviceId: string,
    input: ControlPlaneRecord = {},
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/edge/devices/" + encodeURIComponent(deviceId) + "/heartbeat",
      input,
    );
  }

  deployEdge(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/edge/deployments", input);
  }

  acknowledgeEdgeDeployment(
    deploymentId: string,
    input: ControlPlaneRecord = {},
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/edge/deployments/" +
        encodeURIComponent(deploymentId) +
        "/acknowledge",
      input,
    );
  }

  registerAgentTool(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/tools", input);
  }

  proposeAgentAction(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/actions", input);
  }

  decideAgentAction(
    actionId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/agents/actions/" + encodeURIComponent(actionId) + "/decide",
      input,
    );
  }

  executeAgentAction(actionId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/agents/actions/" + encodeURIComponent(actionId) + "/execute",
    );
  }

  recordAgentTrace(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/traces", input);
  }

  recordAgentEvaluation(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/evaluations", input);
  }

  putAgentMemory(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("PUT", "/api/v1/agents/memory", input);
  }

  getAgentMemory(
    namespace: string,
    key: string,
  ): Promise<ControlPlaneRecord | null> {
    return this.controlPlane<ControlPlaneRecord | null>(
      "GET",
      "/api/v1/agents/memory?namespace=" +
        encodeURIComponent(namespace) +
        "&key=" +
        encodeURIComponent(key),
    );
  }

  getDeploymentTopology(): Promise<ControlPlaneRecord> {
    return this.controlPlane("GET", "/api/v1/platform/deployment/topology");
  }

  listDatasets(
    offset = 0,
    limit = 50,
  ): Promise<{
    items: DatasetRecord[];
    offset: number;
    limit: number;
    total: number;
  }> {
    return this.transport<{
      items: DatasetRecord[];
      offset: number;
      limit: number;
      total: number;
    }>(
      "GET",
      "/api/v1/datasets?offset=" + String(offset) + "&limit=" + String(limit),
    );
  }

  createDataset(input: {
    name: string;
    description?: string;
    metadata?: Record<string, unknown>;
  }): Promise<DatasetRecord> {
    return this.transport<DatasetRecord>("POST", "/api/v1/datasets", {
      body: {
        name: input.name,
        description: input.description ?? "",
        metadata: input.metadata ?? {},
      },
    });
  }

  getDataset(datasetId: string): Promise<DatasetRecord> {
    return this.transport<DatasetRecord>(
      "GET",
      "/api/v1/datasets/" + encodeURIComponent(datasetId),
    );
  }

  updateDataset(
    datasetId: string,
    input: Partial<
      Pick<DatasetRecord, "name" | "description" | "status" | "metadata">
    >,
  ): Promise<DatasetRecord> {
    return this.transport<DatasetRecord>(
      "PATCH",
      "/api/v1/datasets/" + encodeURIComponent(datasetId),
      { body: input },
    );
  }

  createDatasetVersion(
    datasetId: string,
    input: {
      version: string;
      manifestSha256: string;
      assetIds?: string[];
      qualityScore?: number | null;
      lineage?: Record<string, unknown>;
      annotationSummary?: Record<string, unknown>;
    },
  ): Promise<DatasetVersion> {
    return this.transport<DatasetVersion>(
      "POST",
      "/api/v1/datasets/" + encodeURIComponent(datasetId) + "/versions",
      {
        body: {
          version: input.version,
          manifest_sha256: input.manifestSha256,
          asset_ids: input.assetIds ?? [],
          quality_score: input.qualityScore ?? null,
          lineage: input.lineage ?? {},
          annotation_summary: input.annotationSummary ?? {},
        },
      },
    );
  }

  listDatasetVersions(
    datasetId: string,
    offset = 0,
    limit = 50,
  ): Promise<{
    items: DatasetVersion[];
    offset: number;
    limit: number;
    total: number;
  }> {
    return this.transport<{
      items: DatasetVersion[];
      offset: number;
      limit: number;
      total: number;
    }>(
      "GET",
      "/api/v1/datasets/" +
        encodeURIComponent(datasetId) +
        "/versions?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  transitionDatasetVersion(
    versionId: string,
    status: "validated" | "published" | "retired",
  ): Promise<DatasetVersion> {
    return this.transport<DatasetVersion>(
      "POST",
      "/api/v1/dataset-versions/" +
        encodeURIComponent(versionId) +
        "/transition",
      { body: { status } },
    );
  }

  listAuditEvents(
    filters: {
      action?: string;
      resourceType?: string;
      principalId?: string;
      outcome?: string;
      offset?: number;
      limit?: number;
    } = {},
  ): Promise<AuditEventPage> {
    const query = new URLSearchParams();
    if (filters.action) query.set("action", filters.action);
    if (filters.resourceType) query.set("resource_type", filters.resourceType);
    if (filters.principalId) query.set("principal_id", filters.principalId);
    if (filters.outcome) query.set("outcome", filters.outcome);
    query.set("offset", String(filters.offset ?? 0));
    query.set("limit", String(filters.limit ?? 50));
    return this.transport<AuditEventPage>(
      "GET",
      "/api/v1/audit/events?" + query.toString(),
    );
  }

  enrollPortraitIdentityImage(
    identityId: string,
    file: Blob,
    filename = "portrait-image",
    options: { featureSpaceId?: string; quality?: number } = {},
  ): Promise<Record<string, unknown>> {
    const form = new FormData();
    form.append("file", file, filename);
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.quality !== undefined)
      form.append("quality", String(options.quality));
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/identities/" +
        encodeURIComponent(identityId) +
        "/enrollments/image",
      { body: form },
    );
  }

  searchPortraitImage(
    file: Blob,
    filename = "portrait-query",
    options: {
      featureSpaceId?: string;
      limit?: number;
      threshold?: number;
    } = {},
  ): Promise<Record<string, unknown>> {
    const form = new FormData();
    form.append("file", file, filename);
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.limit !== undefined)
      form.append("limit", String(options.limit));
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/search/image",
      { body: form },
    );
  }

  comparePortraitImages(
    left: Blob,
    right: Blob,
    options: {
      leftFilename?: string;
      rightFilename?: string;
      featureSpaceId?: string;
      threshold?: number;
    } = {},
  ): Promise<PortraitCompareResponse> {
    const form = new FormData();
    form.append("left", left, options.leftFilename ?? "portrait-left");
    form.append("right", right, options.rightFilename ?? "portrait-right");
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/images",
      { body: form },
    );
  }

  comparePortraitAssets(input: {
    leftAssetId: string;
    rightAssetId: string;
    featureSpaceId?: string;
    threshold?: number;
  }): Promise<PortraitCompareResponse> {
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/assets",
      {
        body: {
          left_asset_id: input.leftAssetId,
          right_asset_id: input.rightAssetId,
          feature_space_id: input.featureSpaceId,
          threshold: input.threshold,
        },
      },
    );
  }

  comparePortraitAssetImage(
    assetId: string,
    image: Blob,
    options: {
      filename?: string;
      featureSpaceId?: string;
      threshold?: number;
    } = {},
  ): Promise<PortraitCompareResponse> {
    const form = new FormData();
    form.append("asset_id", assetId);
    form.append("file", image, options.filename ?? "portrait-image");
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/asset-image",
      { body: form },
    );
  }

  comparePortraitImageAsset(
    image: Blob,
    assetId: string,
    options: {
      filename?: string;
      featureSpaceId?: string;
      threshold?: number;
    } = {},
  ): Promise<PortraitCompareResponse> {
    const form = new FormData();
    form.append("file", image, options.filename ?? "portrait-image");
    form.append("asset_id", assetId);
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/image-asset",
      { body: form },
    );
  }

  listSearchIndexes(domain?: string): Promise<IndexDefinition[]> {
    const query = domain ? `?domain=${encodeURIComponent(domain)}` : "";
    return this.transport<IndexDefinition[]>("GET", "/api/v1/indexes" + query);
  }

  listSearchIndexRecords(
    indexId: string,
    filters: {
      sourceType?: string;
      sourceId?: string;
      offset?: number;
      limit?: number;
    } = {},
  ): Promise<IndexRecordView[]> {
    const query = new URLSearchParams();
    if (filters.sourceType) query.set("source_type", filters.sourceType);
    if (filters.sourceId) query.set("source_id", filters.sourceId);
    if (filters.offset !== undefined)
      query.set("offset", String(filters.offset));
    if (filters.limit !== undefined) query.set("limit", String(filters.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return this.transport<IndexRecordView[]>(
      "GET",
      "/api/v1/indexes/" + encodeURIComponent(indexId) + "/records" + suffix,
    );
  }

  querySearchIndexText(
    indexId: string,
    query: string,
    limit = 20,
  ): Promise<Record<string, unknown>[]> {
    return this.transport<Record<string, unknown>[]>(
      "POST",
      "/api/v1/indexes/" + encodeURIComponent(indexId) + "/query/text",
      { body: { query, limit } },
    );
  }

  querySearchIndexVector(
    indexId: string,
    vector: number[],
    options: { limit?: number; threshold?: number } = {},
  ): Promise<IndexHit[]> {
    return this.transport<IndexHit[]>(
      "POST",
      "/api/v1/indexes/" + encodeURIComponent(indexId) + "/query/vector",
      {
        body: {
          vector,
          limit: options.limit ?? 20,
          threshold: options.threshold,
        },
      },
    );
  }

  searchText(input: {
    query: string;
    domains?: string[];
    mediaKinds?: string[];
    limit?: number;
  }): Promise<SearchResponse> {
    return this.transport<SearchResponse>("POST", "/api/v1/search/text", {
      body: {
        query: input.query,
        domains: input.domains ?? [],
        media_kinds: input.mediaKinds ?? [],
        limit: input.limit ?? 50,
      },
    });
  }

  searchPortraitResults(input: {
    file: Blob;
    filename?: string;
    featureSpaceId?: string;
    mediaKinds?: string[];
    limit?: number;
    threshold?: number;
  }): Promise<SearchResponse> {
    const form = new FormData();
    form.append("file", input.file, input.filename ?? "query-image");
    if (input.featureSpaceId)
      form.append("feature_space_id", input.featureSpaceId);
    if (input.mediaKinds?.length)
      form.append("media_kinds", input.mediaKinds.join(","));
    if (input.limit !== undefined) form.append("limit", String(input.limit));
    if (input.threshold !== undefined)
      form.append("threshold", String(input.threshold));
    return this.transport<SearchResponse>("POST", "/api/v1/search/image", {
      body: form,
    });
  }

  searchPortraitAsset(input: {
    assetId: string;
    featureSpaceId?: string;
    mediaKinds?: string[];
    limit?: number;
    threshold?: number;
  }): Promise<SearchResponse> {
    return this.transport<SearchResponse>("POST", "/api/v1/search/asset", {
      body: {
        asset_id: input.assetId,
        feature_space_id: input.featureSpaceId,
        media_kinds: input.mediaKinds ?? [],
        limit: input.limit ?? 50,
        threshold: input.threshold,
      },
    });
  }

  createSavedSearch(input: {
    name: string;
    mode: "text" | "portrait";
    definition: Record<string, unknown>;
    description?: string;
  }): Promise<SavedSearch> {
    return this.transport<SavedSearch>("POST", "/api/v1/search/saved", {
      body: {
        name: input.name,
        description: input.description ?? "",
        mode: input.mode,
        definition: input.definition,
      },
    });
  }

  listSavedSearches(offset = 0, limit = 50): Promise<SavedSearchPage> {
    return this.transport<SavedSearchPage>(
      "GET",
      "/api/v1/search/saved?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  getSavedSearch(savedSearchId: string): Promise<SavedSearch> {
    return this.transport<SavedSearch>(
      "GET",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId),
    );
  }

  updateSavedSearch(
    savedSearchId: string,
    input: {
      name?: string;
      description?: string;
      definition?: Record<string, unknown>;
    },
  ): Promise<SavedSearch> {
    return this.transport<SavedSearch>(
      "PATCH",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId),
      {
        body: input,
      },
    );
  }

  runSavedSearch(savedSearchId: string): Promise<SearchResponse> {
    return this.transport<SearchResponse>(
      "POST",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId) + "/run",
    );
  }

  deleteSavedSearch(savedSearchId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId),
    );
  }

  createWatchlist(input: {
    name: string;
    category?: "blacklist" | "whitelist" | "custom";
    description?: string;
  }): Promise<OpenApi.Watchlist> {
    return this.transport<OpenApi.Watchlist>(
      "POST",
      "/api/v1/surveillance/watchlists",
      { body: input },
    );
  }

  listWatchlists(offset = 0, limit = 50): Promise<OpenApi.WatchlistPage> {
    return this.transport<OpenApi.WatchlistPage>(
      "GET",
      "/api/v1/surveillance/watchlists?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  addWatchlistMember(
    watchlistId: string,
    input: {
      portraitIdentityId: string;
      displayLabel?: string;
      validFrom?: number;
      validUntil?: number;
    },
  ): Promise<OpenApi.WatchlistMember> {
    return this.transport<OpenApi.WatchlistMember>(
      "POST",
      "/api/v1/surveillance/watchlists/" +
        encodeURIComponent(watchlistId) +
        "/members",
      {
        body: {
          portrait_identity_id: input.portraitIdentityId,
          display_label: input.displayLabel ?? "",
          valid_from: input.validFrom,
          valid_until: input.validUntil,
        },
      },
    );
  }

  createSurveillanceTask(
    input: OpenApi.CreateSurveillanceTaskRequest,
  ): Promise<OpenApi.SurveillanceTask> {
    return this.transport<OpenApi.SurveillanceTask>(
      "POST",
      "/api/v1/surveillance/tasks",
      { body: input },
    );
  }

  listSurveillanceTasks(
    offset = 0,
    limit = 50,
  ): Promise<OpenApi.SurveillanceTaskPage> {
    return this.transport<OpenApi.SurveillanceTaskPage>(
      "GET",
      "/api/v1/surveillance/tasks?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  startSurveillanceTask(taskId: string): Promise<OpenApi.SurveillanceTask> {
    return this.transport<OpenApi.SurveillanceTask>(
      "POST",
      "/api/v1/surveillance/tasks/" + encodeURIComponent(taskId) + "/start",
    );
  }

  pauseSurveillanceTask(taskId: string): Promise<OpenApi.SurveillanceTask> {
    return this.transport<OpenApi.SurveillanceTask>(
      "POST",
      "/api/v1/surveillance/tasks/" + encodeURIComponent(taskId) + "/pause",
    );
  }

  listSurveillanceAlerts(
    input: {
      status?: OpenApi.AlertStatus;
      taskId?: string;
      cameraId?: string;
      offset?: number;
      limit?: number;
    } = {},
  ): Promise<OpenApi.AlertPage> {
    const query = new URLSearchParams();
    if (input.status) query.set("status", input.status);
    if (input.taskId) query.set("task_id", input.taskId);
    if (input.cameraId) query.set("camera_id", input.cameraId);
    query.set("offset", String(input.offset ?? 0));
    query.set("limit", String(input.limit ?? 50));
    return this.transport<OpenApi.AlertPage>(
      "GET",
      "/api/v1/surveillance/alerts?" + query.toString(),
    );
  }

  triageSurveillanceAlert(
    alertId: string,
    input: {
      expectedRevision: number;
      status: "confirmed" | "false_positive" | "ignored";
      reason: string;
      notes?: string;
    },
  ): Promise<OpenApi.AlertRecord> {
    return this.transport<OpenApi.AlertRecord>(
      "PATCH",
      "/api/v1/surveillance/alerts/" + encodeURIComponent(alertId) + "/status",
      {
        body: {
          expected_revision: input.expectedRevision,
          status: input.status,
          reason: input.reason,
          notes: input.notes ?? "",
        },
      },
    );
  }

  createSurveillanceAlertFeedback(
    alertId: string,
    correction: Record<string, unknown> = {},
  ): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>(
      "POST",
      "/api/v1/surveillance/alerts/" +
        encodeURIComponent(alertId) +
        "/feedback",
      { body: { correction } },
    );
  }

  createFeedback(feedback: Record<string, unknown>): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>("POST", "/api/v1/feedback", {
      body: feedback,
    });
  }

  listFeedback(): Promise<FeedbackRecord[]> {
    return this.transport<FeedbackRecord[]>("GET", "/api/v1/feedback");
  }

  reviewFeedback(
    feedbackId: string,
    status: "approved" | "rejected",
    notes = "",
  ): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>(
      "POST",
      "/api/v1/feedback/" + encodeURIComponent(feedbackId) + "/review",
      { body: { status, notes } },
    );
  }

  createHardSampleManifest(input: {
    datasetId: string;
    version: string;
    feedbackIds: string[];
    labelSchema?: string;
    split?: "train" | "validation" | "test";
  }): Promise<HardSampleManifest> {
    return this.transport<HardSampleManifest>(
      "POST",
      "/api/v1/hard-sample-manifests",
      {
        body: {
          dataset_id: input.datasetId,
          version: input.version,
          feedback_ids: input.feedbackIds,
          label_schema: input.labelSchema ?? "scenara.feedback.correction.v1",
          split: input.split ?? "train",
        },
      },
    );
  }

  createModelRelease(release: Record<string, unknown>): Promise<ModelRelease> {
    return this.transport<ModelRelease>("POST", "/api/v1/model-releases", {
      body: release,
    });
  }

  admitModelPackage(modelPackage: ModelPackage): Promise<ModelPackage> {
    return this.transport<ModelPackage>(
      "POST",
      "/api/v1/model-packages/admissions",
      { body: modelPackage },
    );
  }

  listModelReleases(): Promise<ModelRelease[]> {
    return this.transport<ModelRelease[]>("GET", "/api/v1/model-releases");
  }

  transitionModelRelease(
    modelId: string,
    version: string,
    status: "validated" | "approved" | "active" | "retired" | "candidate",
    reason: string,
  ): Promise<ModelRelease> {
    return this.transport<ModelRelease>(
      "POST",
      "/api/v1/model-releases/" +
        encodeURIComponent(modelId) +
        "/versions/" +
        encodeURIComponent(version) +
        "/transition",
      { body: { status, reason } },
    );
  }

  rollbackModelRelease(
    modelId: string,
    targetVersion: string,
    reason: string,
  ): Promise<ModelRelease> {
    return this.transport<ModelRelease>(
      "POST",
      "/api/v1/model-releases/" + encodeURIComponent(modelId) + "/rollback",
      { body: { target_version: targetVersion, reason } },
    );
  }

  listModelDeploymentEvents(limit = 100): Promise<ModelDeploymentEvent[]> {
    return this.transport<ModelDeploymentEvent[]>(
      "GET",
      "/api/v1/model-deployment-events?limit=" + String(limit),
    );
  }

  async waitResult(
    runId: string,
    options: { timeoutMs?: number; pollMs?: number } = {},
  ): Promise<ResultEnvelope> {
    const deadline = Date.now() + (options.timeoutMs ?? 300000);
    while (Date.now() < deadline) {
      const run = await this.getRun(runId);
      if (run.status === "completed") return await this.getResult(runId);
      if (["failed", "cancelled"].includes(run.status)) {
        throw new ScenaraError(
          run.error_code ?? "RUN_TERMINATED",
          run.termination_reason ?? run.status,
        );
      }
      await new Promise((resolve) =>
        setTimeout(resolve, options.pollMs ?? 500),
      );
    }
    throw new ScenaraError(
      "RUN_TIMEOUT",
      "Run did not complete before timeout",
    );
  }
}
