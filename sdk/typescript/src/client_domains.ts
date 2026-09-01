import type {
  AuditEventPage,
  DatasetRecord,
  DatasetVersion,
  FeedbackRecord,
  HardSampleManifest,
  ModelDeploymentEvent,
  ModelPackage,
  ModelRelease,
  PortraitCompareResponse,
  IndexDefinition,
  IndexHit,
  IndexRecordView,
  SearchResponse,
  SavedSearch,
  SavedSearchPage,
  ResultEnvelope,
  Run,
  UserAccount,
} from "./types.js";
import type { OpenApi } from "./generated.js";
import { ScenaraClientCore } from "./client_core.js";
import { ScenaraError } from "./client_types.js";
import type { ControlPlaneRecord } from "./client_types.js";

export class ScenaraClient extends ScenaraClientCore {
  createPortraitIdentity(
    displayName: string,
    metadata: Record<string, unknown> = {},
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/identities",
      {
        body: { display_name: displayName, metadata },
      },
    );
  }

  deletePortraitIdentity(identityId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/portrait/identities/" + encodeURIComponent(identityId),
    );
  }

  enrollPortraitIdentity(
    identityId: string,
    enrollment: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/identities/" +
        encodeURIComponent(identityId) +
        "/enrollments",
      { body: enrollment },
    );
  }

  searchPortrait(
    query: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/search",
      { body: query },
    );
  }

  comparePortrait(
    comparison: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/compare",
      {
        body: comparison,
      },
    );
  }

  getStreamSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "GET",
      "/api/v1/stream-sessions/" + encodeURIComponent(sessionId),
    );
  }

  cancelStreamSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/stream-sessions/" + encodeURIComponent(sessionId) + "/cancel",
    );
  }

  createIdentityProvider(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/identity-providers",
      input,
    );
  }

  listIdentityProviders(): Promise<ControlPlaneRecord[]> {
    return this.controlPlane<ControlPlaneRecord[]>(
      "GET",
      "/api/v1/platform/identity-providers",
    );
  }

  probeIdentityProvider(providerId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/identity-providers/" +
        encodeURIComponent(providerId) +
        "/probe",
    );
  }

  requestProjectLifecycle(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/projects/lifecycle-requests",
      input,
    );
  }

  decideProjectLifecycle(
    requestId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/platform/projects/lifecycle-requests/" +
        encodeURIComponent(requestId) +
        "/decide",
      input,
    );
  }

  setAuditRetention(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("PUT", "/api/v1/platform/audit/retention", input);
  }

  purgeAudit(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/audit/purge", input);
  }

  createSession(input: {
    userId: string;
    ttlSeconds?: number;
  }): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/sessions", {
      user_id: input.userId,
      ttl_seconds: input.ttlSeconds ?? 3600,
    });
  }

  setUserDisabled(userId: string, disabled: boolean): Promise<UserAccount> {
    const action = disabled ? "disable" : "restore";
    return this.transport<UserAccount>(
      "POST",
      "/api/v1/platform/users/" + encodeURIComponent(userId) + "/" + action,
    );
  }

  createQuotaPlan(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/quotas/plans", input);
  }

  checkQuota(metric: string, amount = 1): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/platform/quotas/check", {
      metric,
      amount,
    });
  }

  createAnnotationTask(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/data/annotation-tasks", input);
  }

  registerAnnotationProvider(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/data/annotation-providers",
      input,
    );
  }

  probeAnnotationProvider(providerId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/data/annotation-providers/" +
        encodeURIComponent(providerId) +
        "/probe",
    );
  }

  reviewAnnotationTask(
    taskId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/data/annotation-tasks/" + encodeURIComponent(taskId) + "/review",
      input,
    );
  }

  createFlow(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/flows", input);
  }

  executeFlow(
    flowId: string,
    input: ControlPlaneRecord = {},
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/flows/" + encodeURIComponent(flowId) + "/execute",
      input,
    );
  }

  decideFlowApproval(
    approvalId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/flows/approvals/" + encodeURIComponent(approvalId) + "/decide",
      input,
    );
  }

  createSearchRankingProfile(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/ranking-profiles", input);
  }

  evaluateSearch(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/evaluations", input);
  }

  rebuildIndex(indexId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/indexes/rebuild", {
      index_id: indexId,
    });
  }

  createIndex(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/indexes", input);
  }

  registerIndexBackend(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/index-backends", input);
  }

  probeIndexBackend(backendId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/search/index-backends/" +
        encodeURIComponent(backendId) +
        "/probe",
    );
  }

  registerSearchReranker(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/search/rerankers", input);
  }

  probeSearchReranker(rerankerId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/search/rerankers/" + encodeURIComponent(rerankerId) + "/probe",
    );
  }

  registerEdgeDevice(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/edge/devices", input);
  }

  heartbeatEdgeDevice(
    deviceId: string,
    input: ControlPlaneRecord = {},
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/edge/devices/" + encodeURIComponent(deviceId) + "/heartbeat",
      input,
    );
  }

  deployEdge(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/edge/deployments", input);
  }

  acknowledgeEdgeDeployment(
    deploymentId: string,
    input: ControlPlaneRecord = {},
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/edge/deployments/" +
        encodeURIComponent(deploymentId) +
        "/acknowledge",
      input,
    );
  }

  registerAgentTool(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/tools", input);
  }

  proposeAgentAction(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/actions", input);
  }

  decideAgentAction(
    actionId: string,
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/agents/actions/" + encodeURIComponent(actionId) + "/decide",
      input,
    );
  }

  executeAgentAction(actionId: string): Promise<ControlPlaneRecord> {
    return this.controlPlane(
      "POST",
      "/api/v1/agents/actions/" + encodeURIComponent(actionId) + "/execute",
    );
  }

  recordAgentTrace(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/traces", input);
  }

  recordAgentEvaluation(
    input: ControlPlaneRecord,
  ): Promise<ControlPlaneRecord> {
    return this.controlPlane("POST", "/api/v1/agents/evaluations", input);
  }

  putAgentMemory(input: ControlPlaneRecord): Promise<ControlPlaneRecord> {
    return this.controlPlane("PUT", "/api/v1/agents/memory", input);
  }

  getAgentMemory(
    namespace: string,
    key: string,
  ): Promise<ControlPlaneRecord | null> {
    return this.controlPlane<ControlPlaneRecord | null>(
      "GET",
      "/api/v1/agents/memory?namespace=" +
        encodeURIComponent(namespace) +
        "&key=" +
        encodeURIComponent(key),
    );
  }

  getDeploymentTopology(): Promise<ControlPlaneRecord> {
    return this.controlPlane("GET", "/api/v1/platform/deployment/topology");
  }

  listDatasets(
    offset = 0,
    limit = 50,
  ): Promise<{
    items: DatasetRecord[];
    offset: number;
    limit: number;
    total: number;
  }> {
    return this.transport<{
      items: DatasetRecord[];
      offset: number;
      limit: number;
      total: number;
    }>(
      "GET",
      "/api/v1/datasets?offset=" + String(offset) + "&limit=" + String(limit),
    );
  }

  createDataset(input: {
    name: string;
    description?: string;
    metadata?: Record<string, unknown>;
  }): Promise<DatasetRecord> {
    return this.transport<DatasetRecord>("POST", "/api/v1/datasets", {
      body: {
        name: input.name,
        description: input.description ?? "",
        metadata: input.metadata ?? {},
      },
    });
  }

  getDataset(datasetId: string): Promise<DatasetRecord> {
    return this.transport<DatasetRecord>(
      "GET",
      "/api/v1/datasets/" + encodeURIComponent(datasetId),
    );
  }

  updateDataset(
    datasetId: string,
    input: Partial<
      Pick<DatasetRecord, "name" | "description" | "status" | "metadata">
    >,
  ): Promise<DatasetRecord> {
    return this.transport<DatasetRecord>(
      "PATCH",
      "/api/v1/datasets/" + encodeURIComponent(datasetId),
      { body: input },
    );
  }

  createDatasetVersion(
    datasetId: string,
    input: {
      version: string;
      manifestSha256: string;
      assetIds?: string[];
      qualityScore?: number | null;
      lineage?: Record<string, unknown>;
      annotationSummary?: Record<string, unknown>;
    },
  ): Promise<DatasetVersion> {
    return this.transport<DatasetVersion>(
      "POST",
      "/api/v1/datasets/" + encodeURIComponent(datasetId) + "/versions",
      {
        body: {
          version: input.version,
          manifest_sha256: input.manifestSha256,
          asset_ids: input.assetIds ?? [],
          quality_score: input.qualityScore ?? null,
          lineage: input.lineage ?? {},
          annotation_summary: input.annotationSummary ?? {},
        },
      },
    );
  }

  listDatasetVersions(
    datasetId: string,
    offset = 0,
    limit = 50,
  ): Promise<{
    items: DatasetVersion[];
    offset: number;
    limit: number;
    total: number;
  }> {
    return this.transport<{
      items: DatasetVersion[];
      offset: number;
      limit: number;
      total: number;
    }>(
      "GET",
      "/api/v1/datasets/" +
        encodeURIComponent(datasetId) +
        "/versions?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  transitionDatasetVersion(
    versionId: string,
    status: "validated" | "published" | "retired",
  ): Promise<DatasetVersion> {
    return this.transport<DatasetVersion>(
      "POST",
      "/api/v1/dataset-versions/" +
        encodeURIComponent(versionId) +
        "/transition",
      { body: { status } },
    );
  }

  listAuditEvents(
    filters: {
      action?: string;
      resourceType?: string;
      principalId?: string;
      outcome?: string;
      offset?: number;
      limit?: number;
    } = {},
  ): Promise<AuditEventPage> {
    const query = new URLSearchParams();
    if (filters.action) query.set("action", filters.action);
    if (filters.resourceType) query.set("resource_type", filters.resourceType);
    if (filters.principalId) query.set("principal_id", filters.principalId);
    if (filters.outcome) query.set("outcome", filters.outcome);
    query.set("offset", String(filters.offset ?? 0));
    query.set("limit", String(filters.limit ?? 50));
    return this.transport<AuditEventPage>(
      "GET",
      "/api/v1/audit/events?" + query.toString(),
    );
  }

  enrollPortraitIdentityImage(
    identityId: string,
    file: Blob,
    filename = "portrait-image",
    options: { featureSpaceId?: string; quality?: number } = {},
  ): Promise<Record<string, unknown>> {
    const form = new FormData();
    form.append("file", file, filename);
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.quality !== undefined)
      form.append("quality", String(options.quality));
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/identities/" +
        encodeURIComponent(identityId) +
        "/enrollments/image",
      { body: form },
    );
  }

  searchPortraitImage(
    file: Blob,
    filename = "portrait-query",
    options: {
      featureSpaceId?: string;
      limit?: number;
      threshold?: number;
    } = {},
  ): Promise<Record<string, unknown>> {
    const form = new FormData();
    form.append("file", file, filename);
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.limit !== undefined)
      form.append("limit", String(options.limit));
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<Record<string, unknown>>(
      "POST",
      "/api/v1/portrait/search/image",
      { body: form },
    );
  }

  comparePortraitImages(
    left: Blob,
    right: Blob,
    options: {
      leftFilename?: string;
      rightFilename?: string;
      featureSpaceId?: string;
      threshold?: number;
    } = {},
  ): Promise<PortraitCompareResponse> {
    const form = new FormData();
    form.append("left", left, options.leftFilename ?? "portrait-left");
    form.append("right", right, options.rightFilename ?? "portrait-right");
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/images",
      { body: form },
    );
  }

  comparePortraitAssets(input: {
    leftAssetId: string;
    rightAssetId: string;
    featureSpaceId?: string;
    threshold?: number;
  }): Promise<PortraitCompareResponse> {
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/assets",
      {
        body: {
          left_asset_id: input.leftAssetId,
          right_asset_id: input.rightAssetId,
          feature_space_id: input.featureSpaceId,
          threshold: input.threshold,
        },
      },
    );
  }

  comparePortraitAssetImage(
    assetId: string,
    image: Blob,
    options: {
      filename?: string;
      featureSpaceId?: string;
      threshold?: number;
    } = {},
  ): Promise<PortraitCompareResponse> {
    const form = new FormData();
    form.append("asset_id", assetId);
    form.append("file", image, options.filename ?? "portrait-image");
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/asset-image",
      { body: form },
    );
  }

  comparePortraitImageAsset(
    image: Blob,
    assetId: string,
    options: {
      filename?: string;
      featureSpaceId?: string;
      threshold?: number;
    } = {},
  ): Promise<PortraitCompareResponse> {
    const form = new FormData();
    form.append("file", image, options.filename ?? "portrait-image");
    form.append("asset_id", assetId);
    if (options.featureSpaceId)
      form.append("feature_space_id", options.featureSpaceId);
    if (options.threshold !== undefined)
      form.append("threshold", String(options.threshold));
    return this.transport<PortraitCompareResponse>(
      "POST",
      "/api/v1/portrait/compare/image-asset",
      { body: form },
    );
  }

  listSearchIndexes(domain?: string): Promise<IndexDefinition[]> {
    const query = domain ? `?domain=${encodeURIComponent(domain)}` : "";
    return this.transport<IndexDefinition[]>("GET", "/api/v1/indexes" + query);
  }

  listSearchIndexRecords(
    indexId: string,
    filters: {
      sourceType?: string;
      sourceId?: string;
      offset?: number;
      limit?: number;
    } = {},
  ): Promise<IndexRecordView[]> {
    const query = new URLSearchParams();
    if (filters.sourceType) query.set("source_type", filters.sourceType);
    if (filters.sourceId) query.set("source_id", filters.sourceId);
    if (filters.offset !== undefined)
      query.set("offset", String(filters.offset));
    if (filters.limit !== undefined) query.set("limit", String(filters.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return this.transport<IndexRecordView[]>(
      "GET",
      "/api/v1/indexes/" + encodeURIComponent(indexId) + "/records" + suffix,
    );
  }

  querySearchIndexText(
    indexId: string,
    query: string,
    limit = 20,
  ): Promise<Record<string, unknown>[]> {
    return this.transport<Record<string, unknown>[]>(
      "POST",
      "/api/v1/indexes/" + encodeURIComponent(indexId) + "/query/text",
      { body: { query, limit } },
    );
  }

  querySearchIndexVector(
    indexId: string,
    vector: number[],
    options: { limit?: number; threshold?: number } = {},
  ): Promise<IndexHit[]> {
    return this.transport<IndexHit[]>(
      "POST",
      "/api/v1/indexes/" + encodeURIComponent(indexId) + "/query/vector",
      {
        body: {
          vector,
          limit: options.limit ?? 20,
          threshold: options.threshold,
        },
      },
    );
  }

  searchText(input: {
    query: string;
    domains?: string[];
    mediaKinds?: string[];
    limit?: number;
  }): Promise<SearchResponse> {
    return this.transport<SearchResponse>("POST", "/api/v1/search/text", {
      body: {
        query: input.query,
        domains: input.domains ?? [],
        media_kinds: input.mediaKinds ?? [],
        limit: input.limit ?? 50,
      },
    });
  }

  searchPortraitResults(input: {
    file: Blob;
    filename?: string;
    featureSpaceId?: string;
    mediaKinds?: string[];
    limit?: number;
    threshold?: number;
  }): Promise<SearchResponse> {
    const form = new FormData();
    form.append("file", input.file, input.filename ?? "query-image");
    if (input.featureSpaceId)
      form.append("feature_space_id", input.featureSpaceId);
    if (input.mediaKinds?.length)
      form.append("media_kinds", input.mediaKinds.join(","));
    if (input.limit !== undefined) form.append("limit", String(input.limit));
    if (input.threshold !== undefined)
      form.append("threshold", String(input.threshold));
    return this.transport<SearchResponse>("POST", "/api/v1/search/image", {
      body: form,
    });
  }

  searchPortraitAsset(input: {
    assetId: string;
    featureSpaceId?: string;
    mediaKinds?: string[];
    limit?: number;
    threshold?: number;
  }): Promise<SearchResponse> {
    return this.transport<SearchResponse>("POST", "/api/v1/search/asset", {
      body: {
        asset_id: input.assetId,
        feature_space_id: input.featureSpaceId,
        media_kinds: input.mediaKinds ?? [],
        limit: input.limit ?? 50,
        threshold: input.threshold,
      },
    });
  }

  createSavedSearch(input: {
    name: string;
    mode: "text" | "portrait";
    definition: Record<string, unknown>;
    description?: string;
  }): Promise<SavedSearch> {
    return this.transport<SavedSearch>("POST", "/api/v1/search/saved", {
      body: {
        name: input.name,
        description: input.description ?? "",
        mode: input.mode,
        definition: input.definition,
      },
    });
  }

  listSavedSearches(offset = 0, limit = 50): Promise<SavedSearchPage> {
    return this.transport<SavedSearchPage>(
      "GET",
      "/api/v1/search/saved?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  getSavedSearch(savedSearchId: string): Promise<SavedSearch> {
    return this.transport<SavedSearch>(
      "GET",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId),
    );
  }

  updateSavedSearch(
    savedSearchId: string,
    input: {
      name?: string;
      description?: string;
      definition?: Record<string, unknown>;
    },
  ): Promise<SavedSearch> {
    return this.transport<SavedSearch>(
      "PATCH",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId),
      {
        body: input,
      },
    );
  }

  runSavedSearch(savedSearchId: string): Promise<SearchResponse> {
    return this.transport<SearchResponse>(
      "POST",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId) + "/run",
    );
  }

  deleteSavedSearch(savedSearchId: string): Promise<void> {
    return this.transport<void>(
      "DELETE",
      "/api/v1/search/saved/" + encodeURIComponent(savedSearchId),
    );
  }

  createWatchlist(input: {
    name: string;
    category?: "blacklist" | "whitelist" | "custom";
    description?: string;
  }): Promise<OpenApi.Watchlist> {
    return this.transport<OpenApi.Watchlist>(
      "POST",
      "/api/v1/surveillance/watchlists",
      { body: input },
    );
  }

  listWatchlists(offset = 0, limit = 50): Promise<OpenApi.WatchlistPage> {
    return this.transport<OpenApi.WatchlistPage>(
      "GET",
      "/api/v1/surveillance/watchlists?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  addWatchlistMember(
    watchlistId: string,
    input: {
      portraitIdentityId: string;
      displayLabel?: string;
      validFrom?: number;
      validUntil?: number;
    },
  ): Promise<OpenApi.WatchlistMember> {
    return this.transport<OpenApi.WatchlistMember>(
      "POST",
      "/api/v1/surveillance/watchlists/" +
        encodeURIComponent(watchlistId) +
        "/members",
      {
        body: {
          portrait_identity_id: input.portraitIdentityId,
          display_label: input.displayLabel ?? "",
          valid_from: input.validFrom,
          valid_until: input.validUntil,
        },
      },
    );
  }

  createSurveillanceTask(
    input: OpenApi.CreateSurveillanceTaskRequest,
  ): Promise<OpenApi.SurveillanceTask> {
    return this.transport<OpenApi.SurveillanceTask>(
      "POST",
      "/api/v1/surveillance/tasks",
      { body: input },
    );
  }

  listSurveillanceTasks(
    offset = 0,
    limit = 50,
  ): Promise<OpenApi.SurveillanceTaskPage> {
    return this.transport<OpenApi.SurveillanceTaskPage>(
      "GET",
      "/api/v1/surveillance/tasks?offset=" +
        String(offset) +
        "&limit=" +
        String(limit),
    );
  }

  startSurveillanceTask(taskId: string): Promise<OpenApi.SurveillanceTask> {
    return this.transport<OpenApi.SurveillanceTask>(
      "POST",
      "/api/v1/surveillance/tasks/" + encodeURIComponent(taskId) + "/start",
    );
  }

  pauseSurveillanceTask(taskId: string): Promise<OpenApi.SurveillanceTask> {
    return this.transport<OpenApi.SurveillanceTask>(
      "POST",
      "/api/v1/surveillance/tasks/" + encodeURIComponent(taskId) + "/pause",
    );
  }

  listSurveillanceAlerts(
    input: {
      status?: OpenApi.AlertStatus;
      taskId?: string;
      cameraId?: string;
      offset?: number;
      limit?: number;
    } = {},
  ): Promise<OpenApi.AlertPage> {
    const query = new URLSearchParams();
    if (input.status) query.set("status", input.status);
    if (input.taskId) query.set("task_id", input.taskId);
    if (input.cameraId) query.set("camera_id", input.cameraId);
    query.set("offset", String(input.offset ?? 0));
    query.set("limit", String(input.limit ?? 50));
    return this.transport<OpenApi.AlertPage>(
      "GET",
      "/api/v1/surveillance/alerts?" + query.toString(),
    );
  }

  triageSurveillanceAlert(
    alertId: string,
    input: {
      expectedRevision: number;
      status: "confirmed" | "false_positive" | "ignored";
      reason: string;
      notes?: string;
    },
  ): Promise<OpenApi.AlertRecord> {
    return this.transport<OpenApi.AlertRecord>(
      "PATCH",
      "/api/v1/surveillance/alerts/" + encodeURIComponent(alertId) + "/status",
      {
        body: {
          expected_revision: input.expectedRevision,
          status: input.status,
          reason: input.reason,
          notes: input.notes ?? "",
        },
      },
    );
  }

  createSurveillanceAlertFeedback(
    alertId: string,
    correction: Record<string, unknown> = {},
  ): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>(
      "POST",
      "/api/v1/surveillance/alerts/" +
        encodeURIComponent(alertId) +
        "/feedback",
      { body: { correction } },
    );
  }

  createFeedback(feedback: Record<string, unknown>): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>("POST", "/api/v1/feedback", {
      body: feedback,
    });
  }

  listFeedback(): Promise<FeedbackRecord[]> {
    return this.transport<FeedbackRecord[]>("GET", "/api/v1/feedback");
  }

  reviewFeedback(
    feedbackId: string,
    status: "approved" | "rejected",
    notes = "",
  ): Promise<FeedbackRecord> {
    return this.transport<FeedbackRecord>(
      "POST",
      "/api/v1/feedback/" + encodeURIComponent(feedbackId) + "/review",
      { body: { status, notes } },
    );
  }

  createHardSampleManifest(input: {
    datasetId: string;
    version: string;
    feedbackIds: string[];
    labelSchema?: string;
    split?: "train" | "validation" | "test";
  }): Promise<HardSampleManifest> {
    return this.transport<HardSampleManifest>(
      "POST",
      "/api/v1/hard-sample-manifests",
      {
        body: {
          dataset_id: input.datasetId,
          version: input.version,
          feedback_ids: input.feedbackIds,
          label_schema: input.labelSchema ?? "scenara.feedback.correction.v1",
          split: input.split ?? "train",
        },
      },
    );
  }

  createModelRelease(release: Record<string, unknown>): Promise<ModelRelease> {
    return this.transport<ModelRelease>("POST", "/api/v1/model-releases", {
      body: release,
    });
  }

  admitModelPackage(modelPackage: ModelPackage): Promise<ModelPackage> {
    return this.transport<ModelPackage>(
      "POST",
      "/api/v1/model-packages/admissions",
      { body: modelPackage },
    );
  }

  listModelReleases(): Promise<ModelRelease[]> {
    return this.transport<ModelRelease[]>("GET", "/api/v1/model-releases");
  }

  transitionModelRelease(
    modelId: string,
    version: string,
    status: "validated" | "approved" | "active" | "retired" | "candidate",
    reason: string,
  ): Promise<ModelRelease> {
    return this.transport<ModelRelease>(
      "POST",
      "/api/v1/model-releases/" +
        encodeURIComponent(modelId) +
        "/versions/" +
        encodeURIComponent(version) +
        "/transition",
      { body: { status, reason } },
    );
  }

  rollbackModelRelease(
    modelId: string,
    targetVersion: string,
    reason: string,
  ): Promise<ModelRelease> {
    return this.transport<ModelRelease>(
      "POST",
      "/api/v1/model-releases/" + encodeURIComponent(modelId) + "/rollback",
      { body: { target_version: targetVersion, reason } },
    );
  }

  listModelDeploymentEvents(limit = 100): Promise<ModelDeploymentEvent[]> {
    return this.transport<ModelDeploymentEvent[]>(
      "GET",
      "/api/v1/model-deployment-events?limit=" + String(limit),
    );
  }

  async waitResult(
    runId: string,
    options: { timeoutMs?: number; pollMs?: number } = {},
  ): Promise<ResultEnvelope> {
    const deadline = Date.now() + (options.timeoutMs ?? 300000);
    while (Date.now() < deadline) {
      const run = await this.getRun(runId);
      if (run.status === "completed") return await this.getResult(runId);
      if (["failed", "cancelled"].includes(run.status)) {
        throw new ScenaraError(
          run.error_code ?? "RUN_TERMINATED",
          run.termination_reason ?? run.status,
        );
      }
      await new Promise((resolve) =>
        setTimeout(resolve, options.pollMs ?? 500),
      );
    }
    throw new ScenaraError(
      "RUN_TIMEOUT",
      "Run did not complete before timeout",
    );
  }
}
