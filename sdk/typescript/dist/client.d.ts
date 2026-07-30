import type { Domain, FeedbackRecord, HardSampleManifest, ModelDeploymentEvent, ModelPackage, ModelRelease, ResultEnvelope, Run, RunPage, RunStatus, WebhookDelivery, WebhookSubscription } from "./types.js";
export type ScenaraTransport = <T>(method: "GET" | "POST" | "DELETE", path: string, options?: {
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