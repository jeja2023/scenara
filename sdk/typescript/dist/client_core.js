import { ScenaraError } from "./client_types.js";
export class ScenaraClientCore {
    transport;
    constructor(options) {
        this.transport = options.transport;
    }
    controlPlane(method, path, body) {
        return this.transport(method, path, body === undefined ? undefined : { body });
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
                pipeline: {
                    pipeline_id: input.pipelineId,
                    version: input.pipelineVersion,
                },
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
        const page = await this.getResultPage(runId, 0, 1000);
        const units = [...page.result.units];
        let total = page.unit_total;
        while (units.length < total) {
            const next = await this.getResultPage(runId, units.length, 1000);
            if (!next.result.units.length)
                break;
            units.push(...next.result.units);
            total = Math.max(total, next.unit_total);
        }
        return { ...page.result, units };
    }
    getResultPage(runId, unitOffset = 0, unitLimit = 100) {
        const query = new URLSearchParams({
            unit_offset: String(unitOffset),
            unit_limit: String(unitLimit),
        });
        return this.transport("GET", "/api/v1/runs/" +
            encodeURIComponent(runId) +
            "/result?" +
            query.toString());
    }
    /**
     * Download one derived image declared by a run result: a feature crop
     * (`crop_artifact_id` on a detected object) or a full unit image
     * (`frame_artifact_id` on a media unit).
     */
    getResultArtifact(runId, artifactId) {
        return this.transport("GET", "/api/v1/runs/" +
            encodeURIComponent(runId) +
            "/artifacts/" +
            encodeURIComponent(artifactId));
    }
    pauseRun(runId) {
        return this.transport("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/pause");
    }
    resumeRun(runId) {
        return this.transport("POST", "/api/v1/runs/" + encodeURIComponent(runId) + "/resume");
    }
    listAssets(offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/media/assets?offset=" +
            String(offset) +
            "&limit=" +
            String(limit));
    }
    uploadAsset(input) {
        const form = new FormData();
        form.append("file", input.file, input.filename);
        form.append("kind", input.kind ?? "image");
        return this.transport("POST", "/api/v1/media/assets", {
            body: form,
        });
    }
    async uploadAssetDirect(input) {
        const digest = await crypto.subtle.digest("SHA-256", await input.file.arrayBuffer());
        const sha256 = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
        const request = {
            filename: input.filename,
            content_type: input.file.type || "application/octet-stream",
            kind: input.kind ?? "video",
            size_bytes: input.file.size,
            sha256,
        };
        const upload = await this.transport("POST", "/api/v1/media/uploads/presign", {
            body: request,
        });
        const response = await fetch(upload.url, {
            method: upload.method,
            headers: upload.headers,
            body: input.file,
        });
        if (!response.ok)
            throw new ScenaraError("OBJECT_UPLOAD_FAILED", `Object upload failed with ${response.status}`);
        return this.transport("POST", "/api/v1/media/uploads/complete", {
            body: {
                ...request,
                upload_id: upload.upload_id,
                upload_token: upload.upload_token,
                expires_at: upload.expires_at,
            },
        });
    }
    getAssetDownloadUrl(assetId, expiresIn) {
        const query = expiresIn === undefined ? "" : "?expires_in=" + String(expiresIn);
        return this.transport("GET", "/api/v1/media/assets/" +
            encodeURIComponent(assetId) +
            "/download-url" +
            query);
    }
    parseImage(input) {
        const form = new FormData();
        form.append("file", input.file, input.filename);
        form.append("domain", input.domain ?? "portrait");
        if (input.pipelineId)
            form.append("pipeline_id", input.pipelineId);
        if (input.pipelineVersion)
            form.append("pipeline_version", input.pipelineVersion);
        return this.transport("POST", "/api/v1/parse/image", {
            body: form,
            idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
        });
    }
    parseVideo(input) {
        const form = new FormData();
        form.append("file", input.file, input.filename);
        form.append("domain", input.domain ?? "portrait");
        if (input.pipelineId)
            form.append("pipeline_id", input.pipelineId);
        if (input.pipelineVersion)
            form.append("pipeline_version", input.pipelineVersion);
        form.append("sample_interval_ms", String(input.sampleIntervalMs ?? 1000));
        form.append("sample_strategy", input.sampleStrategy ?? "interval");
        form.append("sample_start_ms", String(input.sampleStartMs ?? 0));
        if (input.sampleEndMs !== undefined)
            form.append("sample_end_ms", String(input.sampleEndMs));
        form.append("scene_change_threshold", String(input.sceneChangeThreshold ?? 0.35));
        if (input.frameMaxEdge !== undefined)
            form.append("frame_max_edge", String(input.frameMaxEdge));
        form.append("page_scale", String(input.pageScale ?? 1.5));
        if (input.cameraId)
            form.append("camera_id", input.cameraId);
        if (input.recordingStartedAt !== undefined)
            form.append("recording_started_at", String(input.recordingStartedAt));
        form.append("wait_ms", String(input.waitMs ?? 0));
        return this.transport("POST", "/api/v1/parse/video", {
            body: form,
            idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
        });
    }
    parseDocument(input) {
        const form = new FormData();
        form.append("file", input.file, input.filename);
        form.append("domain", input.domain ?? "ocr");
        if (input.pipelineId)
            form.append("pipeline_id", input.pipelineId);
        if (input.pipelineVersion)
            form.append("pipeline_version", input.pipelineVersion);
        form.append("page_scale", String(input.pageScale ?? 1.5));
        form.append("wait_ms", String(input.waitMs ?? 0));
        return this.transport("POST", "/api/v1/parse/document", {
            body: form,
            idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
        });
    }
    parseStream(input) {
        const domain = input.domain ?? "portrait";
        const pipelineId = input.pipelineId ??
            (domain === "portrait" ? "portrait.person-detection" : "ocr.document");
        const pipeline = {
            pipeline_id: pipelineId,
            ...(input.pipelineVersion === undefined
                ? {}
                : { version: input.pipelineVersion }),
        };
        return this.transport("POST", "/api/v1/parse/stream", {
            idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
            body: {
                source_id: input.sourceId,
                domain,
                pipeline,
                parameters: {
                    sample_interval_ms: input.sampleIntervalMs ?? 1000,
                    sample_strategy: input.sampleStrategy ?? "interval",
                    sample_start_ms: input.sampleStartMs ?? 0,
                    ...(input.sampleEndMs === undefined
                        ? {}
                        : { sample_end_ms: input.sampleEndMs }),
                    scene_change_threshold: input.sceneChangeThreshold ?? 0.35,
                    ...(input.frameMaxEdge === undefined
                        ? {}
                        : { frame_max_edge: input.frameMaxEdge }),
                    max_reconnect_attempts: input.maxReconnectAttempts ?? 3,
                    connect_timeout_ms: input.connectTimeoutMs ?? 10000,
                    read_timeout_ms: input.readTimeoutMs ?? 10000,
                    ...(input.streamSegmentDurationMs === undefined
                        ? {}
                        : { stream_segment_duration_ms: input.streamSegmentDurationMs }),
                },
                priority: input.priority ?? 0,
                wait_ms: input.waitMs ?? 0,
            },
        });
    }
    deleteAsset(assetId) {
        return this.transport("DELETE", "/api/v1/media/assets/" + encodeURIComponent(assetId));
    }
    getAssetPreview(assetId) {
        return this.transport("GET", "/api/v1/media/assets/" + encodeURIComponent(assetId) + "/preview");
    }
    listSources(offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/media/sources?offset=" +
            String(offset) +
            "&limit=" +
            String(limit));
    }
    createSource(input) {
        return this.transport("POST", "/api/v1/media/sources", {
            body: {
                name: input.name,
                url: input.url,
                metadata: input.metadata ?? {},
            },
        });
    }
    getSource(sourceId) {
        return this.transport("GET", "/api/v1/media/sources/" + encodeURIComponent(sourceId));
    }
    probeSource(sourceId, timeoutMs = 10000) {
        return this.transport("POST", "/api/v1/media/sources/" +
            encodeURIComponent(sourceId) +
            "/probe?timeout_ms=" +
            String(timeoutMs));
    }
    deleteSource(sourceId) {
        return this.transport("DELETE", "/api/v1/media/sources/" + encodeURIComponent(sourceId));
    }
    listPipelines() {
        return this.transport("GET", "/api/v1/pipelines");
    }
    listDomains() {
        return this.transport("GET", "/api/v1/domains");
    }
    listProducts() {
        return this.transport("GET", "/api/v1/platform/products");
    }
    getRepositoryTopology() {
        return this.transport("GET", "/api/v1/platform/repositories");
    }
    getRepositoryContracts() {
        return this.transport("GET", "/api/v1/platform/contracts");
    }
    getAccessFoundation() {
        return this.transport("GET", "/api/v1/platform/access-foundation");
    }
    /**
     * Returns the Portrait Intelligence Foundation Platform contract: the six
     * strategic capability modules, three core assets, and per-capability
     * readiness state for the portrait domain.
     */
    getPortraitIntelligence() {
        return this.transport("GET", "/api/v1/platform/portrait-intelligence");
    }
    getIamSummary() {
        return this.transport("GET", "/api/v1/platform/iam/summary");
    }
    createOrganization(displayName) {
        return this.transport("POST", "/api/v1/platform/organizations", {
            body: { display_name: displayName },
        });
    }
    listOrganizations() {
        return this.transport("GET", "/api/v1/platform/organizations");
    }
    createProject(input) {
        return this.transport("POST", "/api/v1/platform/projects", {
            body: { display_name: input.displayName, project_id: input.projectId },
        });
    }
    listProjects() {
        return this.transport("GET", "/api/v1/platform/projects");
    }
    createUser(input) {
        return this.transport("POST", "/api/v1/platform/users", {
            body: {
                display_name: input.displayName,
                user_id: input.userId,
                email: input.email,
            },
        });
    }
    listUsers() {
        return this.transport("GET", "/api/v1/platform/users");
    }
    createRole(input) {
        return this.transport("POST", "/api/v1/platform/roles", {
            body: {
                display_name: input.displayName,
                role_id: input.roleId,
                scopes: input.scopes,
                product_ids: input.productIds ?? [],
            },
        });
    }
    listRoles() {
        return this.transport("GET", "/api/v1/platform/roles");
    }
    createMembership(input) {
        return this.transport("POST", "/api/v1/platform/memberships", {
            body: {
                principal_id: input.principalId,
                principal_type: input.principalType,
                role_ids: input.roleIds,
                project_id: input.projectId,
            },
        });
    }
    listMemberships() {
        return this.transport("GET", "/api/v1/platform/memberships");
    }
    createServiceAccount(input) {
        return this.transport("POST", "/api/v1/platform/service-accounts", {
            body: {
                display_name: input.displayName,
                service_account_id: input.serviceAccountId,
                scopes: input.scopes,
                product_ids: input.productIds ?? [],
            },
        });
    }
    listServiceAccounts() {
        return this.transport("GET", "/api/v1/platform/service-accounts");
    }
    createApiKey(input) {
        return this.transport("POST", "/api/v1/platform/service-accounts/" +
            encodeURIComponent(input.serviceAccountId) +
            "/api-keys", {
            body: {
                name: input.name,
                scopes: input.scopes,
                product_ids: input.productIds,
                expires_at: input.expiresAt,
            },
        });
    }
    listApiKeys() {
        return this.transport("GET", "/api/v1/platform/api-keys");
    }
    revokeApiKey(keyId) {
        return this.transport("POST", "/api/v1/platform/api-keys/" + encodeURIComponent(keyId) + "/revoke");
    }
    createProductEntitlement(input) {
        return this.transport("POST", "/api/v1/platform/product-entitlements", {
            body: {
                product_id: input.productId,
                status: input.status ?? "active",
                source: input.source ?? "manual",
                project_id: input.projectId,
            },
        });
    }
    listProductEntitlements() {
        return this.transport("GET", "/api/v1/platform/product-entitlements");
    }
    updateProductEntitlement(input) {
        return this.transport("PUT", "/api/v1/platform/product-entitlements/" +
            encodeURIComponent(input.productId), { body: { status: input.status, source: input.source ?? "manual" } });
    }
    listModels() {
        return this.transport("GET", "/api/v1/models");
    }
    createWebhookSubscription(input) {
        return this.transport("POST", "/api/v1/webhooks/subscriptions", {
            body: {
                name: input.name,
                url: input.url,
                secret: input.secret,
                event_types: input.eventTypes,
            },
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
}
//# sourceMappingURL=client_core.js.map