export type Domain = "portrait" | "ocr";
export type RunStatus = "queued" | "running" | "pausing" | "paused" | "completed" | "failed" | "cancelling" | "cancelled";
export interface PipelineRef {
    pipeline_id: string;
    version: string;
}
export interface MediaAsset {
    asset_id: string;
    kind: "image" | "video" | "document";
    filename?: string | null;
    content_type: string;
    size_bytes: number;
    sha256: string;
    temporary: boolean;
    created_at: number;
}
export interface Run {
    run_id: string;
    domain: Domain;
    pipeline: PipelineRef;
    asset_id?: string | null;
    source_id?: string | null;
    status: RunStatus;
    revision: number;
    progress: number;
    error_code?: string | null;
    termination_reason?: string | null;
    created_at: number;
    updated_at: number;
}
export interface RunPage {
    items: Run[];
    offset: number;
    limit: number;
    total: number;
}
export interface ResultEnvelope {
    schema_version: string;
    run_id: string;
    domain: Domain;
    pipeline: PipelineRef;
    units: Record<string, unknown>[];
    domain_payload: Record<string, unknown>;
    models: Record<string, unknown>[];
    timings: Record<string, number>;
    warnings: string[];
    created_at: number;
}
export interface ResultPage {
    result: ResultEnvelope;
    unit_offset: number;
    unit_limit: number;
    unit_total: number;
}
export interface ParseImageResponse {
    asset: MediaAsset;
    run: Run;
    result: ResultEnvelope | null;
}
//# sourceMappingURL=types.d.ts.map