import type { AccessFoundationStatus, ApiKeyRecord, CreateApiKeyResponse, Domain, FeedbackRecord, HardSampleManifest, IamSummary, MediaAsset, MediaAssetPage, MediaSource, MediaSourcePage, MediaSourceProbe, Membership, ModelDeploymentEvent, ModelPackage, ModelRelease, Organization, ParseDocumentResponse, ParseImageResponse, ParseVideoResponse, PortraitIntelligenceStatus, ProductCatalogItem, ProductEntitlement, Project, RepositoryContractCatalog, RepositoryTopology, ResultEnvelope, Run, RunPage, RunStatus, SampleStrategy, Role, ServiceAccount, UserAccount, WebhookDelivery, WebhookSubscription } from "./types.js";
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
    /**
     * Download one derived image declared by a run result: a feature crop
     * (`crop_artifact_id` on a detected object) or a full unit image
     * (`frame_artifact_id` on a media unit).
     */
    getResultArtifact(runId: string, artifactId: string): Promise<Uint8Array>;
    pauseRun(runId: string): Promise<Run>;
    resumeRun(runId: string): Promise<Run>;
    listAssets(offset?: number, limit?: number): Promise<MediaAssetPage>;
    uploadAsset(input: {
        file: Blob;
        filename: string;
        kind?: "image" | "video" | "document";
    }): Promise<MediaAsset>;
    parseImage(input: ParseFileInput): Promise<ParseImageResponse>;
    parseVideo(input: ParseVideoInput): Promise<ParseVideoResponse>;
    parseDocument(input: ParseDocumentInput): Promise<ParseDocumentResponse>;
    parseStream(input: ParseStreamInput): Promise<Run>;
    deleteAsset(assetId: string): Promise<void>;
    getAssetPreview(assetId: string): Promise<Uint8Array>;
    listSources(offset?: number, limit?: number): Promise<MediaSourcePage>;
    createSource(input: {
        name: string;
        url: string;
        metadata?: Record<string, unknown>;
    }): Promise<MediaSource>;
    getSource(sourceId: string): Promise<MediaSource>;
    probeSource(sourceId: string, timeoutMs?: number): Promise<MediaSourceProbe>;
    deleteSource(sourceId: string): Promise<void>;
    listPipelines(): Promise<Record<string, unknown>[]>;
    listDomains(): Promise<Record<string, unknown>[]>;
    listProducts(): Promise<ProductCatalogItem[]>;
    getRepositoryTopology(): Promise<RepositoryTopology>;
    getRepositoryContracts(): Promise<RepositoryContractCatalog>;
    getAccessFoundation(): Promise<AccessFoundationStatus>;
    /**
     * Returns the Portrait Intelligence Foundation Platform contract: the six
     * strategic capability modules, three core assets, and per-capability
     * readiness state for the portrait domain.
     */
    getPortraitIntelligence(): Promise<PortraitIntelligenceStatus>;
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
    admitModelPackage(modelPackage: ModelPackage): Promise<ModelPackage>;
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