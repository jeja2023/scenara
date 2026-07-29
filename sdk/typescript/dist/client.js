export class ScenaraError extends Error {
    code;
    details;
    constructor(code, message, details) {
        super(message);
        this.code = code;
        this.details = details;
        this.name = "ScenaraError";
    }
}
export class ScenaraClient {
    transport;
    constructor(options) {
        this.transport = options.transport;
    }
    getRun(runId) {
        return this.transport("GET", "/api/v1/runs/" + encodeURIComponent(runId));
    }
    listRuns(filters = {}) {
        const query = new URLSearchParams();
        if (filters.status)
            query.set("status", filters.status);
        if (filters.domain)
            query.set("domain", filters.domain);
        query.set("limit", String(filters.limit ?? 50));
        return this.transport("GET", "/api/v1/runs?" + query.toString());
    }
    createRun(input) {
        return this.transport("POST", "/api/v1/runs", {
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
    cancelRun(runId) {
        return this.transport("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/cancel");
    }
    async getResult(runId) {
        const page = await this.transport("GET", "/api/v1/runs/" + encodeURIComponent(runId) + "/result");
        return page.result;
    }
    async waitResult(runId, options = {}) {
        const deadline = Date.now() + (options.timeoutMs ?? 300000);
        while (Date.now() < deadline) {
            const run = await this.getRun(runId);
            if (run.status === "completed")
                return await this.getResult(runId);
            if (["failed", "cancelled"].includes(run.status)) {
                throw new ScenaraError(run.error_code ?? "RUN_TERMINATED", run.termination_reason ?? run.status);
            }
            await new Promise((resolve) => setTimeout(resolve, options.pollMs ?? 500));
        }
        throw new ScenaraError("RUN_TIMEOUT", "Run did not complete before timeout");
    }
}
//# sourceMappingURL=client.js.map