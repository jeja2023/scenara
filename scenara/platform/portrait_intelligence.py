"""Builder for the Portrait Intelligence Foundation Platform contract.

This module is a pure function — it never imports ``app.*`` or
``scenara.domains.*``.  Model-capability state is injected by the caller
(server layer or test) through the ``capability_snapshot`` parameter so
that the architecture boundary enforced by ``test_architecture.py`` is
preserved.

Usage (server layer)::

    from app.portrait_model_capabilities import capability_status, production_model_ready
    from scenara.platform.portrait_intelligence import CapabilitySnapshot, build_portrait_intelligence

    snapshot: dict[str, CapabilitySnapshot] = {
        name: CapabilitySnapshot(
            readiness=capability_status(name).get("status", "not_configured"),
            production_ready=production_model_ready(name),
            current_model=capability_status(name).get("model_id"),
            target_model=capability_status(name).get("production_model"),
            embedding_dimension=capability_status(name).get("embedding_dim"),
            target_embedding_dimension=capability_status(name).get("production_embedding_dim"),
        )
        for name in PORTRAIT_CAPABILITY_IDS
    }
    status = build_portrait_intelligence(snapshot, installed_domains=["portrait"])
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypedDict

from scenara.platform.models import (
    PortraitAssetItem,
    PortraitCapabilityItem,
    PortraitCapabilityReadiness,
    PortraitIntelligenceStatus,
    PortraitModuleItem,
    PortraitModuleMaturity,
)

# 标准能力标识符，必须与 model-capabilities.yml 中的键保持同步。
PORTRAIT_CAPABILITY_IDS: tuple[str, ...] = (
    "person_detection",
    "body_embedding",
    "face_detection",
    "face_embedding",
    "pose",
    "gait",
    "appearance",
)


class CapabilitySnapshot(TypedDict, total=False):
    """Minimal capability state injected from app.portrait_model_capabilities."""

    readiness: str  # "ready" | "fallback" | "placeholder" | "not_configured"
    production_ready: bool
    current_model: str | None
    target_model: str | None
    embedding_dimension: int | None
    target_embedding_dimension: int | None


def _readiness(snapshot: CapabilitySnapshot) -> PortraitCapabilityReadiness:
    raw = snapshot.get("readiness") or "not_configured"
    try:
        return PortraitCapabilityReadiness(raw)
    except ValueError:
        return PortraitCapabilityReadiness.NOT_CONFIGURED


def _capability_item(cap_id: str, snapshot: CapabilitySnapshot) -> PortraitCapabilityItem:
    return PortraitCapabilityItem(
        capability_id=cap_id,
        readiness=_readiness(snapshot),
        production_ready=bool(snapshot.get("production_ready", False)),
        current_model=snapshot.get("current_model") or None,
        target_model=snapshot.get("target_model") or None,
        embedding_dimension=snapshot.get("embedding_dimension") or None,
        target_embedding_dimension=snapshot.get("target_embedding_dimension") or None,
    )


def build_portrait_intelligence(
    capability_snapshot: Mapping[str, CapabilitySnapshot],
    *,
    installed_domains: Iterable[str],
) -> PortraitIntelligenceStatus:
    """Return the Portrait Intelligence Foundation Platform contract.

    Parameters
    ----------
    capability_snapshot:
        A mapping from capability identifier to its current readiness state.
        Unknown keys are treated as ``not_configured``.
    installed_domains:
        The domain plug-ins currently installed in the platform runtime.
        Used to distinguish between a domain not being installed versus a
        capability that is installed but uses a fallback model.
    """
    domains = frozenset(installed_domains)
    portrait_installed = "portrait" in domains

    # -------------------------------------------------------------------
    # 能力条目
    # -------------------------------------------------------------------
    capabilities = [
        _capability_item(
            cap_id,
            capability_snapshot.get(cap_id, CapabilitySnapshot()),
        )
        for cap_id in PORTRAIT_CAPABILITY_IDS
    ]

    # -------------------------------------------------------------------
    # 用于计算模块成熟度的汇总计数
    # -------------------------------------------------------------------
    ready_count = sum(1 for c in capabilities if c.readiness == PortraitCapabilityReadiness.READY)
    total_count = len(capabilities)

    # -------------------------------------------------------------------
    # 六个战略模块
    # -------------------------------------------------------------------
    modules = [
        PortraitModuleItem(
            module_id="data_governance",
            name="Data Governance",
            maturity=PortraitModuleMaturity.SEED,
            summary=(
                "Versioned, lineage-complete portrait training and evaluation data assets "
                "using FiftyOne, LakeFS, and DVC."
            ),
            owner_repository_id="scenara-data",
            current_scope=[
                "HardSampleManifest cross-repository contract (v1.0.0)",
                "DatasetVersionReference cross-repository contract (v1.0.0)",
                "Hard-sample export with approval, authorization, and deidentification",
                "Dataset catalog and version lifecycle",
                "Asset manifest binding, quality score, and lineage summary",
            ],
            not_in_scope_yet=[
                "Data lake object management",
                "Data quality explorer and automated distribution checks",
                "FiftyOne / LakeFS / DVC integration",
                "Embedding version migration tooling",
            ],
            next_gate=(
                "Create scenara-data repository only after datasets, versions, lineage, "
                "authorization, and export have stable ownership and versioned handoff contracts."
            ),
        ),
        PortraitModuleItem(
            module_id="annotation",
            name="Annotation Platform",
            maturity=PortraitModuleMaturity.SEED,
            summary=(
                "Image, video, and stream-frame annotation and review workflows "
                "using CVAT and Label Studio, closing the hard-sample feedback loop."
            ),
            owner_repository_id="scenara-data",
            current_scope=[
                "Feedback collection API (POST /api/v1/feedback)",
                "Hard-sample approval and manifest export",
                "Tenant-scoped annotation task queue and review status",
                "Consistency score and review comment capture",
                "scenara-data consumer contract defined",
            ],
            not_in_scope_yet=[
                "CVAT / Label Studio integration",
                "Review ratio and quality gate",
                "External annotation provider synchronization",
            ],
            next_gate=(
                "Build data governance foundation first; annotation tooling belongs to "
                "the scenara-data repository lifecycle."
            ),
        ),
        PortraitModuleItem(
            module_id="training",
            name="Model Training",
            maturity=PortraitModuleMaturity.EXTERNAL,
            summary=(
                "Unified training framework covering detection, recognition, pose, ReID, "
                "and attribute tasks using OpenMMLab and PyTorch Lightning."
            ),
            owner_repository_id="scenara-model",
            current_scope=[
                "Model package admission API (POST /api/v1/model-packages/admissions)",
                "Release state machine: candidate → validated → approved → active → retired",
                "ModelDeploymentEvent audit and webhook delivery",
                "Per-tenant per-project model activation and rollback",
                "Run binding freeze at execution start",
            ],
            not_in_scope_yet=[
                "Training jobs and compute scheduling (scenara-model responsibility)",
                "Experiment tracking with MLflow (scenara-model responsibility)",
                "Multi-task shared backbone model",
                "Incremental / continual training pipeline",
            ],
            next_gate=(
                "Publish immutable model package manifests from scenara-model "
                "with SHA-256 artifact references, model cards, and evaluation evidence."
            ),
        ),
        PortraitModuleItem(
            module_id="algorithms",
            name="Portrait Algorithms",
            maturity=(PortraitModuleMaturity.PARTIAL if portrait_installed else PortraitModuleMaturity.PLANNED),
            summary=(
                "Complete portrait AI capability matrix: person detection, face detection, "
                "face embedding (ArcFace), body ReID, pose estimation (RTMPose), "
                "gait recognition, and appearance attributes."
            ),
            owner_repository_id="scenara-model",
            current_scope=[
                "person_detection — ready (YOLOv8n ONNX)",
                "body_embedding — ready (OSNet IBN 512-dim)",
                f"{ready_count}/{total_count} capabilities at production readiness",
                "Model capability routing via model-capabilities.yml",
                "Development fallback adapters for unqualified capabilities",
            ],
            not_in_scope_yet=[
                "face_detection — production SCRFD-10GF ONNX artifact required",
                "face_embedding — production ArcFace R100 ONNX artifact required",
                "pose — production RTMPose-m ONNX artifact required",
                "gait — production OpenGait / Gait3D ONNX artifact required",
                "appearance — production attribute parsing ONNX artifact required",
            ],
            next_gate=(
                f"Qualify all {total_count} capabilities: submit ONNX artifacts with "
                "SHA-256 references and model cards through the model admission API."
            ),
        ),
        PortraitModuleItem(
            module_id="vector_retrieval",
            name="Vector Retrieval",
            maturity=PortraitModuleMaturity.PARTIAL,
            summary=(
                "High-speed ANN search for portrait galleries supporting cross-camera "
                "re-identification and clustering, backed by pgvector or Qdrant."
            ),
            owner_repository_id="scenara",
            current_scope=[
                "FeatureStore protocol with cosine / L2 / inner-product metrics",
                "MemoryFeatureStore (development) and PostgresFeatureStore (production)",
                "Multi-dimensional feature spaces isolated by domain, modality, model, version",
                "Tenant-scoped IndexStore and portrait result search",
                "Cluster, association, and event records with audit trail",
                "Cross-camera Re-ID trajectory service with face + body fusion",
                "Long-term identity timeline correlation with camera topology constraints",
                "Human adjudication: confirm, reject, rename, merge, split, biometric deletion",
                "Qdrant HTTP FeatureStore adapter with tenant/project payload filters",
            ],
            not_in_scope_yet=[
                "Milvus backend for large-scale or multi-modal hybrid search",
                "Unsupervised gallery-wide clustering beyond per-run trajectory association",
                "Gait and appearance modalities in the trajectory fusion score",
                "Production Qdrant compatibility, capacity, backup/restore, and isolation qualification",
            ],
            next_gate=(
                "Qualify the Qdrant provider in a real deployment, then extend trajectory fusion "
                "beyond face and body modalities."
            ),
        ),
        PortraitModuleItem(
            module_id="mlops",
            name="MLOps",
            maturity=PortraitModuleMaturity.SEED,
            summary=(
                "End-to-end model lifecycle governance from experiment through admission, "
                "deployment, monitoring, and feedback, with Triton and Kubernetes for scale."
            ),
            owner_repository_id="scenara",
            current_scope=[
                "Model release state machine with deployment event audit",
                "Webhook delivery of deployment state changes to scenara-model",
                "Per-tenant/project model activation and rollback",
                "Per-model latency, error-rate, throughput, and quality metric points",
                "p95 health snapshot and degradation/rollback recommendation",
                "Fail-closed production configuration checks (scenara/settings.py)",
                "Provider-neutral inference boundary and deployment health evidence",
                "Triton HTTP inference adapter and MLflow ModelPackageManifest tracking boundary",
                "Thresholded automatic rollback endpoint with retired-release selection",
            ],
            not_in_scope_yet=[
                "Production Triton/MLflow/Kubernetes compatibility and capacity qualification",
                "Automatic rollback orchestration from external alert managers",
            ],
            next_gate=(
                "Qualify 1.0 with ONNXRuntime single-node baseline and target GPU evidence; "
                "then qualify Triton/MLflow/Kubernetes providers for 1.1 concurrency and operations."
            ),
        ),
    ]

    # -------------------------------------------------------------------
    # 三项战略资产
    # -------------------------------------------------------------------
    assets = [
        PortraitAssetItem(
            asset_id="data_lake",
            name="Portrait Data Lake",
            maturity=PortraitModuleMaturity.PLANNED,
            summary=(
                "Unified management of raw media, annotations, embeddings, quality labels, "
                "and version lineage for all portrait AI training and evaluation."
            ),
            depends_on_modules=["data_governance", "annotation"],
            next_gate=(
                "Build data governance and annotation tooling first; "
                "data lake emerges from stable dataset versioning and lineage ownership."
            ),
        ),
        PortraitAssetItem(
            asset_id="foundation_model",
            name="Portrait Foundation Model",
            maturity=PortraitModuleMaturity.PLANNED,
            summary=(
                "A continuously trained multi-task model covering detection, face recognition, "
                "attributes, pose, ReID, and gait — replacing multiple isolated task models."
            ),
            depends_on_modules=["algorithms", "training", "data_governance"],
            next_gate=(
                "First qualify all seven independent task models (algorithms module); "
                "then converge toward a shared backbone in the 1.x cycle."
            ),
        ),
        PortraitAssetItem(
            asset_id="intelligence_engine",
            name="Portrait Intelligence Engine",
            maturity=PortraitModuleMaturity.PARTIAL,
            summary=(
                "Fuses retrieval, clustering, knowledge graph, event analysis, and "
                "continual learning into a self-improving platform capability."
            ),
            depends_on_modules=["algorithms", "vector_retrieval", "mlops"],
            next_gate=(
                "Multi-modal fusion (face + body) shipped in the cross-camera trajectory "
                "service; next qualify the Qdrant provider and extend fusion to gait and appearance."
            ),
        ),
    ]

    return PortraitIntelligenceStatus(
        modules=modules,
        assets=assets,
        capabilities=capabilities,
    )


__all__ = [
    "PORTRAIT_CAPABILITY_IDS",
    "CapabilitySnapshot",
    "build_portrait_intelligence",
]
