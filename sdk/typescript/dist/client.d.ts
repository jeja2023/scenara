import type { AccessFoundationStatus, AuditEventPage, ApiKeyRecord, CreateApiKeyResponse, DatasetRecord, DatasetVersion, Domain, FeedbackRecord, HardSampleManifest, IamSummary, MediaAsset, MediaAssetPage, MediaSource, MediaSourcePage, MediaSourceProbe, Membership, ModelDeploymentEvent, ModelPackage, ModelRelease, Organization, ParseDocumentResponse, ParseImageResponse, ParseVideoResponse, PresignedMediaDownload, PortraitCompareResponse, IndexDefinition, IndexHit, IndexRecordView, SearchResponse, SavedSearch, SavedSearchPage, PortraitIntelligenceStatus, ProductCatalogItem, ProductEntitlement, Project, RepositoryContractCatalog, RepositoryTopology, ResultEnvelope, ResultPage, Run, RunPage, RunStatus, SampleStrategy, Role, ServiceAccount, UserAccount, WebhookDelivery, WebhookSubscription } from "./types.js";
export type ScenaraTransport = <T>(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path: string, options?: {
    body?: unknown;
    idempotencyKey?: string;
}) => Promise<T>;
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
export declare class ScenaraError extends Error {
    readonly code: string;
    readonly details?: unknown | undefined;
    constructor(code: string, message: string, details?: unknown | undefined);
}
export declare class ScenaraClient {
    private readonly transport;
    constructor(options: ScenaraClientOptions);
    controlPlane<T = ControlPlaneRecord>(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: ControlPlaneRecord): Promise<T>;
    getRun(runId: string): Promise<Run>;
    listRuns(filters?: {
        status?: RunStatus;
        domain?: Domain;
        limit?: number;
    }): Promise<RunPage>;
    createRun(input: CreateRunInput): Promise<Run>;
    cancelRun(runId: string): Promise<Run>;
    getResult(runId: string): Promise<ResultEnvelope>;
    getResultPage(runId: string, unitOffset?: number, unitLimit?: number): Promise<ResultPage>;
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
    uploadAssetDirect(input: {
        file: Blob;
        filename: string;
        kind?: "image" | "video" | "document";
    }): Promise<MediaAsset>;
    getAssetDownloadUrl(assetId: string, expiresIn?: number): Promise<PresignedMediaDownload>;
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
    getStreamSession(sessionId: string): Promise<Record<string, unknown>>;
    cancelStreamSession(sessionId: string): Promise<Record<string, unknown>>;
    createIdentityProvider(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    listIdentityProviders(): Promise<ControlPlaneRecord[]>;
    probeIdentityProvider(providerId: string): Promise<ControlPlaneRecord>;
    requestProjectLifecycle(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    decideProjectLifecycle(requestId: string, input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    setAuditRetention(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    purgeAudit(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    createSession(input: {
        userId: string;
        ttlSeconds?: number;
    }): Promise<ControlPlaneRecord>;
    setUserDisabled(userId: string, disabled: boolean): Promise<UserAccount>;
    createQuotaPlan(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    checkQuota(metric: string, amount?: number): Promise<ControlPlaneRecord>;
    createAnnotationTask(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    registerAnnotationProvider(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    probeAnnotationProvider(providerId: string): Promise<ControlPlaneRecord>;
    reviewAnnotationTask(taskId: string, input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    createFlow(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    executeFlow(flowId: string, input?: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    decideFlowApproval(approvalId: string, input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    createSearchRankingProfile(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    evaluateSearch(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    rebuildIndex(indexId: string): Promise<ControlPlaneRecord>;
    createIndex(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    registerIndexBackend(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    probeIndexBackend(backendId: string): Promise<ControlPlaneRecord>;
    registerSearchReranker(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    probeSearchReranker(rerankerId: string): Promise<ControlPlaneRecord>;
    registerEdgeDevice(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    heartbeatEdgeDevice(deviceId: string, input?: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    deployEdge(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    acknowledgeEdgeDeployment(deploymentId: string, input?: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    registerAgentTool(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    proposeAgentAction(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    decideAgentAction(actionId: string, input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    executeAgentAction(actionId: string): Promise<ControlPlaneRecord>;
    recordAgentTrace(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    recordAgentEvaluation(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    putAgentMemory(input: ControlPlaneRecord): Promise<ControlPlaneRecord>;
    getAgentMemory(namespace: string, key: string): Promise<ControlPlaneRecord | null>;
    getDeploymentTopology(): Promise<ControlPlaneRecord>;
    listDatasets(offset?: number, limit?: number): Promise<{
        items: DatasetRecord[];
        offset: number;
        limit: number;
        total: number;
    }>;
    createDataset(input: {
        name: string;
        description?: string;
        metadata?: Record<string, unknown>;
    }): Promise<DatasetRecord>;
    getDataset(datasetId: string): Promise<DatasetRecord>;
    updateDataset(datasetId: string, input: Partial<Pick<DatasetRecord, "name" | "description" | "status" | "metadata">>): Promise<DatasetRecord>;
    createDatasetVersion(datasetId: string, input: {
        version: string;
        manifestSha256: string;
        assetIds?: string[];
        qualityScore?: number | null;
        lineage?: Record<string, unknown>;
        annotationSummary?: Record<string, unknown>;
    }): Promise<DatasetVersion>;
    listDatasetVersions(datasetId: string, offset?: number, limit?: number): Promise<{
        items: DatasetVersion[];
        offset: number;
        limit: number;
        total: number;
    }>;
    transitionDatasetVersion(versionId: string, status: "validated" | "published" | "retired"): Promise<DatasetVersion>;
    listAuditEvents(filters?: {
        action?: string;
        resourceType?: string;
        principalId?: string;
        outcome?: string;
        offset?: number;
        limit?: number;
    }): Promise<AuditEventPage>;
    enrollPortraitIdentityImage(identityId: string, file: Blob, filename?: string, options?: {
        featureSpaceId?: string;
        quality?: number;
    }): Promise<Record<string, unknown>>;
    searchPortraitImage(file: Blob, filename?: string, options?: {
        featureSpaceId?: string;
        limit?: number;
        threshold?: number;
    }): Promise<Record<string, unknown>>;
    comparePortraitImages(left: Blob, right: Blob, options?: {
        leftFilename?: string;
        rightFilename?: string;
        featureSpaceId?: string;
        threshold?: number;
    }): Promise<PortraitCompareResponse>;
    comparePortraitAssets(input: {
        leftAssetId: string;
        rightAssetId: string;
        featureSpaceId?: string;
        threshold?: number;
    }): Promise<PortraitCompareResponse>;
    comparePortraitAssetImage(assetId: string, image: Blob, options?: {
        filename?: string;
        featureSpaceId?: string;
        threshold?: number;
    }): Promise<PortraitCompareResponse>;
    comparePortraitImageAsset(image: Blob, assetId: string, options?: {
        filename?: string;
        featureSpaceId?: string;
        threshold?: number;
    }): Promise<PortraitCompareResponse>;
    listSearchIndexes(domain?: string): Promise<IndexDefinition[]>;
    listSearchIndexRecords(indexId: string, filters?: {
        sourceType?: string;
        sourceId?: string;
        offset?: number;
        limit?: number;
    }): Promise<IndexRecordView[]>;
    querySearchIndexText(indexId: string, query: string, limit?: number): Promise<Record<string, unknown>[]>;
    querySearchIndexVector(indexId: string, vector: number[], options?: {
        limit?: number;
        threshold?: number;
    }): Promise<IndexHit[]>;
    searchText(input: {
        query: string;
        domains?: string[];
        mediaKinds?: string[];
        limit?: number;
    }): Promise<SearchResponse>;
    searchPortraitResults(input: {
        file: Blob;
        filename?: string;
        featureSpaceId?: string;
        mediaKinds?: string[];
        limit?: number;
        threshold?: number;
    }): Promise<SearchResponse>;
    searchPortraitAsset(input: {
        assetId: string;
        featureSpaceId?: string;
        mediaKinds?: string[];
        limit?: number;
        threshold?: number;
    }): Promise<SearchResponse>;
    createSavedSearch(input: {
        name: string;
        mode: "text" | "portrait";
        definition: Record<string, unknown>;
        description?: string;
    }): Promise<SavedSearch>;
    listSavedSearches(offset?: number, limit?: number): Promise<SavedSearchPage>;
    getSavedSearch(savedSearchId: string): Promise<SavedSearch>;
    updateSavedSearch(savedSearchId: string, input: {
        name?: string;
        description?: string;
        definition?: Record<string, unknown>;
    }): Promise<SavedSearch>;
    runSavedSearch(savedSearchId: string): Promise<SearchResponse>;
    deleteSavedSearch(savedSearchId: string): Promise<void>;
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