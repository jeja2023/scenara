export declare const OPENAPI_SHA256 = "eaa6fb8c12733cca0af76dfce006f159a74881092e62b649b1a8c2f9e50aedab" /** gitleaks:allow - public contract digest */;
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
    type ApiEnvelope_AccessFoundationStatus_ = {
        data: AccessFoundationStatus;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ApiKeyRecord_ = {
        data: ApiKeyRecord;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_ComplianceEvidence_ = {
        data: ComplianceEvidence;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_CreateApiKeyResponse_ = {
        data: CreateApiKeyResponse;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_EnterpriseStatus_ = {
        data: EnterpriseStatus;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_FeedbackRecord_ = {
        data: FeedbackRecord;
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
    type ApiEnvelope_Incident_ = {
        data: Incident;
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
    type ApiEnvelope_ProductEntitlement_ = {
        data: ProductEntitlement;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_Project_ = {
        data: Project;
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
    type ApiEnvelope_ServiceAccount_ = {
        data: ServiceAccount;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SlaSnapshot_ = {
        data: SlaSnapshot;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SupportCase_ = {
        data: SupportCase;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_SystemStatus_ = {
        data: SystemStatus;
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
    type ApiEnvelope_list_ApiKeyRecord__ = {
        data: Array<ApiKeyRecord>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ComplianceEvidence__ = {
        data: Array<ComplianceEvidence>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_FeedbackRecord__ = {
        data: Array<FeedbackRecord>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_HardSampleManifest__ = {
        data: Array<HardSampleManifest>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_Incident__ = {
        data: Array<Incident>;
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
    type ApiEnvelope_list_Project__ = {
        data: Array<Project>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_Role__ = {
        data: Array<Role>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_ServiceAccount__ = {
        data: Array<ServiceAccount>;
        request_id: string;
        schema_version?: "1.0";
    };
    type ApiEnvelope_list_SupportCase__ = {
        data: Array<SupportCase>;
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
    type Body_create_media_asset_api_v1_media_assets_post = {
        file: string;
        kind?: MediaKind;
    };
    type Body_parse_document_api_v1_parse_document_post = {
        domain?: DomainId;
        file: string;
        max_units?: number;
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
        domain?: DomainId;
        file: string;
        frame_max_edge?: (number) | (null);
        max_units?: number;
        page_scale?: number;
        pipeline_id?: (string) | (null);
        pipeline_version?: (string) | (null);
        sample_end_ms?: (number) | (null);
        sample_interval_ms?: number;
        sample_start_ms?: number;
        sample_strategy?: SampleStrategy;
        scene_change_threshold?: number;
        wait_ms?: number;
    };
    type BoundingBox = {
        height: number;
        width: number;
        x: number;
        y: number;
    };
    type ComplianceEvidence = {
        created_at: number;
        evidence_id: string;
        evidence_type: string;
        metadata?: {
            [key: string]: unknown;
        };
        object_ref: string;
        project_id: string;
        sha256: string;
        signed_by: string;
        tenant_id: string;
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
    type CreateComplianceEvidenceRequest = {
        evidence_type: string;
        metadata?: {
            [key: string]: unknown;
        };
        object_ref: string;
        sha256: string;
        signed_by: string;
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
    type CreateHardSampleManifestRequest = {
        dataset_id: string;
        feedback_ids: Array<string>;
        label_schema?: string;
        split?: "train" | "validation" | "test";
        version: string;
    };
    type CreateIdentityRequest = {
        display_name: string;
        metadata?: {
            [key: string]: unknown;
        };
    };
    type CreateIncidentRequest = {
        severity: "sev1" | "sev2" | "sev3" | "sev4";
        started_at?: (number) | (null);
        summary?: string;
        title: string;
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
    type CreateProductEntitlementRequest = {
        product_id: ProductId;
        project_id?: (AccessId) | (null);
        source?: "manual" | "enterprise_license" | "system";
        status?: EntitlementStatus;
    };
    type CreateProjectRequest = {
        display_name: string;
        project_id?: (AccessId) | (null);
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
    type CreateServiceAccountRequest = {
        display_name: string;
        product_ids?: Array<ProductId>;
        scopes: Array<string>;
        service_account_id?: (AccessId) | (null);
    };
    type CreateSupportCaseRequest = {
        description: string;
        priority?: "low" | "normal" | "high" | "urgent";
        subject: string;
    };
    type CreateUserRequest = {
        display_name: string;
        email?: (string) | (null);
        user_id?: (AccessId) | (null);
    };
    type CreateWebhookSubscriptionRequest = {
        event_types: Array<string>;
        name: string;
        secret: string;
        url: string;
    };
    type DistanceMetric = "cosine" | "l2" | "inner_product";
    type DomainId = string;
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
    type EnterpriseStatus = {
        customer: string;
        document_sha256: string;
        entitlements: Array<string>;
        expires_at: number;
        license_id: string;
        limits: {
            [key: string]: number;
        };
        provider_id: string;
        sla_targets: {
            [key: string]: number;
        };
        support_tier: string;
        tenant_ids: Array<string>;
        usage: {
            [key: string]: number;
        };
    };
    type EntitlementStatus = "active" | "suspended";
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
    type Incident = {
        created_at: number;
        incident_id: string;
        project_id: string;
        resolved_at?: (number) | (null);
        severity: "sev1" | "sev2" | "sev3" | "sev4";
        started_at: number;
        status?: "open" | "mitigated" | "resolved";
        summary?: string;
        tenant_id: string;
        title: string;
        updated_at: number;
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
    type PortraitAssetItem = {
        asset_id: PortraitModuleId;
        depends_on_modules?: Array<PortraitModuleId>;
        maturity: PortraitModuleMaturity;
        name: string;
        next_gate: string;
        summary: string;
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
    type PortraitCompareRequest = {
        feature_space_id: string;
        left: Array<number>;
        right: Array<number>;
    };
    type PortraitCompareResponse = {
        distance: number;
        feature_space_id: string;
        matched: (boolean) | (null);
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
        feature_id: string;
        feature_space_id: string;
        identity_id: string;
        modality: "face" | "body" | "gait" | "appearance";
        project_id: string;
        quality: number;
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
        source?: "manual" | "enterprise_license" | "system";
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
    type ProvenanceEvidence = {
        development_substitutes?: Array<string>;
        generated_by?: string;
        source_sha256?: (string) | (null);
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
    type ResolveIncidentRequest = {
        summary?: string;
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
        parameters?: {
            [key: string]: unknown;
        };
        pipeline: PipelineRef;
        principal_id?: string;
        priority?: number;
        progress?: number;
        project_id: string;
        revision?: number;
        run_id: string;
        source_id?: (string) | (null);
        started_at?: (number) | (null);
        status?: RunStatus;
        tenant_id: string;
        termination_reason?: (string) | (null);
        updated_at: number;
    };
    type RunStatus = "queued" | "running" | "pausing" | "paused" | "completed" | "failed" | "cancelling" | "cancelled";
    type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";
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
    type SlaSnapshot = {
        breaches: Array<string>;
        measured_at: number;
        measurements: {
            [key: string]: number;
        };
        targets: {
            [key: string]: number;
        };
    };
    type SourceKind = "stream";
    type SupportCase = {
        case_id: string;
        created_at: number;
        created_by: string;
        description: string;
        priority: "low" | "normal" | "high" | "urgent";
        project_id: string;
        status?: "open" | "waiting" | "closed";
        subject: string;
        tenant_id: string;
        updated_at: number;
    };
    type SystemStatus = {
        auth_required: boolean;
        enterprise_policy_provider?: string;
        object_backend: string;
        production_models_required: boolean;
        profile: string;
        queue_backend: string;
        state_backend: string;
        version: string;
    };
    type TransitionModelReleaseRequest = {
        reason: string;
        status: ModelReleaseStatus;
    };
    type UpdateProductEntitlementRequest = {
        source?: "manual" | "enterprise_license" | "system";
        status: EntitlementStatus;
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
}
//# sourceMappingURL=generated.d.ts.map