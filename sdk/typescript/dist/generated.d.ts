export declare const OPENAPI_SHA256 = "e36f906e5cf4e7ec62d8620d42a2179358860b003c938e4491ced35181804678" /** gitleaks:allow - public contract digest */;
export declare namespace OpenApi {
    type AccessCapabilityItem = {
        capability_id: string;
        current_scope?: Array<string>;
        name: string;
        next_gate: string;
        not_in_scope_yet?: Array<string>;
        status: AccessCapabilityStatus;
        summary: string;
    };
    type AccessCapabilityStatus = "available" | "seed" | "planned" | "gated";
    type AccessFoundationStatus = {
        auth_mode: "development_open" | "single_bearer_token";
        capabilities: Array<AccessCapabilityItem>;
        policy_provider: string;
        principal_id: string;
        principal_source: "anonymous" | "api_token" | "service_account_api_key" | "header";
        project_id: string;
        schema_version?: "1.0";
        tenant_id: string;
    };
    type AccessId = string;
    type AcknowledgeEdgeDeploymentRequest = {
        applied?: boolean;
        error?: (string) | (null);
    };
    type AcknowledgeEdgeSyncRequest = {
        acknowledged?: boolean;
    };
    type AgentAction = {
        created_at: number;
        created_by: string;
        error?: (string) | (null);
        input?: {
            [key: string]: unknown;
        };
        output?: {
            [key: string]: unknown;
        };
        project_id: string;
        record_id: string;
        status?: AgentActionStatus;
        tenant_id: string;
        tool_id: string;
        updated_at: number;
    };
    type AgentActionStatus = "proposed" | "pending_approval" | "approved" | "rejected" | "executed" | "failed";
    type AgentEvaluation = {
        created_at: number;
        created_by: string;
        policy_violation_count?: number;
        project_id: string;
        record_id: string;
        sample_count: number;
        success_rate: number;
        suite_name: string;
        tenant_id: string;
    };
    type AgentMemoryEntry = {
        expires_at?: (number) | (null);
        key: string;
        namespace: string;
        project_id: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
        updated_by: string;
        value?: {
            [key: string]: unknown;
        };
    };
    type AgentTool = {
        created_at: number;
        description: string;
        enabled?: boolean;
        name: string;
        project_id: string;
        record_id: string;
        requires_approval?: boolean;
        scopes?: Array<string>;
        tenant_id: string;
    };
    type AgentTrace = {
        action_id?: (string) | (null);
        created_at: number;
        created_by: string;
        payload?: {
            [key: string]: unknown;
        };
        project_id: string;
        record_id: string;
        tenant_id: string;
        trace_type: string;
    };
    type AnnotationProvider = {
        created_at: number;
        enabled?: boolean;
        endpoint: string;
        kind: string;
        last_health?: string;
        name: string;
        project_id: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
    };
    type AnnotationTask = {
        asset_ids: Array<string>;
        assignee?: (string) | (null);
        consistency_score?: (number) | (null);
        created_at: number;
        created_by: string;
        labels?: {
            [key: string]: unknown;
        };
        project_id: string;
        record_id: string;
        review_comment?: string;
        schema_name: string;
        status?: AnnotationTaskStatus;
        tenant_id: string;
        updated_at: number;
    };
    type AnnotationTaskStatus = "queued" | "in_review" | "approved" | "rejected";
    type ApiEnvelope_AccessFoundationStatus_ = {
        data: AccessFoundationStatus;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AgentAction_ = {
        data: AgentAction;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AgentEvaluation_ = {
        data: AgentEvaluation;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AgentMemoryEntry_ = {
        data: AgentMemoryEntry;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AgentTool_ = {
        data: AgentTool;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AgentTrace_ = {
        data: AgentTrace;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AnnotationProvider_ = {
        data: AnnotationProvider;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AnnotationTask_ = {
        data: AnnotationTask;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ApiKeyRecord_ = {
        data: ApiKeyRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AuditEventPage_ = {
        data: AuditEventPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_AuditRetentionPolicy_ = {
        data: AuditRetentionPolicy;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_CameraRecord_ = {
        data: CameraRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_CreateApiKeyResponse_ = {
        data: CreateApiKeyResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_DatasetPage_ = {
        data: DatasetPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_DatasetRecord_ = {
        data: DatasetRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_DatasetVersionPage_ = {
        data: DatasetVersionPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_DatasetVersion_ = {
        data: DatasetVersion;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_DeploymentTopology_ = {
        data: DeploymentTopology;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_EdgeDeployment_ = {
        data: EdgeDeployment;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_EdgeDevice_ = {
        data: EdgeDevice;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_EdgeSyncItem_ = {
        data: EdgeSyncItem;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_FeedbackRecord_ = {
        data: FeedbackRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_FlowApproval_ = {
        data: FlowApproval;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_FlowDefinition_ = {
        data: FlowDefinition;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_FlowExecution_ = {
        data: FlowExecution;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_HardSampleManifest_ = {
        data: HardSampleManifest;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_IamSummary_ = {
        data: IamSummary;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_IdentityPage_ = {
        data: IdentityPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_IdentityProvider_ = {
        data: IdentityProvider;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_IndexBackend_ = {
        data: IndexBackend;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_IndexDefinition_ = {
        data: IndexDefinition;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_IndexRebuildJob_ = {
        data: IndexRebuildJob;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_LongTermIdentity_ = {
        data: LongTermIdentity;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_MediaAssetPage_ = {
        data: MediaAssetPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_MediaAsset_ = {
        data: MediaAsset;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_MediaSourcePage_ = {
        data: MediaSourcePage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_MediaSourceProbe_ = {
        data: MediaSourceProbe;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_MediaSourceView_ = {
        data: MediaSourceView;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_Membership_ = {
        data: Membership;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ModelHealthSnapshot_ = {
        data: ModelHealthSnapshot;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ModelMetricPoint_ = {
        data: ModelMetricPoint;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ModelPackageManifest_ = {
        data: ModelPackageManifest;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ModelRelease_ = {
        data: ModelRelease;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_Organization_ = {
        data: Organization;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ParseDocumentResponse_ = {
        data: ParseDocumentResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ParseImageResponse_ = {
        data: ParseImageResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ParseVideoResponse_ = {
        data: ParseVideoResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitAssociation_ = {
        data: PortraitAssociation;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitCluster_ = {
        data: PortraitCluster;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitCompareResponse_ = {
        data: PortraitCompareResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitEnrollment_ = {
        data: PortraitEnrollment;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitEvent_ = {
        data: PortraitEvent;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitIdentityPage_ = {
        data: PortraitIdentityPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitIdentity_ = {
        data: PortraitIdentity;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitIntelligenceStatus_ = {
        data: PortraitIntelligenceStatus;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PortraitSearchResponse_ = {
        data: PortraitSearchResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PresignedMediaDownload_ = {
        data: PresignedMediaDownload;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PresignedMediaUpload_ = {
        data: PresignedMediaUpload;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ProductEntitlement_ = {
        data: ProductEntitlement;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ProjectLifecycleRequest_ = {
        data: ProjectLifecycleRequest;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_Project_ = {
        data: Project;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_PurgeAuditResponse_ = {
        data: PurgeAuditResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_QuotaCheckResponse_ = {
        data: QuotaCheckResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_QuotaPlan_ = {
        data: QuotaPlan;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_RepositoryContractCatalog_ = {
        data: RepositoryContractCatalog;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_RepositoryTopology_ = {
        data: RepositoryTopology;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ResourceLifecycleRecord_ = {
        data: ResourceLifecycleRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ResultPage_ = {
        data: ResultPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ResultSummaryPage_ = {
        data: ResultSummaryPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_Role_ = {
        data: Role;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_RunPage_ = {
        data: RunPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_RunRecord_ = {
        data: RunRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SavedSearchPage_ = {
        data: SavedSearchPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SavedSearch_ = {
        data: SavedSearch;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SearchEvaluation_ = {
        data: SearchEvaluation;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SearchRankingProfile_ = {
        data: SearchRankingProfile;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SearchRelevanceFeedback_ = {
        data: SearchRelevanceFeedback;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SearchReranker_ = {
        data: SearchReranker;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SearchResponse_ = {
        data: SearchResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SegmentPage_ = {
        data: SegmentPage;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ServiceAccount_ = {
        data: ServiceAccount;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SessionResponse_ = {
        data: SessionResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_StreamSessionView_ = {
        data: StreamSessionView;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SystemStatus_ = {
        data: SystemStatus;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_Union_AgentMemoryEntry__NoneType__ = {
        data: (AgentMemoryEntry) | (null);
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_UserAccount_ = {
        data: UserAccount;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_WebhookSubscriptionView_ = {
        data: WebhookSubscriptionView;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_WorkerLease_ = {
        data: WorkerLease;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_dict_str__object__ = {
        data: {
            [key: string]: unknown;
        };
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_dict_str__str__ = {
        data: {
            [key: string]: string;
        };
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_AgentEvaluation__ = {
        data: Array<AgentEvaluation>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_AgentTool__ = {
        data: Array<AgentTool>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_AgentTrace__ = {
        data: Array<AgentTrace>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_AnnotationProvider__ = {
        data: Array<AnnotationProvider>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_AnnotationTask__ = {
        data: Array<AnnotationTask>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ApiKeyRecord__ = {
        data: Array<ApiKeyRecord>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_CameraRecord__ = {
        data: Array<CameraRecord>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_CameraTransition__ = {
        data: Array<CameraTransition>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_EdgeDeployment__ = {
        data: Array<EdgeDeployment>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_EdgeDevice__ = {
        data: Array<EdgeDevice>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_FeedbackRecord__ = {
        data: Array<FeedbackRecord>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_FlowApproval__ = {
        data: Array<FlowApproval>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_FlowDefinition__ = {
        data: Array<FlowDefinition>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_HardSampleManifest__ = {
        data: Array<HardSampleManifest>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_IdentityProvider__ = {
        data: Array<IdentityProvider>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_IndexBackend__ = {
        data: Array<IndexBackend>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_IndexDefinition__ = {
        data: Array<IndexDefinition>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_IndexHit__ = {
        data: Array<IndexHit>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_IndexRecordView__ = {
        data: Array<IndexRecordView>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_Membership__ = {
        data: Array<Membership>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ModelDeploymentEvent__ = {
        data: Array<ModelDeploymentEvent>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ModelRelease__ = {
        data: Array<ModelRelease>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_Organization__ = {
        data: Array<Organization>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_PortraitAssociation__ = {
        data: Array<PortraitAssociation>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_PortraitCluster__ = {
        data: Array<PortraitCluster>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_PortraitEvent__ = {
        data: Array<PortraitEvent>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ProductCatalogItem__ = {
        data: Array<ProductCatalogItem>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ProductEntitlement__ = {
        data: Array<ProductEntitlement>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ProjectLifecycleRequest__ = {
        data: Array<ProjectLifecycleRequest>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_Project__ = {
        data: Array<Project>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_QuotaPlan__ = {
        data: Array<QuotaPlan>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_Role__ = {
        data: Array<Role>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_SearchRankingProfile__ = {
        data: Array<SearchRankingProfile>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_SearchReranker__ = {
        data: Array<SearchReranker>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ServiceAccount__ = {
        data: Array<ServiceAccount>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_TimelineEntry__ = {
        data: Array<TimelineEntry>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_UserAccount__ = {
        data: Array<UserAccount>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_WebhookDeliveryRecord__ = {
        data: Array<WebhookDeliveryRecord>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_WebhookSubscriptionView__ = {
        data: Array<WebhookSubscriptionView>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_WorkerLease__ = {
        data: Array<WorkerLease>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_dict_str__object___ = {
        data: Array<{
            [key: string]: unknown;
        }>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiKeyRecord = {
        created_at: number;
        expires_at?: (number) | (null);
        key_id: AccessId;
        last_used_at?: (number) | (null);
        name: string;
        product_ids?: Array<ProductId>;
        project_id: AccessId;
        revoked_at?: (number) | (null);
        scopes: Array<string>;
        service_account_id: AccessId;
        tenant_id: AccessId;
        token_prefix: string;
    };
    type ApproveAgentActionRequest = {
        approved: boolean;
        comment?: string;
    };
    type AuditEventPage = {
        items: Array<AuditEventView>;
        limit: number;
        offset: number;
        total: number;
    };
    type AuditEventView = {
        action: string;
        created_at: number;
        event_id: string;
        evidence?: {
            [key: string]: unknown;
        };
        outcome: string;
        principal_id: string;
        project_id: string;
        request_id?: (string) | (null);
        resource_id?: (string) | (null);
        resource_type: string;
        tenant_id: string;
    };
    type AuditRetentionPolicy = {
        created_at: number;
        enabled?: boolean;
        export_approval_required?: boolean;
        project_id: string;
        record_id: string;
        retention_days: number;
        tenant_id: string;
        updated_at: number;
        updated_by: string;
    };
    type Body_compare_portrait_asset_image_api_v1_portrait_compare_asset_image_post = {
        asset_id: string;
        feature_space_id?: (string) | (null);
        file: string;
        threshold?: (number) | (null);
    };
    type Body_compare_portrait_image_asset_api_v1_portrait_compare_image_asset_post = {
        asset_id: string;
        feature_space_id?: (string) | (null);
        file: string;
        threshold?: (number) | (null);
    };
    type Body_compare_portrait_images_api_v1_portrait_compare_images_post = {
        feature_space_id?: (string) | (null);
        left: string;
        right: string;
        threshold?: (number) | (null);
    };
    type Body_create_media_asset_api_v1_media_assets_post = {
        file: string;
        kind?: MediaKind;
    };
    type Body_enroll_portrait_identity_image_api_v1_portrait_identities__identity_id__enrollments_image_post = {
        feature_space_id?: (string) | (null);
        file: string;
        quality?: (number) | (null);
    };
    type Body_parse_document_api_v1_parse_document_post = {
        domain?: DomainId;
        file: string;
        page_scale?: number;
        pipeline_id?: (string) | (null);
        pipeline_version?: (string) | (null);
        wait_ms?: number;
    };
    type Body_parse_image_api_v1_parse_image_post = {
        domain?: DomainId;
        file: string;
        pipeline_id?: (string) | (null);
        pipeline_version?: (string) | (null);
    };
    type Body_parse_video_api_v1_parse_video_post = {
        camera_id?: (string) | (null);
        domain?: DomainId;
        file: string;
        frame_max_edge?: (number) | (null);
        page_scale?: number;
        pipeline_id?: (string) | (null);
        pipeline_version?: (string) | (null);
        recording_started_at?: (number) | (null);
        sample_end_ms?: (number) | (null);
        sample_interval_ms?: number;
        sample_start_ms?: number;
        sample_strategy?: SampleStrategy;
        scene_change_threshold?: number;
        wait_ms?: number;
    };
    type Body_search_portrait_identities_image_api_v1_portrait_search_image_post = {
        feature_space_id?: (string) | (null);
        file: string;
        limit?: number;
        threshold?: (number) | (null);
    };
    type Body_search_portrait_image_api_v1_search_image_post = {
        feature_space_id?: (string) | (null);
        file: string;
        limit?: number;
        media_kinds?: (string) | (null);
        profile_id?: (string) | (null);
        threshold?: (number) | (null);
    };
    type BoundingBox = {
        height: number;
        width: number;
        x: number;
        y: number;
    };
    type CameraRecord = {
        auto_registered?: boolean;
        camera_id: string;
        created_at?: number;
        display_name?: string;
        location?: string;
        metadata?: {
            [key: string]: unknown;
        };
        project_id: string;
        tenant_id: string;
        updated_at?: number;
    };
    type CameraTransition = {
        from_camera_id: string;
        max_seconds?: (number) | (null);
        min_seconds?: number;
        to_camera_id: string;
    };
    type CameraTransitionEntry = {
        max_seconds?: (number) | (null);
        min_seconds?: number;
        to_camera_id: string;
    };
    type CompleteMediaUploadRequest = {
        content_type: string;
        expires_at: number;
        filename?: (string) | (null);
        kind: MediaKind;
        sha256: string;
        size_bytes: number;
        upload_id: string;
        upload_token: string;
    };
    type CreateAgentEvaluationRequest = {
        policy_violation_count?: number;
        sample_count: number;
        success_rate: number;
        suite_name: string;
    };
    type CreateAgentTraceRequest = {
        action_id?: (string) | (null);
        payload?: {
            [key: string]: unknown;
        };
        trace_type: string;
    };
    type CreateAnnotationProviderRequest = {
        endpoint: string;
        kind: string;
        name: string;
    };
    type CreateAnnotationTaskRequest = {
        asset_ids: Array<string>;
        assignee?: (string) | (null);
        labels?: {
            [key: string]: unknown;
        };
        schema_name: string;
    };
    type CreateApiKeyRequest = {
        expires_at?: (number) | (null);
        name: string;
        product_ids?: (Array<ProductId>) | (null);
        scopes?: (Array<string>) | (null);
    };
    type CreateApiKeyResponse = {
        api_key: string;
        record: ApiKeyRecord;
    };
    type CreateDatasetRequest = {
        description?: string;
        metadata?: {
            [key: string]: unknown;
        };
        name: string;
    };
    type CreateDatasetVersionRequest = {
        annotation_summary?: {
            [key: string]: unknown;
        };
        asset_ids?: Array<string>;
        lineage?: {
            [key: string]: unknown;
        };
        manifest_sha256: string;
        quality_score?: (number) | (null);
        version: string;
    };
    type CreateEdgeDeploymentRequest = {
        artifact_sha256: string;
        device_id: string;
        model_id: string;
        model_version: string;
        pipeline_id: string;
        pipeline_version: string;
    };
    type CreateFeedbackRequest = {
        authorized_for_training?: boolean;
        correction: {
            [key: string]: unknown;
        };
        deidentified?: boolean;
        kind: FeedbackKind;
        model_id: string;
        model_version: string;
        run_id: string;
    };
    type CreateFlowRequest = {
        entry_node_id: string;
        name: string;
        nodes: Array<FlowNode>;
        version: string;
    };
    type CreateHardSampleManifestRequest = {
        dataset_id: string;
        feedback_ids: Array<string>;
        label_schema?: string;
        split?: "train" | "validation" | "test";
        version: string;
    };
    type CreateIdentityProviderRequest = {
        client_id: string;
        display_name: string;
        issuer_url: string;
        kind: IdentityProviderKind;
        scopes?: Array<string>;
    };
    type CreateIdentityRequest = {
        display_name: string;
        metadata?: {
            [key: string]: unknown;
        };
    };
    type CreateIndexBackendRequest = {
        capabilities?: Array<string>;
        endpoint: string;
        kind: string;
        name: string;
    };
    type CreateIndexRebuildRequest = {
        index_id: string;
    };
    type CreateMediaSourceRequest = {
        metadata?: {
            [key: string]: unknown;
        };
        name: string;
        url: string;
    };
    type CreateMembershipRequest = {
        principal_id: AccessId;
        principal_type: PrincipalType;
        project_id?: (AccessId) | (null);
        role_ids: Array<AccessId>;
    };
    type CreateModelReleaseRequest = {
        evidence_refs?: Array<string>;
        model_id: string;
        package_sha256: string;
        version: string;
    };
    type CreateOrganizationRequest = {
        display_name: string;
    };
    type CreatePortraitAssociationRequest = {
        feature_space_id: string;
        left_record_id: string;
        right_record_id: string;
        score: number;
        source?: string;
    };
    type CreatePortraitClusterRequest = {
        confidence?: number;
        feature_space_id: string;
        label?: string;
        member_record_ids: Array<string>;
    };
    type CreatePortraitEventRequest = {
        confidence?: number;
        ended_at?: (number) | (null);
        event_type: string;
        metadata?: {
            [key: string]: unknown;
        };
        source_ids?: Array<string>;
        started_at: number;
        subject_record_ids?: Array<string>;
    };
    type CreateProductEntitlementRequest = {
        product_id: ProductId;
        project_id?: (AccessId) | (null);
        source?: "manual" | "system";
        status?: EntitlementStatus;
    };
    type CreateProjectLifecycleRequest = {
        action: string;
        project_id: string;
        reason?: string;
    };
    type CreateProjectRequest = {
        display_name: string;
        project_id?: (AccessId) | (null);
    };
    type CreateQuotaPlanRequest = {
        limits?: {
            [key: string]: number;
        };
        name: string;
        window_seconds?: number;
    };
    type CreateRoleRequest = {
        display_name: string;
        product_ids?: Array<ProductId>;
        role_id?: (AccessId) | (null);
        scopes: Array<string>;
    };
    type CreateRunRequest = {
        asset_id?: (string) | (null);
        domain: DomainId;
        parameters?: {
            [key: string]: unknown;
        };
        pipeline: PipelineRef;
        priority?: number;
        source_id?: (string) | (null);
        wait_ms?: number;
    };
    type CreateSavedSearchRequest = {
        definition?: {
            [key: string]: unknown;
        };
        description?: string;
        mode: SavedSearchMode;
        name: string;
    };
    type CreateSearchEvaluationRequest = {
        expected_record_ids?: Array<string>;
        profile_id?: (string) | (null);
        query: string;
        result_record_ids?: Array<string>;
    };
    type CreateSearchRankingProfileRequest = {
        exact_weight?: number;
        name: string;
        reranker?: string;
        vector_weight?: number;
    };
    type CreateSearchRelevanceFeedbackRequest = {
        hit_record_id: string;
        relevant: boolean;
        search_id: string;
    };
    type CreateSearchRerankerRequest = {
        endpoint: string;
        kind: string;
        name: string;
    };
    type CreateServiceAccountRequest = {
        display_name: string;
        product_ids?: Array<ProductId>;
        scopes: Array<string>;
        service_account_id?: (AccessId) | (null);
    };
    type CreateSessionRequest = {
        ttl_seconds?: number;
        user_id: string;
    };
    type CreateUserRequest = {
        display_name: string;
        email?: (string) | (null);
        password?: (string) | (null);
        user_id?: (AccessId) | (null);
    };
    type CreateWebhookSubscriptionRequest = {
        event_types: Array<string>;
        name: string;
        secret: string;
        url: string;
    };
    type DatasetPage = {
        items: Array<DatasetRecord>;
        limit: number;
        offset: number;
        total: number;
    };
    type DatasetRecord = {
        created_at: number;
        dataset_id: string;
        description?: string;
        metadata?: {
            [key: string]: unknown;
        };
        name: string;
        project_id: string;
        status?: DatasetStatus;
        tenant_id: string;
        updated_at: number;
    };
    type DatasetStatus = "draft" | "active" | "archived";
    type DatasetVersion = {
        annotation_summary?: {
            [key: string]: unknown;
        };
        asset_ids?: Array<string>;
        created_at: number;
        created_by: string;
        dataset_id: string;
        item_count?: number;
        lineage?: {
            [key: string]: unknown;
        };
        manifest_sha256: string;
        project_id: string;
        quality_score?: (number) | (null);
        status?: DatasetVersionStatus;
        tenant_id: string;
        updated_at: number;
        version: string;
        version_id: string;
    };
    type DatasetVersionPage = {
        items: Array<DatasetVersion>;
        limit: number;
        offset: number;
        total: number;
    };
    type DatasetVersionStatus = "draft" | "validated" | "published" | "retired";
    type DecideApprovalRequest = {
        approved: boolean;
        comment?: string;
    };
    type DecideProjectLifecycleRequest = {
        approved: boolean;
        comment?: string;
    };
    type DeploymentTopology = {
        constraints?: Array<string>;
        lanes?: {
            [key: string]: number;
        };
        mode?: string;
        project_id: string;
        readiness?: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
        workers?: number;
    };
    type DistanceMetric = "cosine" | "l2" | "inner_product";
    type DomainId = string;
    type EdgeDeployment = {
        applied_at?: (number) | (null);
        artifact_sha256: string;
        created_at: number;
        device_id: string;
        model_id: string;
        model_version: string;
        pipeline_id: string;
        pipeline_version: string;
        project_id: string;
        record_id: string;
        status?: string;
        tenant_id: string;
        updated_at: number;
    };
    type EdgeDevice = {
        capabilities?: Array<string>;
        certificate_fingerprint: string;
        created_at: number;
        last_seen_at?: (number) | (null);
        metadata?: {
            [key: string]: unknown;
        };
        name: string;
        project_id: string;
        record_id: string;
        status?: EdgeDeviceStatus;
        tenant_id: string;
        updated_at: number;
    };
    type EdgeDeviceStatus = "pending" | "online" | "offline" | "revoked";
    type EdgeHeartbeatRequest = {
        metadata?: {
            [key: string]: unknown;
        };
        status?: EdgeDeviceStatus;
    };
    type EdgeSyncItem = {
        acknowledged_at?: (number) | (null);
        created_at: number;
        device_id: string;
        direction?: string;
        object_ref: string;
        project_id: string;
        record_id: string;
        sha256: string;
        status?: string;
        tenant_id: string;
    };
    type EnrollIdentityRequest = {
        distance_metric?: DistanceMetric;
        embedding: Array<number>;
        expires_at?: (number) | (null);
        feature_space_id: string;
        modality: "face" | "body" | "gait" | "appearance";
        model_id: string;
        model_version: string;
        quality: number;
        threshold?: (number) | (null);
    };
    type EntitlementStatus = "active" | "suspended";
    type ExecuteFlowRequest = {
        context?: {
            [key: string]: unknown;
        };
    };
    type FeedbackKind = "false_positive" | "false_negative" | "wrong_attribute" | "wrong_identity" | "ocr_correction";
    type FeedbackRecord = {
        authorized_for_training: boolean;
        correction: {
            [key: string]: unknown;
        };
        created_at: number;
        deidentified: boolean;
        feedback_id: string;
        kind: FeedbackKind;
        media_ref: string;
        model_id: string;
        model_version: string;
        pipeline_id: string;
        pipeline_version: string;
        project_id: string;
        result_ref: string;
        review_notes?: string;
        reviewed_by?: (string) | (null);
        run_id: string;
        schema_version?: "1.0";
        status?: FeedbackStatus;
        submitted_by: string;
        tenant_id: string;
        updated_at: number;
    };
    type FeedbackStatus = "pending" | "approved" | "rejected";
    type FlowApproval = {
        comment?: string;
        created_at: number;
        decided_by?: (string) | (null);
        execution_id: string;
        node_id: string;
        project_id: string;
        record_id: string;
        status?: string;
        tenant_id: string;
        updated_at: number;
    };
    type FlowDefinition = {
        created_at: number;
        created_by: string;
        entry_node_id: string;
        name: string;
        nodes: Array<FlowNode>;
        project_id: string;
        record_id: string;
        status?: string;
        tenant_id: string;
        updated_at: number;
        version: string;
    };
    type FlowExecution = {
        completed_at?: (number) | (null);
        context?: {
            [key: string]: unknown;
        };
        created_at: number;
        created_by: string;
        current_node_id: string;
        flow_id: string;
        project_id: string;
        record_id: string;
        status?: string;
        tenant_id: string;
        updated_at: number;
    };
    type FlowNode = {
        config?: {
            [key: string]: unknown;
        };
        kind: FlowNodeKind;
        next_nodes?: Array<string>;
        node_id: string;
    };
    type FlowNodeKind = "run" | "condition" | "approval" | "webhook";
    type GenericDomainPayload = {
        domain: DomainId;
        schema_version?: string;
        [key: string]: unknown;
    };
    type HTTPValidationError = {
        detail?: Array<ValidationError>;
    };
    type HardSampleItem = {
        authorized_for_training?: boolean;
        correction: {
            [key: string]: unknown;
        };
        deidentified?: boolean;
        feedback_id: string;
        kind: FeedbackKind;
        media_ref: string;
        model_id: string;
        model_version: string;
        pipeline_id: string;
        pipeline_version: string;
        result_ref: string;
    };
    type HardSampleManifest = {
        created_at: number;
        created_by: string;
        dataset_id: string;
        items: Array<HardSampleItem>;
        label_schema?: string;
        manifest_id: string;
        project_id: string;
        schema_version?: "1.0";
        sha256: string;
        split?: "train" | "validation" | "test";
        tenant_id: string;
        version: string;
    };
    type IamInventory = {
        api_keys: number;
        memberships: number;
        organizations: number;
        product_entitlements: number;
        projects: number;
        roles: number;
        service_accounts: number;
        users: number;
    };
    type IamSummary = {
        default_admin_scopes: Array<string>;
        inventory: IamInventory;
        project_id: string;
        schema_version?: "1.0";
        tenant_id: string;
    };
    type IdentityPage = {
        items: Array<LongTermIdentity>;
        limit: number;
        offset: number;
        total: number;
    };
    type IdentityProvider = {
        client_id: string;
        created_at: number;
        display_name: string;
        enabled?: boolean;
        issuer_url: string;
        kind: IdentityProviderKind;
        last_health?: string;
        project_id: string;
        record_id: string;
        scopes?: Array<string>;
        tenant_id: string;
        updated_at: number;
    };
    type IdentityProviderKind = "oidc" | "saml" | "scim";
    type IndexBackend = {
        capabilities?: Array<string>;
        created_at: number;
        enabled?: boolean;
        endpoint: string;
        health?: string;
        kind: string;
        name: string;
        project_id: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
    };
    type IndexDefinition = {
        created_at?: number;
        distance_metric?: (string) | (null);
        domain: string;
        index_id: string;
        record_kind: IndexRecordKind;
        schema_version?: string;
        text_analyzer?: (string) | (null);
        threshold?: (number) | (null);
        vector_dimension?: (number) | (null);
        vector_model_id?: (string) | (null);
        vector_model_version?: (string) | (null);
    };
    type IndexHit = {
        distance?: (number) | (null);
        domain: string;
        feature_id?: (string) | (null);
        index_id: string;
        metadata?: {
            [key: string]: unknown;
        };
        record_id: string;
        score?: (number) | (null);
        source: IndexSourceRef;
        text_snippet?: (string) | (null);
    };
    type IndexRebuildJob = {
        completed_at?: (number) | (null);
        created_at: number;
        created_by: string;
        index_id: string;
        project_id: string;
        record_id: string;
        records_rebuilt?: number;
        records_seen?: number;
        status?: string;
        tenant_id: string;
    };
    type IndexRecordKind = "vector" | "text" | "multimodal";
    type IndexRecordStatus = "ready" | "pending" | "failed" | "deleted";
    type IndexRecordView = {
        created_at: number;
        deleted_at?: (number) | (null);
        domain: string;
        expires_at?: (number) | (null);
        feature_id?: (string) | (null);
        has_vector?: boolean;
        index_id: string;
        kind: IndexRecordKind;
        metadata?: {
            [key: string]: unknown;
        };
        record_id: string;
        source: IndexSourceRef;
        status: IndexRecordStatus;
        text_snippet?: (string) | (null);
    };
    type IndexSourceRef = {
        artifact_id?: (string) | (null);
        asset_id?: (string) | (null);
        object_id?: (string) | (null);
        page_number?: (number) | (null);
        pts_ms?: (number) | (null);
        run_id?: (string) | (null);
        source_id: string;
        source_type: string;
        unit_id?: (string) | (null);
    };
    type IndexTextQueryRequest = {
        limit?: number;
        query: string;
    };
    type IndexVectorQueryRequest = {
        limit?: number;
        threshold?: (number) | (null);
        vector: Array<number>;
    };
    type InteractiveSession = {
        created_at: number;
        expires_at: number;
        last_used_at?: (number) | (null);
        product_ids?: Array<string>;
        project_id: string;
        revoked_at?: (number) | (null);
        scopes?: Array<string>;
        session_id: string;
        tenant_id: string;
        token_prefix: string;
        token_sha256: string;
        user_id: string;
    };
    type LifecycleStatus = "active" | "disabled" | "deleted" | "pending_restore";
    type LoginRequest = {
        password: string;
        ttl_seconds?: number;
        username: AccessId;
    };
    type LongTermIdentity = {
        camera_ids?: Array<string>;
        created_at?: number;
        display_name?: string;
        feature_space_ids?: {
            [key: string]: string;
        };
        first_seen_at: number;
        identity_id: string;
        last_camera_id?: string;
        last_seen_at: number;
        metadata?: {
            [key: string]: unknown;
        };
        modalities?: Array<string>;
        project_id: string;
        segment_count?: number;
        status?: "auto" | "confirmed" | "rejected";
        tenant_id: string;
        updated_at?: number;
    };
    type MediaAsset = {
        asset_id: string;
        content_type: string;
        created_at: number;
        deleted_at?: (number) | (null);
        expires_at?: (number) | (null);
        filename?: (string) | (null);
        kind: MediaKind;
        metadata?: MediaTechnicalMetadata;
        object_key: string;
        original_deleted_at?: (number) | (null);
        preview_content_type?: (string) | (null);
        preview_object_key?: (string) | (null);
        preview_sha256?: (string) | (null);
        project_id: string;
        sha256: string;
        size_bytes: number;
        temporary?: boolean;
        tenant_id: string;
    };
    type MediaAssetPage = {
        items: Array<MediaAsset>;
        limit: number;
        offset: number;
        total: number;
    };
    type MediaKind = "image" | "video" | "document" | "stream";
    type MediaSourcePage = {
        items: Array<MediaSourceView>;
        limit: number;
        offset: number;
        total: number;
    };
    type MediaSourceProbe = {
        checked_at: number;
        latency_ms: number;
        metadata?: MediaTechnicalMetadata;
        reachable: boolean;
        source_id: string;
    };
    type MediaSourceView = {
        created_at: number;
        kind?: SourceKind;
        masked_url: string;
        metadata?: {
            [key: string]: unknown;
        };
        name: string;
        source_id: string;
    };
    type MediaTechnicalMetadata = {
        codec?: (string) | (null);
        container?: (string) | (null);
        decode_seek_used?: (boolean) | (null);
        duration_ms?: (number) | (null);
        elapsed_ms?: (number) | (null);
        format?: (string) | (null);
        fps?: (number) | (null);
        frame_count?: (number) | (null);
        frame_max_edge?: (number) | (null);
        frames_read?: (number) | (null);
        height?: (number) | (null);
        keyframe_count?: (number) | (null);
        page_count?: (number) | (null);
        reconnect_count?: (number) | (null);
        sample_end_ms?: (number) | (null);
        sample_interval_ms?: (number) | (null);
        sample_start_ms?: (number) | (null);
        sample_strategy?: (SampleStrategy) | (null);
        sampled_units?: (number) | (null);
        scene_change_count?: (number) | (null);
        stream_segment_duration_ms?: (number) | (null);
        stream_segment_index?: (number) | (null);
        timestamp_source?: ("decoder_pts" | "position_msec" | "monotonic_clock") | (null);
        width?: (number) | (null);
    };
    type MediaUnitResult = {
        frame_artifact_id?: (string) | (null);
        height: number;
        index: number;
        objects?: Array<VisionObject>;
        page_number?: (number) | (null);
        pts_ms?: (number) | (null);
        unit_id: string;
        unit_type: "frame" | "page";
        width: number;
    };
    type Membership = {
        created_at: number;
        principal_id: AccessId;
        principal_type: PrincipalType;
        project_id: AccessId;
        role_ids: Array<AccessId>;
        tenant_id: AccessId;
        updated_at: number;
    };
    type MergeIdentitiesRequest = {
        source_identity_ids: Array<string>;
        target_identity_id: string;
    };
    type ModelDeploymentEvent = {
        action: string;
        audit_id: string;
        capability: string;
        created_at: number;
        event_id: string;
        from_status: (ModelReleaseStatus) | (null);
        model_id: string;
        operator_id: string;
        package_sha256: string;
        project_id: string;
        reason: string;
        runtime_model_id: string;
        schema_version?: "1.0";
        tenant_id: string;
        to_status: ModelReleaseStatus;
        version: string;
    };
    type ModelHealthSnapshot = {
        capability: string;
        degraded?: boolean;
        error_rate: number;
        evaluated_at: number;
        model_id: string;
        model_version: string;
        p95_latency_ms?: (number) | (null);
        quality_score?: (number) | (null);
        rollback_recommended?: boolean;
        sample_count: number;
    };
    type ModelMetricPoint = {
        capability: string;
        created_at: number;
        error_rate?: number;
        latency_ms: number;
        model_id: string;
        model_version: string;
        project_id: string;
        quality_score?: (number) | (null);
        record_id: string;
        tenant_id: string;
        throughput?: (number) | (null);
    };
    type ModelPackageManifest = {
        adapter: string;
        capability: string;
        evaluation_evidence: Array<string>;
        license_id: string;
        model_card: string;
        model_id: string;
        production_ready?: boolean;
        regression_samples: Array<string>;
        runtime_model_id: string;
        schema_version?: "1.0";
        sha256: string;
        source_uri: string;
        version: string;
        vram_mb: number;
    };
    type ModelProvenance = {
        capability: string;
        model_id: string;
        production_ready?: boolean;
        sha256?: (string) | (null);
        version: string;
    };
    type ModelRelease = {
        activated_at?: (number) | (null);
        capability: string;
        created_at: number;
        created_by: string;
        evidence_refs?: Array<string>;
        model_id: string;
        package_sha256: string;
        project_id: string;
        retired_at?: (number) | (null);
        runtime_model_id: string;
        schema_version?: "1.0";
        status?: ModelReleaseStatus;
        tenant_id: string;
        updated_at: number;
        version: string;
    };
    type ModelReleaseStatus = "candidate" | "validated" | "approved" | "active" | "retired";
    type OcrDomainPayload = {
        blocks?: Array<OcrTextBlock>;
        domain?: "ocr";
        language?: (string) | (null);
        schema_version?: "1.0";
        text?: string;
        [key: string]: unknown;
    };
    type OcrTextBlock = {
        block_id: string;
        block_type?: "text" | "title" | "paragraph" | "image" | "table";
        polygon?: Array<Point>;
        reading_order?: (number) | (null);
        score?: (number) | (null);
        text: string;
        [key: string]: unknown;
    };
    type Organization = {
        created_at: number;
        display_name: string;
        tenant_id: AccessId;
        updated_at: number;
    };
    type ParseDocumentResponse = {
        asset: MediaAsset;
        result?: (ResultEnvelope) | (null);
        run: RunRecord;
    };
    type ParseImageResponse = {
        asset: MediaAsset;
        result?: (ResultEnvelope) | (null);
        run: RunRecord;
    };
    type ParseStreamRequest = {
        domain: DomainId;
        parameters?: {
            [key: string]: unknown;
        };
        pipeline: PipelineSelection;
        priority?: number;
        source_id: string;
        wait_ms?: number;
    };
    type ParseVideoResponse = {
        asset: MediaAsset;
        result?: (ResultEnvelope) | (null);
        run: RunRecord;
    };
    type PipelineRef = {
        pipeline_id: string;
        version: string;
    };
    type PipelineSelection = {
        pipeline_id: string;
        version?: (string) | (null);
    };
    type PipelineStatus = "draft" | "validated" | "approved" | "active" | "retired";
    type PipelineTransitionRequest = {
        status: PipelineStatus;
    };
    type Point = {
        x: number;
        y: number;
    };
    type PortraitAssetCompareRequest = {
        feature_space_id?: (string) | (null);
        left_asset_id: string;
        right_asset_id: string;
        threshold?: (number) | (null);
    };
    type PortraitAssetItem = {
        asset_id: PortraitModuleId;
        depends_on_modules?: Array<PortraitModuleId>;
        maturity: PortraitModuleMaturity;
        name: string;
        next_gate: string;
        summary: string;
    };
    type PortraitAssociation = {
        created_at: number;
        feature_space_id: string;
        left_record_id: string;
        project_id: string;
        record_id: string;
        right_record_id: string;
        score: number;
        source?: string;
        tenant_id: string;
    };
    type PortraitCapabilityItem = {
        capability_id: string;
        current_model?: (string) | (null);
        embedding_dimension?: (number) | (null);
        production_ready: boolean;
        readiness: PortraitCapabilityReadiness;
        target_embedding_dimension?: (number) | (null);
        target_model?: (string) | (null);
    };
    type PortraitCapabilityReadiness = "ready" | "fallback" | "placeholder" | "not_configured";
    type PortraitCluster = {
        confidence?: number;
        confirmed?: boolean;
        created_at: number;
        feature_space_id: string;
        label?: string;
        member_record_ids?: Array<string>;
        project_id: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
    };
    type PortraitCompareRequest = {
        feature_space_id: string;
        left: Array<number>;
        right: Array<number>;
    };
    type PortraitCompareResponse = {
        comparison_id?: (string) | (null);
        distance: number;
        feature_space_id: string;
        left?: (PortraitInputSummary) | (null);
        matched: (boolean) | (null);
        mode?: "vector" | "image" | "asset" | "mixed";
        right?: (PortraitInputSummary) | (null);
        score: number;
        threshold: (number) | (null);
    };
    type PortraitDomainPayload = {
        capabilities?: Array<string>;
        domain?: "portrait";
        faces?: Array<VisionObject>;
        persons?: Array<VisionObject>;
        schema_version?: "1.0";
        tracks?: Array<{
            [key: string]: unknown;
        }>;
        [key: string]: unknown;
    };
    type PortraitEnrollment = {
        created_at: number;
        enrollment_id: string;
        expires_at?: (number) | (null);
        feature_id: string;
        feature_space_id: string;
        identity_id: string;
        index_record_id?: (string) | (null);
        modality: "face" | "body" | "gait" | "appearance";
        project_id: string;
        quality: number;
        tenant_id: string;
    };
    type PortraitEvent = {
        confidence?: number;
        ended_at?: (number) | (null);
        event_type: string;
        metadata?: {
            [key: string]: unknown;
        };
        project_id: string;
        record_id: string;
        source_ids?: Array<string>;
        started_at: number;
        subject_record_ids?: Array<string>;
        tenant_id: string;
    };
    type PortraitIdentity = {
        created_at: number;
        display_name: string;
        identity_id: string;
        metadata?: {
            [key: string]: unknown;
        };
        project_id: string;
        tenant_id: string;
        updated_at: number;
    };
    type PortraitIdentityPage = {
        items: Array<PortraitIdentity>;
        limit: number;
        offset: number;
        total: number;
    };
    type PortraitInputSummary = {
        embedding_dimension: number;
        face_count: number;
        fallback?: boolean;
        metadata?: {
            [key: string]: unknown;
        };
        model_id: string;
        model_version: string;
        quality_score?: (number) | (null);
        selected_face_box?: (Array<number>) | (null);
        selected_face_index: number;
    };
    type PortraitIntelligenceStatus = {
        assets: Array<PortraitAssetItem>;
        capabilities: Array<PortraitCapabilityItem>;
        modules: Array<PortraitModuleItem>;
        positioning?: "portrait_intelligence_foundation_platform";
        schema_version?: "1.0";
    };
    type PortraitModuleId = string;
    type PortraitModuleItem = {
        current_scope?: Array<string>;
        maturity: PortraitModuleMaturity;
        module_id: PortraitModuleId;
        name: string;
        next_gate: string;
        not_in_scope_yet?: Array<string>;
        owner_repository_id: RepositoryId;
        summary: string;
    };
    type PortraitModuleMaturity = "available" | "partial" | "seed" | "planned" | "external";
    type PortraitSearchMatch = {
        distance: number;
        enrollment_id: string;
        identity: PortraitIdentity;
        modality: "face" | "body" | "gait" | "appearance";
        score: number;
    };
    type PortraitSearchRequest = {
        embedding: Array<number>;
        feature_space_id: string;
        limit?: number;
        threshold?: (number) | (null);
    };
    type PortraitSearchResponse = {
        feature_space_id: string;
        matches: Array<PortraitSearchMatch>;
    };
    type PresignMediaUploadRequest = {
        content_type: string;
        filename?: (string) | (null);
        kind: MediaKind;
        sha256: string;
        size_bytes: number;
    };
    type PresignedMediaDownload = {
        expires_at: number;
        headers?: {
            [key: string]: string;
        };
        method?: "GET";
        url: string;
    };
    type PresignedMediaUpload = {
        expires_at: number;
        headers: {
            [key: string]: string;
        };
        method?: "PUT";
        upload_id: string;
        upload_token: string;
        url: string;
    };
    type PrincipalType = "user" | "service_account";
    type ProductCatalogItem = {
        api_paths?: Array<string>;
        console_route?: (string) | (null);
        current_scope?: Array<string>;
        depends_on?: Array<ProductId>;
        layer: ProductLayer;
        maturity: ProductMaturity;
        name: string;
        next_gate: string;
        not_in_scope_yet?: Array<string>;
        product_id: ProductId;
        summary: string;
    };
    type ProductEntitlement = {
        created_at: number;
        product_id: ProductId;
        project_id: AccessId;
        source?: "manual" | "system";
        status?: EntitlementStatus;
        tenant_id: AccessId;
        updated_at: number;
    };
    type ProductId = string;
    type ProductLayer = "product_module" | "control_plane" | "developer_surface" | "foundation";
    type ProductMaturity = "available" | "seed" | "planned" | "gated";
    type Project = {
        created_at: number;
        display_name: string;
        project_id: AccessId;
        tenant_id: AccessId;
        updated_at: number;
    };
    type ProjectLifecycleRequest = {
        action: string;
        created_at: number;
        decided_at?: (number) | (null);
        decided_by?: (string) | (null);
        decision_comment?: string;
        project_id: string;
        reason?: string;
        record_id: string;
        requested_by: string;
        status?: string;
        tenant_id: string;
        updated_at: number;
    };
    type ProposeAgentActionRequest = {
        input?: {
            [key: string]: unknown;
        };
        tool_id: string;
    };
    type ProvenanceEvidence = {
        development_substitutes?: Array<string>;
        generated_by?: string;
        source_sha256?: (string) | (null);
    };
    type PurgeAuditRequest = {
        dry_run?: boolean;
        reason: string;
    };
    type PurgeAuditResponse = {
        cutoff_at: number;
        deleted_count: number;
        dry_run: boolean;
        executed_at: number;
    };
    type PutAgentMemoryRequest = {
        key: string;
        namespace: string;
        ttl_seconds?: (number) | (null);
        value?: {
            [key: string]: unknown;
        };
    };
    type QuotaCheckRequest = {
        amount?: number;
        metric: string;
    };
    type QuotaCheckResponse = {
        allowed: boolean;
        usage: QuotaUsage;
    };
    type QuotaPlan = {
        created_at: number;
        enabled?: boolean;
        limits?: {
            [key: string]: number;
        };
        name: string;
        project_id: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
        window_seconds?: number;
    };
    type QuotaUsage = {
        limit?: (number) | (null);
        metric: string;
        used?: number;
        window_ends_at: number;
        window_started_at: number;
    };
    type RegisterAgentToolRequest = {
        description: string;
        name: string;
        requires_approval?: boolean;
        scopes?: Array<string>;
    };
    type RegisterCameraRequest = {
        camera_id: string;
        display_name?: string;
        location?: string;
        metadata?: {
            [key: string]: unknown;
        };
    };
    type RegisterEdgeDeviceRequest = {
        capabilities?: Array<string>;
        metadata?: {
            [key: string]: unknown;
        };
        name: string;
    };
    type RegisterWorkerRequest = {
        capacity?: number;
        lane: string;
        lease_seconds?: number;
        worker_id: string;
    };
    type RepositoryBoundaryRule = "versioned_contracts_only" | "no_shared_database" | "no_cross_repository_source_imports" | "immutable_artifact_references";
    type RepositoryContractArtifact = {
        compatibility?: "backward";
        consumer_repository_id: string;
        contract_id: string;
        example_path: string;
        example_sha256: string;
        payload_schema_version: string;
        payload_type: string;
        producer_repository_id: string;
        release_version: string;
        schema_path: string;
        schema_sha256: string;
        transport: "versioned_api" | "event" | "immutable_manifest";
    };
    type RepositoryContractCatalog = {
        contracts: Array<RepositoryContractArtifact>;
        package_name: string;
        release_version: string;
        schema_version?: "1.0";
    };
    type RepositoryContractTransport = "versioned_api" | "event" | "immutable_manifest";
    type RepositoryId = string;
    type RepositoryIntegrationContract = {
        compatibility?: "backward";
        consumer_repository_id: RepositoryId;
        contract_id: string;
        invariants?: Array<RepositoryResponsibilityId>;
        payload_type: string;
        producer_repository_id: RepositoryId;
        release_version: string;
        schema_path: string;
        transport: RepositoryContractTransport;
    };
    type RepositoryKind = "platform_integration" | "specialized_product";
    type RepositoryLifecycle = "current" | "external_existing" | "planned";
    type RepositoryResponsibilityId = string;
    type RepositoryTopology = {
        boundary_rules: Array<RepositoryBoundaryRule>;
        current_repository_id: RepositoryId;
        integration_contracts: Array<RepositoryIntegrationContract>;
        repositories: Array<RepositoryTopologyItem>;
        schema_version?: "1.0";
    };
    type RepositoryTopologyItem = {
        current_repository?: boolean;
        excluded_responsibilities?: Array<RepositoryResponsibilityId>;
        integration_product_ids?: Array<ProductId>;
        kind: RepositoryKind;
        lifecycle: RepositoryLifecycle;
        name: string;
        next_gate: string;
        primary_product_ids?: Array<ProductId>;
        repository_id: RepositoryId;
        responsibilities?: Array<RepositoryResponsibilityId>;
    };
    type ResourceLifecycleRecord = {
        created_at: number;
        deleted_at?: (number) | (null);
        project_id: string;
        reason?: string;
        record_id: string;
        resource_id: string;
        resource_type: string;
        status?: LifecycleStatus;
        tenant_id: string;
        updated_at: number;
        updated_by: string;
    };
    type ResultArtifact = {
        artifact_id: string;
        artifact_type: string;
        content_type: string;
        object_key: string;
        sha256: string;
    };
    type ResultEnvelope = {
        artifacts?: Array<ResultArtifact>;
        asset_id?: (string) | (null);
        created_at: number;
        domain: DomainId;
        domain_payload: (PortraitDomainPayload) | (OcrDomainPayload) | (GenericDomainPayload);
        media_metadata?: MediaTechnicalMetadata;
        models?: Array<ModelProvenance>;
        pipeline: PipelineRef;
        provenance?: ProvenanceEvidence;
        relations?: Array<ResultRelation>;
        run_id: string;
        schema_version?: "1.0";
        source_id?: (string) | (null);
        timings?: {
            [key: string]: number;
        };
        units?: Array<MediaUnitResult>;
        warnings?: Array<string>;
    };
    type ResultPage = {
        result: ResultEnvelope;
        unit_limit: number;
        unit_offset: number;
        unit_total: number;
    };
    type ResultRelation = {
        relation_type: string;
        score?: (number) | (null);
        source_object_id: string;
        target_object_id: string;
    };
    type ResultSummary = {
        asset_id?: (string) | (null);
        created_at: number;
        domain: DomainId;
        face_count: number;
        index_status?: "ready" | "partial";
        media_kind?: (MediaKind) | (null);
        object_count: number;
        ocr_block_count: number;
        person_count: number;
        pipeline: PipelineRef;
        resource_name?: (string) | (null);
        result_id: string;
        run_id: string;
        source_id?: (string) | (null);
        status: RunStatus;
        text_length: number;
        unit_count: number;
        warning_count: number;
    };
    type ResultSummaryPage = {
        items: Array<ResultSummary>;
        limit: number;
        offset: number;
        total: number;
    };
    type ReviewAnnotationTaskRequest = {
        approved: boolean;
        comment?: string;
        consistency_score: number;
    };
    type ReviewFeedbackRequest = {
        notes?: string;
        status: FeedbackStatus;
    };
    type Role = {
        created_at: number;
        display_name: string;
        product_ids?: Array<ProductId>;
        role_id: AccessId;
        scopes: Array<string>;
        tenant_id: AccessId;
        updated_at: number;
    };
    type RollbackModelReleaseRequest = {
        reason: string;
        target_version: string;
    };
    type RunPage = {
        items: Array<RunRecord>;
        limit: number;
        offset: number;
        total: number;
    };
    type RunRecord = {
        asset_id?: (string) | (null);
        completed_at?: (number) | (null);
        created_at: number;
        domain: DomainId;
        error_code?: (string) | (null);
        next_run_id?: (string) | (null);
        parameters?: {
            [key: string]: unknown;
        };
        pipeline: PipelineRef;
        previous_run_id?: (string) | (null);
        principal_id?: string;
        priority?: number;
        progress?: number;
        project_id: string;
        revision?: number;
        run_id: string;
        source_id?: (string) | (null);
        started_at?: (number) | (null);
        status?: RunStatus;
        stream_segment_index?: (number) | (null);
        stream_session_id?: (string) | (null);
        tenant_id: string;
        termination_reason?: (string) | (null);
        updated_at: number;
    };
    type RunStatus = "queued" | "running" | "pausing" | "paused" | "completed" | "failed" | "cancelling" | "cancelled";
    type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";
    type SavedSearch = {
        created_at: number;
        created_by: string;
        definition?: {
            [key: string]: unknown;
        };
        description?: string;
        last_run_at?: (number) | (null);
        mode: SavedSearchMode;
        name: string;
        project_id: string;
        saved_search_id: string;
        tenant_id: string;
        updated_at: number;
    };
    type SavedSearchMode = "text" | "portrait";
    type SavedSearchPage = {
        items: Array<SavedSearch>;
        limit: number;
        offset: number;
        total: number;
    };
    type SearchAssetRequest = {
        asset_id: string;
        feature_space_id?: (string) | (null);
        limit?: number;
        media_kinds?: Array<MediaKind>;
        profile_id?: (string) | (null);
        threshold?: (number) | (null);
    };
    type SearchEvaluation = {
        created_at: number;
        created_by: string;
        expected_record_ids?: Array<string>;
        precision: number;
        profile_id?: (string) | (null);
        project_id: string;
        query: string;
        recall: number;
        record_id: string;
        result_record_ids?: Array<string>;
        tenant_id: string;
    };
    type SearchImageInputSummary = {
        embedding_dimension: number;
        face_count: number;
        fallback?: boolean;
        feature_space_id: string;
        model_id: string;
        model_version: string;
        quality_score?: (number) | (null);
        selected_face_index: number;
    };
    type SearchRankingProfile = {
        active?: boolean;
        created_at: number;
        exact_weight?: number;
        name: string;
        project_id: string;
        record_id: string;
        reranker?: string;
        tenant_id: string;
        updated_at: number;
        vector_weight?: number;
    };
    type SearchRelevanceFeedback = {
        created_at: number;
        created_by: string;
        hit_record_id: string;
        project_id: string;
        record_id: string;
        relevant: boolean;
        search_id: string;
        tenant_id: string;
    };
    type SearchReranker = {
        created_at: number;
        enabled?: boolean;
        endpoint: string;
        health?: string;
        kind: string;
        name: string;
        project_id: string;
        record_id: string;
        tenant_id: string;
        updated_at: number;
    };
    type SearchResponse = {
        feature_space_id?: (string) | (null);
        hits: Array<SearchResultHit>;
        mode: "text" | "portrait";
        query?: (string) | (null);
        query_summary?: (SearchImageInputSummary) | (null);
        search_id: string;
        searched_indexes?: Array<string>;
        total: number;
    };
    type SearchResultHit = {
        distance?: (number) | (null);
        domain: string;
        index_id: string;
        media_kind?: (MediaKind) | (null);
        metadata?: {
            [key: string]: unknown;
        };
        record_id: string;
        resource_name?: (string) | (null);
        score?: (number) | (null);
        source: {
            [key: string]: unknown;
        };
        text_snippet?: (string) | (null);
    };
    type SearchTextRequest = {
        domains?: Array<string>;
        limit?: number;
        media_kinds?: Array<MediaKind>;
        profile_id?: (string) | (null);
        query: string;
    };
    type SegmentPage = {
        items: Array<TrajectorySegment>;
        limit: number;
        offset: number;
        total: number;
    };
    type ServiceAccount = {
        created_at: number;
        disabled?: boolean;
        display_name: string;
        product_ids?: Array<ProductId>;
        project_id: AccessId;
        scopes: Array<string>;
        service_account_id: AccessId;
        tenant_id: AccessId;
        updated_at: number;
    };
    type SessionResponse = {
        session: InteractiveSession;
        token: string;
    };
    type SetAuditRetentionPolicyRequest = {
        enabled?: boolean;
        export_approval_required?: boolean;
        retention_days: number;
    };
    type SetCameraTransitionsRequest = {
        transitions?: Array<CameraTransitionEntry>;
    };
    type SourceKind = "stream";
    type SplitIdentityRequest = {
        display_name?: string;
        segment_ids: Array<string>;
    };
    type StreamSessionView = {
        created_at: number;
        current_run_id: string;
        domain: DomainId;
        pipeline: PipelineRef;
        segment_count: number;
        session_id: string;
        source_id: string;
        status: "active" | "completed" | "failed" | "cancelled";
        updated_at: number;
    };
    type SystemStatus = {
        auth_required: boolean;
        object_backend: string;
        policy_provider?: string;
        production_models_required: boolean;
        profile: string;
        queue_backend: string;
        state_backend: string;
        version: string;
    };
    type TimelineEntry = {
        camera_id: string;
        camera_name?: string;
        duration_seconds: number;
        first_seen_at: number;
        last_seen_at: number;
        match_method: "new_identity" | "reid" | "manual";
        match_score: number;
        run_id: string;
        segment_id: string;
        transition_seconds?: (number) | (null);
    };
    type TrajectorySegment = {
        asset_id?: string;
        camera_id?: string;
        created_at?: number;
        feature_ids?: {
            [key: string]: string;
        };
        first_pts_ms?: (number) | (null);
        first_seen_at: number;
        frame_count?: number;
        identity_id: string;
        last_pts_ms?: (number) | (null);
        last_seen_at: number;
        match_method?: "new_identity" | "reid" | "manual";
        match_score?: number;
        match_scores?: {
            [key: string]: number;
        };
        metadata?: {
            [key: string]: unknown;
        };
        project_id: string;
        run_id: string;
        segment_id: string;
        source_id?: string;
        tenant_id: string;
        track_id?: string;
        track_quality?: number;
    };
    type TransitionDatasetVersionRequest = {
        status: DatasetVersionStatus;
    };
    type TransitionModelReleaseRequest = {
        reason: string;
        status: ModelReleaseStatus;
    };
    type UpdateCameraRequest = {
        display_name?: (string) | (null);
        location?: (string) | (null);
        metadata?: ({
            [key: string]: unknown;
        }) | (null);
    };
    type UpdateDatasetRequest = {
        description?: (string) | (null);
        metadata?: ({
            [key: string]: unknown;
        }) | (null);
        name?: (string) | (null);
        status?: (DatasetStatus) | (null);
    };
    type UpdateIdentityRequest = {
        display_name?: (string) | (null);
        metadata?: ({
            [key: string]: unknown;
        }) | (null);
        status?: ("auto" | "confirmed" | "rejected") | (null);
    };
    type UpdateProductEntitlementRequest = {
        source?: "manual" | "system";
        status: EntitlementStatus;
    };
    type UpdateSavedSearchRequest = {
        definition?: ({
            [key: string]: unknown;
        }) | (null);
        description?: (string) | (null);
        name?: (string) | (null);
    };
    type UserAccount = {
        created_at: number;
        disabled?: boolean;
        display_name: string;
        email?: (string) | (null);
        tenant_id: AccessId;
        updated_at: number;
        user_id: AccessId;
    };
    type ValidationError = {
        ctx?: {};
        input?: unknown;
        loc: Array<(string) | (number)>;
        msg: string;
        type: string;
    };
    type VisionObject = {
        attributes?: {
            [key: string]: unknown;
        };
        bbox?: (BoundingBox) | (null);
        crop_artifact_id?: (string) | (null);
        feature_refs?: Array<string>;
        object_id: string;
        object_type: string;
        polygon?: (Array<Point>) | (null);
        score?: (number) | (null);
        track_id?: (string) | (null);
        [key: string]: unknown;
    };
    type WebhookDeliveryRecord = {
        attempts?: number;
        created_at: number;
        delivered_at?: (number) | (null);
        delivery_id: string;
        endpoint_id: string;
        event_id: string;
        event_type: string;
        last_error?: (string) | (null);
        next_attempt_at: number;
        payload: {
            [key: string]: unknown;
        };
        project_id: string;
        status?: "pending" | "delivering" | "delivered" | "dead_letter";
        status_code?: (number) | (null);
        tenant_id: string;
        updated_at: number;
    };
    type WebhookSubscriptionView = {
        created_at: number;
        enabled: boolean;
        endpoint_id: string;
        event_types: Array<string>;
        name: string;
        url: string;
    };
    type WorkerHeartbeatRequest = {
        lease_seconds?: number;
    };
    type WorkerLease = {
        capacity?: number;
        created_at: number;
        lane: string;
        last_heartbeat_at: number;
        lease_expires_at: number;
        project_id: string;
        record_id: string;
        status?: string;
        tenant_id: string;
        worker_id: string;
    };
}
//# sourceMappingURL=generated.d.ts.map