import type { Domain, SampleStrategy } from "./types.js";
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
//# sourceMappingURL=client_types.d.ts.map