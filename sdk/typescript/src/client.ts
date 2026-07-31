import type {
  AccessFoundationStatus,
  ApiKeyRecord,
  CreateApiKeyResponse,
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

export type ScenaraTransport = <T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  options?: { body?: unknown; idempotencyKey?: string },
) => Promise<T>;

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
  maxUnits?: number;
  sampleStrategy?: SampleStrategy;
  sampleStartMs?: number;
  sampleEndMs?: number;
  sceneChangeThreshold?: number;
  frameMaxEdge?: number;
  pageScale?: number;
  waitMs?: number;
}

export interface ParseDocumentInput extends ParseFileInput {
  maxUnits?: number;
  pageScale?: number;
  waitMs?: number;
}

export interface ParseStreamInput {
  sourceId: string;
  domain?: Domain;
  pipelineId?: string;
  pipelineVersion?: string;
  sampleIntervalMs?: number;
  maxUnits?: number;
  sampleStrategy?: SampleStrategy;
  sampleStartMs?: number;
  sampleEndMs?: number;
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
  constructor(readonly code: string, message: string, readonly details?: unknown) {
    super(message);
    this.name = "ScenaraError";
  }
}

export class ScenaraClient {
  private readonly transport: ScenaraTransport;

  constructor(options: ScenaraClientOptions) {
    this.transport = options.transport;
  }

  getRun(runId: string): Promise<Run> {
    return this.transport<Run>("GET", "/api/v1/runs/" + encodeURIComponent(runId));
  }

  listRuns(filters: { status?: RunStatus; domain?: Domain; limit?: number } = {}): Promise<RunPage> {
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
        pipeline: { pipeline_id: input.pipelineId, version: input.pipelineVersion },
        asset_id: input.assetId,
        source_id: input.sourceId,
        parameters: input.parameters ?? {},
        priority: input.priority ?? 0,
        wait_ms: input.waitMs ?? 0,
      },
    });
  }

  cancelRun(runId: string): Promise<Run> {
    return this.transport<Run>("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/cancel");
  }

  async getResult(runId: string): Promise<ResultEnvelope> {
    const page = await this.transport<ResultPage>("GET", "/api/v1/runs/" + encodeURIComponent(runId) + "/result");
    return page.result;
  }

  pauseRun(runId: string): Promise<Run> {
    return this.transport<Run>("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/pause");
  }

  resumeRun(runId: string): Promise<Run> {
    return this.transport<Run>("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/resume");
  }

  listAssets(offset = 0, limit = 50): Promise<MediaAssetPage> {
    return this.transport<MediaAssetPage>(
      "GET",
      "/api/v1/media/assets?offset=" + String(offset) + "&limit=" + String(limit),
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
    return this.transport<MediaAsset>("POST", "/api/v1/media/assets", { body: form });
  }

  parseImage(input: ParseFileInput): Promise<ParseImageResponse> {
    const form = new FormData();
    form.append("file", input.file, input.filename);
    form.append("domain", input.domain ?? "portrait");
    if (input.pipelineId) form.append("pipeline_id", input.pipelineId);
    if (input.pipelineVersion) form.append("pipeline_version", input.pipelineVersion);
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
    if (input.pipelineVersion) form.append("pipeline_version", input.pipelineVersion);
    form.append("sample_interval_ms", String(input.sampleIntervalMs ?? 1000));
    form.append("max_units", String(input.maxUnits ?? 64));
    form.append("sample_strategy", input.sampleStrategy ?? "interval");
    form.append("sample_start_ms", String(input.sampleStartMs ?? 0));
    if (input.sampleEndMs !== undefined) form.append("sample_end_ms", String(input.sampleEndMs));
    form.append("scene_change_threshold", String(input.sceneChangeThreshold ?? 0.35));
    if (input.frameMaxEdge !== undefined) form.append("frame_max_edge", String(input.frameMaxEdge));
    form.append("page_scale", String(input.pageScale ?? 1.5));
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
    if (input.pipelineVersion) form.append("pipeline_version", input.pipelineVersion);
    form.append("max_units", String(input.maxUnits ?? 64));
    form.append("page_scale", String(input.pageScale ?? 1.5));
    form.append("wait_ms", String(input.waitMs ?? 0));
    return this.transport<ParseDocumentResponse>("POST", "/api/v1/parse/document", {
      body: form,
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
    });
  }

  parseStream(input: ParseStreamInput): Promise<Run> {
    const domain = input.domain ?? "portrait";
    const pipelineId = input.pipelineId ?? (
      domain === "portrait" ? "portrait.person-detection" : "ocr.document"
    );
    const pipeline = {
      pipeline_id: pipelineId,
      ...(input.pipelineVersion === undefined ? {} : { version: input.pipelineVersion }),
    };
    return this.transport<Run>("POST", "/api/v1/parse/stream", {
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
      body: {
        source_id: input.sourceId,
        domain,
        pipeline,
        parameters: {
          sample_interval_ms: input.sampleIntervalMs ?? 1000,
          max_units: input.maxUnits ?? 64,
          sample_strategy: input.sampleStrategy ?? "interval",
          sample_start_ms: input.sampleStartMs ?? 0,
          ...(input.sampleEndMs === undefined ? {} : { sample_end_ms: input.sampleEndMs }),
          scene_change_threshold: input.sceneChangeThreshold ?? 0.35,
          ...(input.frameMaxEdge === undefined ? {} : { frame_max_edge: input.frameMaxEdge }),
          max_reconnect_attempts: input.maxReconnectAttempts ?? 3,
          connect_timeout_ms: input.connectTimeoutMs ?? 10000,
          read_timeout_ms: input.readTimeoutMs ?? 10000,
        },
        priority: input.priority ?? 0,
        wait_ms: input.waitMs ?? 0,
      },
    });
  }

  deleteAsset(assetId: string): Promise<void> {
    return this.transport<void>("DELETE", "/api/v1/media/assets/" + encodeURIComponent(assetId));
  }

  getAssetPreview(assetId: string): Promise<Uint8Array> {
    return this.transport<Uint8Array>("GET", "/api/v1/media/assets/" + encodeURIComponent(assetId) + "/preview");
  }

  listSources(offset = 0, limit = 50): Promise<MediaSourcePage> {
    return this.transport<MediaSourcePage>(
      "GET",
      "/api/v1/media/sources?offset=" + String(offset) + "&limit=" + String(limit),
    );
  }

  createSource(input: {
    name: string;
    url: string;
    metadata?: Record<string, unknown>;
  }): Promise<MediaSource> {
    return this.transport<MediaSource>("POST", "/api/v1/media/sources", {
      body: { name: input.name, url: input.url, metadata: input.metadata ?? {} },
    });
  }

  getSource(sourceId: string): Promise<MediaSource> {
    return this.transport<MediaSource>("GET", "/api/v1/media/sources/" + encodeURIComponent(sourceId));
  }

  probeSource(sourceId: string, timeoutMs = 10000): Promise<MediaSourceProbe> {
    return this.transport<MediaSourceProbe>(
      "POST",
      "/api/v1/media/sources/" + encodeURIComponent(sourceId) + "/probe?timeout_ms=" + String(timeoutMs),
    );
  }

  deleteSource(sourceId: string): Promise<void> {
    return this.transport<void>("DELETE", "/api/v1/media/sources/" + encodeURIComponent(sourceId));
  }

  listPipelines(): Promise<Record<string, unknown>[]> {
    return this.transport<Record<string, unknown>[]>("GET", "/api/v1/pipelines");
  }

  listDomains(): Promise<Record<string, unknown>[]> {
    return this.transport<Record<string, unknown>[]>("GET", "/api/v1/domains");
  }

  listProducts(): Promise<ProductCatalogItem[]> {
    return this.transport<ProductCatalogItem[]>("GET", "/api/v1/platform/products");
  }

  getRepositoryTopology(): Promise<RepositoryTopology> {
    return this.transport<RepositoryTopology>("GET", "/api/v1/platform/repositories");
  }

  getRepositoryContracts(): Promise<RepositoryContractCatalog> {
    return this.transport<RepositoryContractCatalog>("GET", "/api/v1/platform/contracts");
  }

  getAccessFoundation(): Promise<AccessFoundationStatus> {
    return this.transport<AccessFoundationStatus>("GET", "/api/v1/platform/access-foundation");
  }

  /**
   * Returns the Portrait Intelligence Foundation Platform contract: the six
   * strategic capability modules, three core assets, and per-capability
   * readiness state for the portrait domain.
   */
  getPortraitIntelligence(): Promise<PortraitIntelligenceStatus> {
    return this.transport<PortraitIntelligenceStatus>("GET", "/api/v1/platform/portrait-intelligence");
  }

  getIamSummary(): Promise<IamSummary> {
    return this.transport<IamSummary>("GET", "/api/v1/platform/iam/summary");
  }

  createOrganization(displayName: string): Promise<Organization> {
    return this.transport<Organization>("POST", "/api/v1/platform/organizations", {
      body: { display_name: displayName },
    });
  }

  listOrganizations(): Promise<Organization[]> {
    return this.transport<Organization[]>("GET", "/api/v1/platform/organizations");
  }

  createProject(input: { displayName: string; projectId?: string }): Promise<Project> {
    return this.transport<Project>("POST", "/api/v1/platform/projects", {
      body: { display_name: input.displayName, project_id: input.projectId },
    });
  }

  listProjects(): Promise<Project[]> {
    return this.transport<Project[]>("GET", "/api/v1/platform/projects");
  }

  createUser(input: { displayName: string; userId?: string; email?: string }): Promise<UserAccount> {
    return this.transport<UserAccount>("POST", "/api/v1/platform/users", {
      body: { display_name: input.displayName, user_id: input.userId, email: input.email },
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
    return this.transport<ServiceAccount>("POST", "/api/v1/platform/service-accounts", {
      body: {
        display_name: input.displayName,
        service_account_id: input.serviceAccountId,
        scopes: input.scopes,
        product_ids: input.productIds ?? [],
      },
    });
  }

  listServiceAccounts(): Promise<ServiceAccount[]> {
    return this.transport<ServiceAccount[]>("GET", "/api/v1/platform/service-accounts");
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
      "/api/v1/platform/service-accounts/" + encodeURIComponent(input.serviceAccountId) + "/api-keys",
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
    return this.transport<ProductEntitlement>("POST", "/api/v1/platform/product-entitlements", {
      body: {
        product_id: input.productId,
        status: input.status ?? "active",
        source: input.source ?? "manual",
        project_id: input.projectId,
      },
    });
  }

  listProductEntitlements(): Promise<ProductEntitlement[]> {
    return this.transport<ProductEntitlement[]>("GET", "/api/v1/platform/product-entitlements");
  }

  updateProductEntitlement(input: {
    productId: string;
    status: "active" | "suspended";
    source?: "manual" | "enterprise_license" | "system";
  }): Promise<ProductEntitlement> {
    return this.transport<ProductEntitlement>(
      "PUT",
      "/api/v1/platform/product-entitlements/" + encodeURIComponent(input.productId),
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
    return this.transport<WebhookSubscription>("POST", "/api/v1/webhooks/subscriptions", {
      body: { name: input.name, url: input.url, secret: input.secret, event_types: input.eventTypes },
    });
  }

  listWebhookSubscriptions(): Promise<WebhookSubscription[]> {
    return this.transport<WebhookSubscription[]>("GET", "/api/v1/webhooks/subscriptions");
  }

  deleteWebhookSubscription(endpointId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/webhooks/subscriptions/" + encodeURIComponent(endpointId),
    );
  }

  listWebhookDeliveries(limit = 100): Promise<WebhookDelivery[]> {
    return this.transport<WebhookDelivery[]>("GET", "/api/v1/webhooks/deliveries?limit=" + String(limit));
  }

  createPortraitIdentity(
    displayName: string,
    metadata: Record<string, unknown> = {},
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>("POST", "/api/v1/portrait/identities", {
      body: { display_name: displayName, metadata },
    });
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
      "/api/v1/portrait/identities/" + encodeURIComponent(identityId) + "/enrollments",
      { body: enrollment },
    );
  }

  searchPortrait(query: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>("POST", "/api/v1/portrait/search", { body: query });
  }

  comparePortrait(comparison: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>("POST", "/api/v1/portrait/compare", {
      body: comparison,
    });
  }

  enterpriseStatus(): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>("GET", "/api/v1/enterprise/status");
  }

  createFeedback(feedback: Record<string, unknown>): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>("POST", "/api/v1/feedback", { body: feedback });
  }

  listFeedback(): Promise<FeedbackRecord[]> {
    return this.transport<FeedbackRecord[]>("GET", "/api/v1/feedback");
  }

  reviewFeedback(feedbackId: string, status: "approved" | "rejected", notes = ""): Promise<FeedbackRecord> {
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
    return this.transport<HardSampleManifest>("POST", "/api/v1/hard-sample-manifests", {
      body: {
        dataset_id: input.datasetId,
        version: input.version,
        feedback_ids: input.feedbackIds,
        label_schema: input.labelSchema ?? "scenara.feedback.correction.v1",
        split: input.split ?? "train",
      },
    });
  }

  createModelRelease(release: Record<string, unknown>): Promise<ModelRelease> {
    return this.transport<ModelRelease>("POST", "/api/v1/model-releases", { body: release });
  }

  admitModelPackage(modelPackage: ModelPackage): Promise<ModelPackage> {
    return this.transport<ModelPackage>("POST", "/api/v1/model-packages/admissions", { body: modelPackage });
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
      "/api/v1/model-releases/" + encodeURIComponent(modelId) + "/versions/" + encodeURIComponent(version) + "/transition",
      { body: { status, reason } },
    );
  }

  rollbackModelRelease(modelId: string, targetVersion: string, reason: string): Promise<ModelRelease> {
    return this.transport<ModelRelease>(
      "POST",
      "/api/v1/model-releases/" + encodeURIComponent(modelId) + "/rollback",
      { body: { target_version: targetVersion, reason } },
    );
  }

  listModelDeploymentEvents(limit = 100): Promise<ModelDeploymentEvent[]> {
    return this.transport<ModelDeploymentEvent[]>("GET", "/api/v1/model-deployment-events?limit=" + String(limit));
  }

  async waitResult(runId: string, options: { timeoutMs?: number; pollMs?: number } = {}): Promise<ResultEnvelope> {
    const deadline = Date.now() + (options.timeoutMs ?? 300000);
    while (Date.now() < deadline) {
      const run = await this.getRun(runId);
      if (run.status === "completed") return await this.getResult(runId);
      if (["failed", "cancelled"].includes(run.status)) {
        throw new ScenaraError(run.error_code ?? "RUN_TERMINATED", run.termination_reason ?? run.status);
      }
      await new Promise((resolve) => setTimeout(resolve, options.pollMs ?? 500));
    }
    throw new ScenaraError("RUN_TIMEOUT", "Run did not complete before timeout");
  }
}
