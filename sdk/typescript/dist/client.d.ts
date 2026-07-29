import type { Domain, ResultEnvelope, Run, RunPage, RunStatus } from "./types.js";
export type ScenaraTransport = <T>(method: "GET" | "POST", path: string, options?: {
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
    waitResult(runId: string, options?: {
        timeoutMs?: number;
        pollMs?: number;
    }): Promise<ResultEnvelope>;
}
//# sourceMappingURL=client.d.ts.map