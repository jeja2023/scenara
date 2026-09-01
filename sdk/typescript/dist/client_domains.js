import { ScenaraClientCore } from "./client_core.js";
import { ScenaraError } from "./client_types.js";
export class ScenaraClient extends ScenaraClientCore {
    createPortraitIdentity(displayName, metadata = {}) {
        return this.transport("POST", "/api/v1/portrait/identities", {
            body: { display_name: displayName, metadata },
        });
    }
    deletePortraitIdentity(identityId) {
        return this.transport("DELETE", "/api/v1/portrait/identities/" + encodeURIComponent(identityId));
    }
    enrollPortraitIdentity(identityId, enrollment) {
        return this.transport("POST", "/api/v1/portrait/identities/" +
            encodeURIComponent(identityId) +
            "/enrollments", { body: enrollment });
    }
    searchPortrait(query) {
        return this.transport("POST", "/api/v1/portrait/search", { body: query });
    }
    comparePortrait(comparison) {
        return this.transport("POST", "/api/v1/portrait/compare", {
            body: comparison,
        });
    }
    getStreamSession(sessionId) {
        return this.transport("GET", "/api/v1/stream-sessions/" + encodeURIComponent(sessionId));
    }
    cancelStreamSession(sessionId) {
        return this.transport("POST", "/api/v1/stream-sessions/" + encodeURIComponent(sessionId) + "/cancel");
    }
    createIdentityProvider(input) {
        return this.controlPlane("POST", "/api/v1/platform/identity-providers", input);
    }
    listIdentityProviders() {
        return this.controlPlane("GET", "/api/v1/platform/identity-providers");
    }
    probeIdentityProvider(providerId) {
        return this.controlPlane("POST", "/api/v1/platform/identity-providers/" +
            encodeURIComponent(providerId) +
            "/probe");
    }
    requestProjectLifecycle(input) {
        return this.controlPlane("POST", "/api/v1/platform/projects/lifecycle-requests", input);
    }
    decideProjectLifecycle(requestId, input) {
        return this.controlPlane("POST", "/api/v1/platform/projects/lifecycle-requests/" +
            encodeURIComponent(requestId) +
            "/decide", input);
    }
    setAuditRetention(input) {
        return this.controlPlane("PUT", "/api/v1/platform/audit/retention", input);
    }
    purgeAudit(input) {
        return this.controlPlane("POST", "/api/v1/platform/audit/purge", input);
    }
    createSession(input) {
        return this.controlPlane("POST", "/api/v1/platform/sessions", {
            user_id: input.userId,
            ttl_seconds: input.ttlSeconds ?? 3600,
        });
    }
    setUserDisabled(userId, disabled) {
        const action = disabled ? "disable" : "restore";
        return this.transport("POST", "/api/v1/platform/users/" + encodeURIComponent(userId) + "/" + action);
    }
    createQuotaPlan(input) {
        return this.controlPlane("POST", "/api/v1/platform/quotas/plans", input);
    }
    checkQuota(metric, amount = 1) {
        return this.controlPlane("POST", "/api/v1/platform/quotas/check", {
            metric,
            amount,
        });
    }
    createAnnotationTask(input) {
        return this.controlPlane("POST", "/api/v1/data/annotation-tasks", input);
    }
    registerAnnotationProvider(input) {
        return this.controlPlane("POST", "/api/v1/data/annotation-providers", input);
    }
    probeAnnotationProvider(providerId) {
        return this.controlPlane("POST", "/api/v1/data/annotation-providers/" +
            encodeURIComponent(providerId) +
            "/probe");
    }
    reviewAnnotationTask(taskId, input) {
        return this.controlPlane("POST", "/api/v1/data/annotation-tasks/" + encodeURIComponent(taskId) + "/review", input);
    }
    createFlow(input) {
        return this.controlPlane("POST", "/api/v1/flows", input);
    }
    executeFlow(flowId, input = {}) {
        return this.controlPlane("POST", "/api/v1/flows/" + encodeURIComponent(flowId) + "/execute", input);
    }
    decideFlowApproval(approvalId, input) {
        return this.controlPlane("POST", "/api/v1/flows/approvals/" + encodeURIComponent(approvalId) + "/decide", input);
    }
    createSearchRankingProfile(input) {
        return this.controlPlane("POST", "/api/v1/search/ranking-profiles", input);
    }
    evaluateSearch(input) {
        return this.controlPlane("POST", "/api/v1/search/evaluations", input);
    }
    rebuildIndex(indexId) {
        return this.controlPlane("POST", "/api/v1/indexes/rebuild", {
            index_id: indexId,
        });
    }
    createIndex(input) {
        return this.controlPlane("POST", "/api/v1/indexes", input);
    }
    registerIndexBackend(input) {
        return this.controlPlane("POST", "/api/v1/search/index-backends", input);
    }
    probeIndexBackend(backendId) {
        return this.controlPlane("POST", "/api/v1/search/index-backends/" +
            encodeURIComponent(backendId) +
            "/probe");
    }
    registerSearchReranker(input) {
        return this.controlPlane("POST", "/api/v1/search/rerankers", input);
    }
    probeSearchReranker(rerankerId) {
        return this.controlPlane("POST", "/api/v1/search/rerankers/" + encodeURIComponent(rerankerId) + "/probe");
    }
    registerEdgeDevice(input) {
        return this.controlPlane("POST", "/api/v1/edge/devices", input);
    }
    heartbeatEdgeDevice(deviceId, input = {}) {
        return this.controlPlane("POST", "/api/v1/edge/devices/" + encodeURIComponent(deviceId) + "/heartbeat", input);
    }
    deployEdge(input) {
        return this.controlPlane("POST", "/api/v1/edge/deployments", input);
    }
    acknowledgeEdgeDeployment(deploymentId, input = {}) {
        return this.controlPlane("POST", "/api/v1/edge/deployments/" +
            encodeURIComponent(deploymentId) +
            "/acknowledge", input);
    }
    registerAgentTool(input) {
        return this.controlPlane("POST", "/api/v1/agents/tools", input);
    }
    proposeAgentAction(input) {
        return this.controlPlane("POST", "/api/v1/agents/actions", input);
    }
    decideAgentAction(actionId, input) {
        return this.controlPlane("POST", "/api/v1/agents/actions/" + encodeURIComponent(actionId) + "/decide", input);
    }
    executeAgentAction(actionId) {
        return this.controlPlane("POST", "/api/v1/agents/actions/" + encodeURIComponent(actionId) + "/execute");
    }
    recordAgentTrace(input) {
        return this.controlPlane("POST", "/api/v1/agents/traces", input);
    }
    recordAgentEvaluation(input) {
        return this.controlPlane("POST", "/api/v1/agents/evaluations", input);
    }
    putAgentMemory(input) {
        return this.controlPlane("PUT", "/api/v1/agents/memory", input);
    }
    getAgentMemory(namespace, key) {
        return this.controlPlane("GET", "/api/v1/agents/memory?namespace=" +
            encodeURIComponent(namespace) +
            "&key=" +
            encodeURIComponent(key));
    }
    getDeploymentTopology() {
        return this.controlPlane("GET", "/api/v1/platform/deployment/topology");
    }
    listDatasets(offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/datasets?offset=" + String(offset) + "&limit=" + String(limit));
    }
    createDataset(input) {
        return this.transport("POST", "/api/v1/datasets", {
            body: {
                name: input.name,
                description: input.description ?? "",
                metadata: input.metadata ?? {},
            },
        });
    }
    getDataset(datasetId) {
        return this.transport("GET", "/api/v1/datasets/" + encodeURIComponent(datasetId));
    }
    updateDataset(datasetId, input) {
        return this.transport("PATCH", "/api/v1/datasets/" + encodeURIComponent(datasetId), { body: input });
    }
    createDatasetVersion(datasetId, input) {
        return this.transport("POST", "/api/v1/datasets/" + encodeURIComponent(datasetId) + "/versions", {
            body: {
                version: input.version,
                manifest_sha256: input.manifestSha256,
                asset_ids: input.assetIds ?? [],
                quality_score: input.qualityScore ?? null,
                lineage: input.lineage ?? {},
                annotation_summary: input.annotationSummary ?? {},
            },
        });
    }
    listDatasetVersions(datasetId, offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/datasets/" +
            encodeURIComponent(datasetId) +
            "/versions?offset=" +
            String(offset) +
            "&limit=" +
            String(limit));
    }
    transitionDatasetVersion(versionId, status) {
        return this.transport("POST", "/api/v1/dataset-versions/" +
            encodeURIComponent(versionId) +
            "/transition", { body: { status } });
    }
    listAuditEvents(filters = {}) {
        const query = new URLSearchParams();
        if (filters.action)
            query.set("action", filters.action);
        if (filters.resourceType)
            query.set("resource_type", filters.resourceType);
        if (filters.principalId)
            query.set("principal_id", filters.principalId);
        if (filters.outcome)
            query.set("outcome", filters.outcome);
        query.set("offset", String(filters.offset ?? 0));
        query.set("limit", String(filters.limit ?? 50));
        return this.transport("GET", "/api/v1/audit/events?" + query.toString());
    }
    enrollPortraitIdentityImage(identityId, file, filename = "portrait-image", options = {}) {
        const form = new FormData();
        form.append("file", file, filename);
        if (options.featureSpaceId)
            form.append("feature_space_id", options.featureSpaceId);
        if (options.quality !== undefined)
            form.append("quality", String(options.quality));
        return this.transport("POST", "/api/v1/portrait/identities/" +
            encodeURIComponent(identityId) +
            "/enrollments/image", { body: form });
    }
    searchPortraitImage(file, filename = "portrait-query", options = {}) {
        const form = new FormData();
        form.append("file", file, filename);
        if (options.featureSpaceId)
            form.append("feature_space_id", options.featureSpaceId);
        if (options.limit !== undefined)
            form.append("limit", String(options.limit));
        if (options.threshold !== undefined)
            form.append("threshold", String(options.threshold));
        return this.transport("POST", "/api/v1/portrait/search/image", { body: form });
    }
    comparePortraitImages(left, right, options = {}) {
        const form = new FormData();
        form.append("left", left, options.leftFilename ?? "portrait-left");
        form.append("right", right, options.rightFilename ?? "portrait-right");
        if (options.featureSpaceId)
            form.append("feature_space_id", options.featureSpaceId);
        if (options.threshold !== undefined)
            form.append("threshold", String(options.threshold));
        return this.transport("POST", "/api/v1/portrait/compare/images", { body: form });
    }
    comparePortraitAssets(input) {
        return this.transport("POST", "/api/v1/portrait/compare/assets", {
            body: {
                left_asset_id: input.leftAssetId,
                right_asset_id: input.rightAssetId,
                feature_space_id: input.featureSpaceId,
                threshold: input.threshold,
            },
        });
    }
    comparePortraitAssetImage(assetId, image, options = {}) {
        const form = new FormData();
        form.append("asset_id", assetId);
        form.append("file", image, options.filename ?? "portrait-image");
        if (options.featureSpaceId)
            form.append("feature_space_id", options.featureSpaceId);
        if (options.threshold !== undefined)
            form.append("threshold", String(options.threshold));
        return this.transport("POST", "/api/v1/portrait/compare/asset-image", { body: form });
    }
    comparePortraitImageAsset(image, assetId, options = {}) {
        const form = new FormData();
        form.append("file", image, options.filename ?? "portrait-image");
        form.append("asset_id", assetId);
        if (options.featureSpaceId)
            form.append("feature_space_id", options.featureSpaceId);
        if (options.threshold !== undefined)
            form.append("threshold", String(options.threshold));
        return this.transport("POST", "/api/v1/portrait/compare/image-asset", { body: form });
    }
    listSearchIndexes(domain) {
        const query = domain ? `?domain=${encodeURIComponent(domain)}` : "";
        return this.transport("GET", "/api/v1/indexes" + query);
    }
    listSearchIndexRecords(indexId, filters = {}) {
        const query = new URLSearchParams();
        if (filters.sourceType)
            query.set("source_type", filters.sourceType);
        if (filters.sourceId)
            query.set("source_id", filters.sourceId);
        if (filters.offset !== undefined)
            query.set("offset", String(filters.offset));
        if (filters.limit !== undefined)
            query.set("limit", String(filters.limit));
        const suffix = query.toString() ? `?${query.toString()}` : "";
        return this.transport("GET", "/api/v1/indexes/" + encodeURIComponent(indexId) + "/records" + suffix);
    }
    querySearchIndexText(indexId, query, limit = 20) {
        return this.transport("POST", "/api/v1/indexes/" + encodeURIComponent(indexId) + "/query/text", { body: { query, limit } });
    }
    querySearchIndexVector(indexId, vector, options = {}) {
        return this.transport("POST", "/api/v1/indexes/" + encodeURIComponent(indexId) + "/query/vector", {
            body: {
                vector,
                limit: options.limit ?? 20,
                threshold: options.threshold,
            },
        });
    }
    searchText(input) {
        return this.transport("POST", "/api/v1/search/text", {
            body: {
                query: input.query,
                domains: input.domains ?? [],
                media_kinds: input.mediaKinds ?? [],
                limit: input.limit ?? 50,
            },
        });
    }
    searchPortraitResults(input) {
        const form = new FormData();
        form.append("file", input.file, input.filename ?? "query-image");
        if (input.featureSpaceId)
            form.append("feature_space_id", input.featureSpaceId);
        if (input.mediaKinds?.length)
            form.append("media_kinds", input.mediaKinds.join(","));
        if (input.limit !== undefined)
            form.append("limit", String(input.limit));
        if (input.threshold !== undefined)
            form.append("threshold", String(input.threshold));
        return this.transport("POST", "/api/v1/search/image", {
            body: form,
        });
    }
    searchPortraitAsset(input) {
        return this.transport("POST", "/api/v1/search/asset", {
            body: {
                asset_id: input.assetId,
                feature_space_id: input.featureSpaceId,
                media_kinds: input.mediaKinds ?? [],
                limit: input.limit ?? 50,
                threshold: input.threshold,
            },
        });
    }
    createSavedSearch(input) {
        return this.transport("POST", "/api/v1/search/saved", {
            body: {
                name: input.name,
                description: input.description ?? "",
                mode: input.mode,
                definition: input.definition,
            },
        });
    }
    listSavedSearches(offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/search/saved?offset=" +
            String(offset) +
            "&limit=" +
            String(limit));
    }
    getSavedSearch(savedSearchId) {
        return this.transport("GET", "/api/v1/search/saved/" + encodeURIComponent(savedSearchId));
    }
    updateSavedSearch(savedSearchId, input) {
        return this.transport("PATCH", "/api/v1/search/saved/" + encodeURIComponent(savedSearchId), {
            body: input,
        });
    }
    runSavedSearch(savedSearchId) {
        return this.transport("POST", "/api/v1/search/saved/" + encodeURIComponent(savedSearchId) + "/run");
    }
    deleteSavedSearch(savedSearchId) {
        return this.transport("DELETE", "/api/v1/search/saved/" + encodeURIComponent(savedSearchId));
    }
    createWatchlist(input) {
        return this.transport("POST", "/api/v1/surveillance/watchlists", { body: input });
    }
    listWatchlists(offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/surveillance/watchlists?offset=" +
            String(offset) +
            "&limit=" +
            String(limit));
    }
    addWatchlistMember(watchlistId, input) {
        return this.transport("POST", "/api/v1/surveillance/watchlists/" +
            encodeURIComponent(watchlistId) +
            "/members", {
            body: {
                portrait_identity_id: input.portraitIdentityId,
                display_label: input.displayLabel ?? "",
                valid_from: input.validFrom,
                valid_until: input.validUntil,
            },
        });
    }
    createSurveillanceTask(input) {
        return this.transport("POST", "/api/v1/surveillance/tasks", { body: input });
    }
    listSurveillanceTasks(offset = 0, limit = 50) {
        return this.transport("GET", "/api/v1/surveillance/tasks?offset=" +
            String(offset) +
            "&limit=" +
            String(limit));
    }
    startSurveillanceTask(taskId) {
        return this.transport("POST", "/api/v1/surveillance/tasks/" + encodeURIComponent(taskId) + "/start");
    }
    pauseSurveillanceTask(taskId) {
        return this.transport("POST", "/api/v1/surveillance/tasks/" + encodeURIComponent(taskId) + "/pause");
    }
    listSurveillanceAlerts(input = {}) {
        const query = new URLSearchParams();
        if (input.status)
            query.set("status", input.status);
        if (input.taskId)
            query.set("task_id", input.taskId);
        if (input.cameraId)
            query.set("camera_id", input.cameraId);
        query.set("offset", String(input.offset ?? 0));
        query.set("limit", String(input.limit ?? 50));
        return this.transport("GET", "/api/v1/surveillance/alerts?" + query.toString());
    }
    triageSurveillanceAlert(alertId, input) {
        return this.transport("PATCH", "/api/v1/surveillance/alerts/" + encodeURIComponent(alertId) + "/status", {
            body: {
                expected_revision: input.expectedRevision,
                status: input.status,
                reason: input.reason,
                notes: input.notes ?? "",
            },
        });
    }
    createSurveillanceAlertFeedback(alertId, correction = {}) {
        return this.transport("POST", "/api/v1/surveillance/alerts/" +
            encodeURIComponent(alertId) +
            "/feedback", { body: { correction } });
    }
    createFeedback(feedback) {
        return this.transport("POST", "/api/v1/feedback", {
            body: feedback,
        });
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
        return this.transport("POST", "/api/v1/model-releases", {
            body: release,
        });
    }
    admitModelPackage(modelPackage) {
        return this.transport("POST", "/api/v1/model-packages/admissions", { body: modelPackage });
    }
    listModelReleases() {
        return this.transport("GET", "/api/v1/model-releases");
    }
    transitionModelRelease(modelId, version, status, reason) {
        return this.transport("POST", "/api/v1/model-releases/" +
            encodeURIComponent(modelId) +
            "/versions/" +
            encodeURIComponent(version) +
            "/transition", { body: { status, reason } });
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
//# sourceMappingURL=client_domains.js.map