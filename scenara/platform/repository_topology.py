from __future__ import annotations

from scenara.platform.models import (
    RepositoryBoundaryRule,
    RepositoryContractTransport,
    RepositoryIntegrationContract,
    RepositoryKind,
    RepositoryLifecycle,
    RepositoryTopology,
    RepositoryTopologyItem,
)


def build_repository_topology() -> RepositoryTopology:
    return RepositoryTopology(
        current_repository_id="scenara",
        repositories=[
            RepositoryTopologyItem(
                repository_id="scenara",
                name="Scenara",
                kind=RepositoryKind.PLATFORM_INTEGRATION,
                lifecycle=RepositoryLifecycle.CURRENT,
                current_repository=True,
                primary_product_ids=[
                    "parse",
                    "console",
                    "api",
                    "sdk",
                    "index",
                    "search",
                    "flow",
                    "edge",
                    "agent",
                ],
                integration_product_ids=["model", "data"],
                responsibilities=[
                    "platform_runtime",
                    "media_and_run_lifecycle",
                    "visual_domain_plugins",
                    "pipeline_execution",
                    "shared_console",
                    "shared_open_api",
                    "shared_sdks",
                    "shared_iam_authorization_and_audit",
                    "shared_product_catalog",
                    "model_admission_release_and_deployment",
                    "operational_feedback_and_hard_sample_export",
                ],
                excluded_responsibilities=[
                    "model_training_jobs",
                    "experiment_tracking",
                    "training_compute_scheduling",
                    "dataset_catalog_and_versioning",
                    "data_labeling_and_review",
                    "dataset_quality_and_lineage",
                ],
                next_gate=(
                    "Keep the shared platform contract stable; extract only independently owned workloads "
                    "with versioned integration contracts."
                ),
            ),
            RepositoryTopologyItem(
                repository_id="scenara-model",
                name="Scenara Model",
                kind=RepositoryKind.SPECIALIZED_PRODUCT,
                lifecycle=RepositoryLifecycle.EXTERNAL_EXISTING,
                primary_product_ids=["model"],
                integration_product_ids=["data", "console", "api", "sdk"],
                responsibilities=[
                    "model_training_jobs",
                    "experiment_tracking",
                    "training_compute_scheduling",
                    "training_evaluation",
                    "immutable_model_artifact_generation",
                ],
                excluded_responsibilities=[
                    "shared_iam_authorization_and_audit",
                    "shared_console",
                    "shared_open_api",
                    "shared_sdks",
                    "model_admission_release_and_deployment",
                ],
                next_gate=(
                    "Publish immutable model package manifests and evidence that the Scenara platform can "
                    "admit, release, deploy, and roll back."
                ),
            ),
            RepositoryTopologyItem(
                repository_id="scenara-data",
                name="Scenara Data",
                kind=RepositoryKind.SPECIALIZED_PRODUCT,
                lifecycle=RepositoryLifecycle.EXTERNAL_EXISTING,
                primary_product_ids=["data"],
                integration_product_ids=["model", "console", "api", "sdk"],
                responsibilities=[
                    "dataset_catalog_and_versioning",
                    "data_labeling_and_review",
                    "dataset_quality_and_lineage",
                    "dataset_authorization_and_export",
                ],
                excluded_responsibilities=[
                    "operational_media_run_and_result_storage",
                    "model_training_jobs",
                    "shared_iam_authorization_and_audit",
                ],
                next_gate=(
                    "Complete data migration shadow verification, immutable dataset version digests, and "
                    "cutover evidence before accepting production traffic."
                ),
            ),
        ],
        integration_contracts=[
            RepositoryIntegrationContract(
                contract_id="model-package-admission",
                producer_repository_id="scenara-model",
                consumer_repository_id="scenara",
                transport=RepositoryContractTransport.IMMUTABLE_MANIFEST,
                payload_type="ModelPackageManifest",
                release_version="1.0.0",
                schema_path="contracts/repository/v1.0.0/model-package-admission.schema.json",
                invariants=[
                    "sha256_digest_required",
                    "model_card_required",
                    "license_metadata_required",
                    "evaluation_evidence_required",
                    "immutable_artifact_reference_required",
                ],
            ),
            RepositoryIntegrationContract(
                contract_id="hard-sample-handoff",
                producer_repository_id="scenara",
                consumer_repository_id="scenara-data",
                transport=RepositoryContractTransport.IMMUTABLE_MANIFEST,
                payload_type="HardSampleManifest",
                release_version="1.0.0",
                schema_path="contracts/repository/v1.0.0/hard-sample-handoff.schema.json",
                invariants=[
                    "approved_feedback_only",
                    "authorized_export_required",
                    "deidentification_required",
                    "content_digest_required",
                ],
            ),
            RepositoryIntegrationContract(
                contract_id="dataset-version-input",
                producer_repository_id="scenara-data",
                consumer_repository_id="scenara-model",
                transport=RepositoryContractTransport.VERSIONED_API,
                payload_type="DatasetVersionReference",
                release_version="1.0.0",
                schema_path="contracts/repository/v1.0.0/dataset-version-input.schema.json",
                invariants=[
                    "immutable_dataset_version_required",
                    "lineage_required",
                    "authorization_required",
                ],
            ),
            RepositoryIntegrationContract(
                contract_id="deployment-feedback",
                producer_repository_id="scenara",
                consumer_repository_id="scenara-model",
                transport=RepositoryContractTransport.EVENT,
                payload_type="ModelDeploymentEvent",
                release_version="1.0.0",
                schema_path="contracts/repository/v1.0.0/deployment-feedback.schema.json",
                invariants=[
                    "versioned_schema_required",
                    "tenant_project_scope_required",
                    "audit_trace_required",
                ],
            ),
        ],
        boundary_rules=[
            RepositoryBoundaryRule.VERSIONED_CONTRACTS_ONLY,
            RepositoryBoundaryRule.NO_SHARED_DATABASE,
            RepositoryBoundaryRule.NO_CROSS_REPOSITORY_SOURCE_IMPORTS,
            RepositoryBoundaryRule.IMMUTABLE_ARTIFACT_REFERENCES,
        ],
    )
