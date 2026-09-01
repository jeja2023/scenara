import type {
  AccessFoundationStatus,
  ApiKeyRecord,
  CreateApiKeyResponse,
  Domain,
  IamSummary,
  MediaAsset,
  MediaAssetPage,
  MediaSource,
  MediaSourcePage,
  MediaSourceProbe,
  Membership,
  ModelPackage,
  Organization,
  ParseDocumentResponse,
  ParseImageResponse,
  ParseVideoResponse,
  PresignedMediaDownload,
  PresignedMediaUpload,
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
  Role,
  ServiceAccount,
  UserAccount,
  WebhookDelivery,
  WebhookSubscription,
} from "./types.js";
import { ScenaraError } from "./client_types.js";
import type {
  ControlPlaneRecord,
  CreateRunInput,
  ParseDocumentInput,
  ParseFileInput,
  ParseStreamInput,
  ParseVideoInput,
  ScenaraClientOptions,
  ScenaraTransport,
} from "./client_types.js";

export class ScenaraClientCore {
  protected readonly transport: ScenaraTransport;

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
}
