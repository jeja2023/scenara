import type { AccessFoundationStatus, ApiKeyRecord, CreateApiKeyResponse, Domain, IamSummary, MediaAsset, MediaAssetPage, MediaSource, MediaSourcePage, MediaSourceProbe, Membership, ModelPackage, Organization, ParseDocumentResponse, ParseImageResponse, ParseVideoResponse, PresignedMediaDownload, PortraitIntelligenceStatus, ProductCatalogItem, ProductEntitlement, Project, RepositoryContractCatalog, RepositoryTopology, ResultEnvelope, ResultPage, Run, RunPage, RunStatus, Role, ServiceAccount, UserAccount, WebhookDelivery, WebhookSubscription } from "./types.js";
import type { ControlPlaneRecord, CreateRunInput, ParseDocumentInput, ParseFileInput, ParseStreamInput, ParseVideoInput, ScenaraClientOptions, ScenaraTransport } from "./client_types.js";
export declare class ScenaraClientCore {
    protected readonly transport: ScenaraTransport;
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
}
//# sourceMappingURL=client_core.d.ts.map