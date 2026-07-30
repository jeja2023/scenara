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
    pauseRun(runId) {
        return this.transport("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/pause");
    }
    resumeRun(runId) {
        return this.transport("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/resume");
    }
    deleteAsset(assetId) {
        return this.transport("DELETE", "/api/v1/media/assets/" + encodeURIComponent(assetId));
    }
    getAssetPreview(assetId) {
        return this.transport("GET", "/api/v1/media/assets/" + encodeURIComponent(assetId) + "/preview");
    }
    listPipelines() {
        return this.transport("GET", "/api/v1/pipelines");
    }
    listDomains() {
        return this.transport("GET", "/api/v1/domains");
    }
    listModels() {
        return this.transport("GET", "/api/v1/models");
    }
    createWebhookSubscription(input) {
        return this.transport("POST", "/api/v1/webhooks/subscriptions", {
            body: { name: input.name, url: input.url, secret: input.secret, event_types: input.eventTypes },
        });
    }
    listWebhookSubscriptions() {
        return this.transport("GET", "/api/v1/webhooks/subscriptions");
    }
    deleteWebhookSubscription(endpointId) {
        return this.transport("DELETE", "/api/v1/webhooks/subscriptions/" + encodeURIComponent(endpointId));
    }
    listWebhookDeliveries(limit = 100) {
        return this.transport("GET", "/api/v1/webhooks/deliveries?limit=" + String(limit));
    }
    createPortraitIdentity(displayName, metadata = {}) {
        return this.transport("POST", "/api/v1/portrait/identities", {
            body: { display_name: displayName, metadata },
        });
    }
    deletePortraitIdentity(identityId) {
        return this.transport("DELETE", "/api/v1/portrait/identities/" + encodeURIComponent(identityId));
    }
    enrollPortraitIdentity(identityId, enrollment) {
        return this.transport("POST", "/api/v1/portrait/identities/" + encodeURIComponent(identityId) + "/enrollments", { body: enrollment });
    }
    searchPortrait(query) {
        return this.transport("POST", "/api/v1/portrait/search", { body: query });
    }
    comparePortrait(comparison) {
        return this.transport("POST", "/api/v1/portrait/compare", {
            body: comparison,
        });
    }
    enterpriseStatus() {
        return this.transport("GET", "/api/v1/enterprise/status");
    }
    createFeedback(feedback) {
        return this.transport("POST", "/api/v1/feedback", { body: feedback });
    }
    listFeedback() {
        return this.transport("GET", "/api/v1/feedback");
    }
    reviewFeedback(feedbackId, status, notes = "") {
        return this.transport("POST", "/api/v1/feedback/" + encodeURIComponent(feedbackId) + "/review", { body: { status, notes } });
    }
    createHardSampleManifest(input) {
        return this.transport("POST", "/api/v1/hard-sample-manifests", {
            body: {
                dataset_id: input.datasetId,
                version: input.version,
                feedback_ids: input.feedbackIds,
                label_schema: input.labelSchema ?? "scenara.feedback.correction.v1",
                split: input.split ?? "train",
            },
        });
    }
    createModelRelease(release) {
        return this.transport("POST", "/api/v1/model-releases", { body: release });
    }
    listModelReleases() {
        return this.transport("GET", "/api/v1/model-releases");
    }
    transitionModelRelease(modelId, version, status, reason) {
        return this.transport("POST", "/api/v1/model-releases/" + encodeURIComponent(modelId) + "/versions/" + encodeURIComponent(version) + "/transition", { body: { status, reason } });
    }
    rollbackModelRelease(modelId, targetVersion, reason) {
        return this.transport("POST", "/api/v1/model-releases/" + encodeURIComponent(modelId) + "/rollback", { body: { target_version: targetVersion, reason } });
    }
    listModelDeploymentEvents(limit = 100) {
        return this.transport("GET", "/api/v1/model-deployment-events?limit=" + String(limit));
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