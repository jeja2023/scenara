import type { AccessFoundationStatus, ApiKeyRecord, CreateApiKeyResponse, Domain, FeedbackRecord, HardSampleManifest, IamSummary, Membership, ModelDeploymentEvent, ModelPackage, ModelRelease, Organization, ProductCatalogItem, ProductEntitlement, Project, RepositoryTopology, ResultEnvelope, Run, RunPage, RunStatus, Role, ServiceAccount, UserAccount, WebhookDelivery, WebhookSubscription } from "./types.js";
export type ScenaraTransport = <T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, options?: {
    body?: unknown;
    idempotencyKey?: string;
}) => Promise<T>;
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
export declare class ScenaraError extends Error {
    readonly code: string;
    readonly details?: unknown | undefined;
    constructor(code: string, message: string, details?: unknown | undefined);
}
export declare class ScenaraClient {
    private readonly transport;
    constructor(options: ScenaraClientOptions);
    getRun(runId: string): Promise<Run>;
    listRuns(filters?: {
        status?: RunStatus;
        domain?: Domain;
        limit?: number;
    }): Promise<RunPage>;
    createRun(input: CreateRunInput): Promise<Run>;
    cancelRun(runId: string): Promise<Run>;
    getResult(runId: string): Promise<ResultEnvelope>;
    pauseRun(runId: string): Promise<Run>;
    resumeRun(runId: string): Promise<Run>;
    deleteAsset(assetId: string): Promise<void>;
    getAssetPreview(assetId: string): Promise<Uint8Array>;
    listPipelines(): Promise<Record<string, unknown>[]>;
    listDomains(): Promise<Record<string, unknown>[]>;
    listProducts(): Promise<ProductCatalogItem[]>;
    getRepositoryTopology(): Promise<RepositoryTopology>;
    getAccessFoundation(): Promise<AccessFoundationStatus>;
    getIamSummary(): Promise<IamSummary>;
    createOrganization(displayName: string): Promise<Organization>;
    listOrganizations(): Promise<Organization[]>;
    createProject(input: {
        displayName: string;
        projectId?: string;
    }): Promise<Project>;
    listProjects(): Promise<Project[]>;
    createUser(input: {
        displayName: string;
        userId?: string;
        email?: string;
    }): Promise<UserAccount>;
    listUsers(): Promise<UserAccount[]>;
    createRole(input: {
        displayName: string;
        scopes: string[];
        productIds?: string[];
        roleId?: string;
    }): Promise<Role>;
    listRoles(): Promise<Role[]>;
    createMembership(input: {
        principalId: string;
        principalType: "user" | "service_account";
        roleIds: string[];
        projectId?: string;
    }): Promise<Membership>;
    listMemberships(): Promise<Membership[]>;
    createServiceAccount(input: {
        displayName: string;
        scopes: string[];
        productIds?: string[];
        serviceAccountId?: string;
    }): Promise<ServiceAccount>;
    listServiceAccounts(): Promise<ServiceAccount[]>;
    createApiKey(input: {
        serviceAccountId: string;
        name: string;
        scopes?: string[];
        productIds?: string[];
        expiresAt?: number;
    }): Promise<CreateApiKeyResponse>;
    listApiKeys(): Promise<ApiKeyRecord[]>;
    revokeApiKey(keyId: string): Promise<ApiKeyRecord>;
    createProductEntitlement(input: {
        productId: string;
        status?: "active" | "suspended";
        source?: "manual" | "enterprise_license" | "system";
        projectId?: string;
    }): Promise<ProductEntitlement>;
    listProductEntitlements(): Promise<ProductEntitlement[]>;
    updateProductEntitlement(input: {
        productId: string;
        status: "active" | "suspended";
        source?: "manual" | "enterprise_license" | "system";
    }): Promise<ProductEntitlement>;
    listModels(): Promise<ModelPackage[]>;
    createWebhookSubscription(input: {
        name: string;
        url: string;
        secret: string;
        eventTypes: string[];
    }): Promise<WebhookSubscription>;
    listWebhookSubscriptions(): Promise<WebhookSubscription[]>;
    deleteWebhookSubscription(endpointId: string): Promise<void>;
    listWebhookDeliveries(limit?: number): Promise<WebhookDelivery[]>;
    createPortraitIdentity(displayName: string, metadata?: Record<string, unknown>): Promise<Record<string, unknown>>;
    deletePortraitIdentity(identityId: string): Promise<void>;
    enrollPortraitIdentity(identityId: string, enrollment: Record<string, unknown>): Promise<Record<string, unknown>>;
    searchPortrait(query: Record<string, unknown>): Promise<Record<string, unknown>>;
    comparePortrait(comparison: Record<string, unknown>): Promise<Record<string, unknown>>;
    enterpriseStatus(): Promise<Record<string, unknown>>;
    createFeedback(feedback: Record<string, unknown>): Promise<FeedbackRecord>;
    listFeedback(): Promise<FeedbackRecord[]>;
    reviewFeedback(feedbackId: string, status: "approved" | "rejected", notes?: string): Promise<FeedbackRecord>;
    createHardSampleManifest(input: {
        datasetId: string;
        version: string;
        feedbackIds: string[];
        labelSchema?: string;
        split?: "train" | "validation" | "test";
    }): Promise<HardSampleManifest>;
    createModelRelease(release: Record<string, unknown>): Promise<ModelRelease>;
    listModelReleases(): Promise<ModelRelease[]>;
    transitionModelRelease(modelId: string, version: string, status: "validated" | "approved" | "active" | "retired" | "candidate", reason: string): Promise<ModelRelease>;
    rollbackModelRelease(modelId: string, targetVersion: string, reason: string): Promise<ModelRelease>;
    listModelDeploymentEvents(limit?: number): Promise<ModelDeploymentEvent[]>;
    waitResult(runId: string, options?: {
        timeoutMs?: number;
        pollMs?: number;
    }): Promise<ResultEnvelope>;
}
//# sourceMappingURL=client.d.ts.map