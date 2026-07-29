import type { Domain, ResultEnvelope, ResultPage, Run, RunPage, RunStatus } from "./types.js";

export type ScenaraTransport = <T>(
  method: "GET" | "POST",
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
