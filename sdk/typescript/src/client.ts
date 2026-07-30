import type {
  AccessFoundationStatus,
  ApiKeyRecord,
  CreateApiKeyResponse,
  Domain,
  FeedbackRecord,
  HardSampleManifest,
  IamSummary,
  Membership,
  ModelDeploymentEvent,
  ModelPackage,
  ModelRelease,
  Organization,
  ProductCatalogItem,
  ProductEntitlement,
  Project,
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

  deleteAsset(assetId: string): Promise<void> {
    return this.transport<void>("DELETE", "/api/v1/media/assets/" + encodeURIComponent(assetId));
  }

  getAssetPreview(assetId: string): Promise<Uint8Array> {
    return this.transport<Uint8Array>("GET", "/api/v1/media/assets/" + encodeURIComponent(assetId) + "/preview");
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

  getAccessFoundation(): Promise<AccessFoundationStatus> {
    return this.transport<AccessFoundationStatus>("GET", "/api/v1/platform/access-foundation");
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
