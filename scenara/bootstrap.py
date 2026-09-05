from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass

from scenara.domains.ocr import OcrPlugin
from scenara.domains.ocr.factory import load_ocr_engine
from scenara.domains.ocr.operators import OcrEngine
from scenara.domains.behavior import BehaviorPlugin
from scenara.domains.behavior.factory import load_behavior_engine
from scenara.domains.behavior.operators import BehaviorEngine
from scenara.domains.fashion import FashionPlugin
from scenara.domains.fashion.factory import load_fashion_engine
from scenara.domains.fashion.operators import FashionEngine
from scenara.domains.portrait import PortraitPlugin
from scenara.domains.portrait.analysis import PortraitAnalysisBackend
from scenara.domains.portrait.encoder import RuntimePortraitImageEncoder
from scenara.domains.portrait.service import MemoryPortraitRepository, PortraitRepository, PortraitService
from scenara.domains.portrait.surveillance import SurveillanceService
from scenara.domains.portrait.trajectory import (
    MemoryTrajectoryRepository,
    TrajectoryRegistrar,
    TrajectoryRepository,
    TrajectoryService,
)
from scenara.enterprise.license import EnterprisePolicyProvider, load_verified_license
from scenara.enterprise.service import (
    EnterpriseRepository,
    EnterpriseService,
    MemoryEnterpriseRepository,
)
from scenara.infrastructure.memory_state import MemoryStateStore
from scenara.infrastructure.object_store import LocalObjectStore, S3ObjectStore
from scenara.infrastructure.postgres_access import PostgresAccessRepository
from scenara.infrastructure.postgres_control_plane import PostgresControlPlaneStore
from scenara.infrastructure.postgres_enterprise import PostgresEnterpriseRepository
from scenara.infrastructure.postgres_features import PostgresFeatureStore
from scenara.infrastructure.qdrant_features import QdrantFeatureStore
from scenara.infrastructure.postgres_feedback import PostgresFeedbackRepository
from scenara.infrastructure.postgres_index import PostgresIndexStore
from scenara.infrastructure.postgres_portrait import PostgresPortraitRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.postgres_surveillance import PostgresSurveillanceRepository
from scenara.infrastructure.postgres_trajectory import PostgresTrajectoryRepository
from scenara.infrastructure.memory_surveillance import MemorySurveillanceRepository
from scenara.infrastructure.queue import InlineRunQueue, RedisRunQueue
from scenara.platform.access import AccessRepository, AccessService, MemoryAccessRepository
from scenara.platform.audit import AuditLogger
from scenara.platform.control_plane import ControlPlaneService
from scenara.platform.control_plane_store import ControlPlaneStore, MemoryControlPlaneStore
from scenara.platform.data_platform import DataPlatformClient, HttpDataPlatformClient, LocalDataPlatformAdapter
from scenara.platform.dataset import DatasetService
from scenara.platform.features import FeatureStore, MemoryFeatureStore
from scenara.platform.feedback import FeedbackRepository, FeedbackService, MemoryFeedbackRepository
from scenara.platform.index import IndexStore, MemoryIndexStore
from scenara.platform.media import DecodeImageOperator
from scenara.platform.media_batch import DecodeMediaOperator
from scenara.platform.model_runtime import ModelRegistry
from scenara.platform.observability import SurveillanceMetrics
from scenara.platform.objects import ObjectStore
from scenara.platform.pipeline import PipelineRegistry
from scenara.platform.plugins import DomainPluginRegistry
from scenara.platform.policy import DevelopmentPolicyProvider, LocalPolicyProvider, PolicyProvider
from scenara.platform.queue import RunQueue
from scenara.platform.search import SearchService
from scenara.platform.secrets import EncryptedObjectSecretStore, MemorySecretStore, SecretStore
from scenara.platform.services import RunService
from scenara.platform.store import StateStore
from scenara.platform.surveillance import SurveillanceRepository
from scenara.platform.webhook_service import WebhookService
from scenara.settings import Settings, load_settings


logger = logging.getLogger(__name__)

@dataclass(slots=True)
class Runtime:
    settings: Settings
    access: AccessService
    features: FeatureStore
    indexes: IndexStore
    secrets: SecretStore
    audit: AuditLogger
    policy: PolicyProvider
    state: StateStore
    objects: ObjectStore
    queue: RunQueue
    models: ModelRegistry
    pipelines: PipelineRegistry
    plugins: DomainPluginRegistry
    runs: RunService
    webhooks: WebhookService
    feedback: FeedbackService
    portrait: PortraitService
    trajectory: TrajectoryService
    surveillance: SurveillanceService
    surveillance_metrics: SurveillanceMetrics
    search: SearchService
    data: DataPlatformClient
    control_plane: ControlPlaneService
    enterprise: EnterpriseService | None
    _session_cleanup_task: asyncio.Task[None] | None = None

    async def open(self) -> None:
        await self.state.open()
        await self.access.ensure_bootstrap_admin(
            tenant_id=self.settings.default_tenant_id,
            project_id=self.settings.default_project_id,
            username=self.settings.bootstrap_admin_username,
            password=self.settings.bootstrap_admin_password,
        )
        await self.runs.sync_pipeline_catalog()
        await self.objects.open()
        await self.queue.open()
        if isinstance(self.queue, InlineRunQueue):
            for run in await self.state.recoverable_runs():
                await self.queue.enqueue(run)
        self._session_cleanup_task = asyncio.create_task(self._session_cleanup_loop())

    async def close(self) -> None:
        if self._session_cleanup_task is not None:
            self._session_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._session_cleanup_task
            self._session_cleanup_task = None
        await self.queue.close()
        await self.data.close()
        await self.models.close()
        close_features = getattr(self.features, "close", None)
        if close_features is not None:
            await close_features()
        await self.objects.close()
        await self.state.close()

    async def _session_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(3_600)
            try:
                await self.control_plane.purge_expired_sessions(time.time())
            except Exception:
                # 会话清理采用尽力而为策略；即使控制面数据库短暂离线，
                # 认证功能也必须保持可用。持续失败会让过期会话堆积，
                # 所以要留下痕迹而不是完全静默。
                logger.warning("过期会话清理失败，将在下一轮重试", exc_info=True)
                continue

    async def health_check(self) -> dict[str, str]:
        await self.state.health_check()
        await self.objects.health_check()
        await self.queue.health_check()
        return {"state": "ok", "objects": "ok", "queue": "ok"}


def build_runtime(
    settings: Settings | None = None,
    *,
    ocr_engine: OcrEngine | None = None,
    behavior_engine: BehaviorEngine | None = None,
    fashion_engine: FashionEngine | None = None,
    portrait_backend: PortraitAnalysisBackend | None = None,
) -> Runtime:
    settings = settings or load_settings()
    if ocr_engine is None and settings.ocr_engine_factory:
        ocr_engine = load_ocr_engine(settings.ocr_engine_factory)
    if behavior_engine is None and settings.behavior_engine_factory:
        behavior_engine = load_behavior_engine(settings.behavior_engine_factory)
    if fashion_engine is None and settings.fashion_engine_factory:
        fashion_engine = load_fashion_engine(settings.fashion_engine_factory)
    control_plane_store: ControlPlaneStore
    if settings.state_backend == "postgres":
        postgres_state = PostgresStateStore(
            settings.postgres_dsn,
            min_size=settings.postgres_pool_min_size,
            max_size=settings.postgres_pool_max_size,
        )
        state: StateStore = postgres_state
        access_repository: AccessRepository = PostgresAccessRepository(postgres_state.pool)
        features: FeatureStore = (
            QdrantFeatureStore(
                settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout_seconds=settings.qdrant_timeout_seconds,
                collection_prefix=settings.qdrant_collection_prefix,
            )
            if settings.qdrant_url
            else PostgresFeatureStore(postgres_state.pool)
        )
        indexes: IndexStore = PostgresIndexStore(postgres_state.pool)
        portrait_repository: PortraitRepository = PostgresPortraitRepository(postgres_state.pool)
        enterprise_repository: EnterpriseRepository = PostgresEnterpriseRepository(postgres_state.pool)
        feedback_repository: FeedbackRepository = PostgresFeedbackRepository(postgres_state.pool)
        control_plane_store = PostgresControlPlaneStore(postgres_state.pool)
        trajectory_repository: TrajectoryRepository = PostgresTrajectoryRepository(postgres_state.pool)
        surveillance_repository: SurveillanceRepository = PostgresSurveillanceRepository(postgres_state.pool)
    elif settings.state_backend == "memory":
        state = MemoryStateStore()
        access_repository = MemoryAccessRepository()
        features = MemoryFeatureStore()
        indexes = MemoryIndexStore()
        portrait_repository = MemoryPortraitRepository()
        enterprise_repository = MemoryEnterpriseRepository()
        feedback_repository = MemoryFeedbackRepository()
        control_plane_store = MemoryControlPlaneStore()
        trajectory_repository = MemoryTrajectoryRepository()
        surveillance_repository = MemorySurveillanceRepository()
    else:
        raise RuntimeError(f"unsupported state backend: {settings.state_backend}")

    if settings.object_backend == "s3":
        objects: ObjectStore = S3ObjectStore(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            public_endpoint_url=settings.s3_public_endpoint_url,
            region=settings.s3_region,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            session_token=settings.s3_session_token,
            verify_tls=settings.s3_verify_tls,
            ca_bundle=settings.s3_ca_bundle,
            server_side_encryption=settings.s3_server_side_encryption,
            kms_key_id=settings.s3_kms_key_id,
            multipart_threshold_bytes=settings.s3_multipart_threshold_bytes,
            multipart_chunk_bytes=settings.s3_multipart_chunk_bytes,
            lifecycle_enabled=settings.s3_lifecycle_enabled,
            raw_media_retention_days=settings.raw_media_retention_days,
            preview_retention_days=settings.preview_retention_days,
            structured_result_retention_days=settings.structured_result_retention_days,
            addressing_style=settings.s3_addressing_style,
        )
    else:
        objects = LocalObjectStore(settings.data_dir / "objects")

    if settings.secret_encryption_key:
        secrets: SecretStore = EncryptedObjectSecretStore(objects, settings.secret_encryption_key)
    else:
        secrets = MemorySecretStore()
    audit = AuditLogger(state)
    enterprise: EnterpriseService | None = None
    license_path = settings.enterprise_license_path
    public_key_path = settings.enterprise_public_key_path
    if (license_path is None) != (public_key_path is None):
        raise RuntimeError("enterprise license and public key paths must be configured together")
    if license_path is not None and public_key_path is not None:
        verified_license = load_verified_license(license_path, public_key_path)
        enterprise_policy = EnterprisePolicyProvider(verified_license, enterprise_repository)
        policy: PolicyProvider = enterprise_policy
        enterprise = EnterpriseService(enterprise_policy, enterprise_repository, audit)
    elif settings.enterprise_policy_required:
        # Kept as a compatibility flag; self-hosted production uses local scoped policy.
        policy = LocalPolicyProvider()
    elif settings.production:
        policy = LocalPolicyProvider()
    else:
        policy = DevelopmentPolicyProvider()

    if settings.queue_backend == "redis":
        queue: RunQueue = RedisRunQueue(settings.redis_url)
    elif settings.queue_backend == "inline":
        queue = InlineRunQueue()
    else:
        raise RuntimeError(f"unsupported queue backend: {settings.queue_backend}")

    pipelines = PipelineRegistry()
    pipelines.register_operator(DecodeImageOperator())
    pipelines.register_operator(DecodeMediaOperator())
    plugins = DomainPluginRegistry(pipelines)
    plugins.register(PortraitPlugin(portrait_backend))
    plugins.register(OcrPlugin(ocr_engine))
    plugins.register(BehaviorPlugin(behavior_engine))
    plugins.register(FashionPlugin(fashion_engine))
    portrait_encoder = RuntimePortraitImageEncoder(production=settings.production)
    portrait = PortraitService(
        portrait_repository,
        features,
        policy,
        audit,
        indexes=indexes,
        encoder=portrait_encoder,
    )
    trajectory = TrajectoryService(
        trajectory_repository,
        features,
        policy,
        audit,
        body_threshold=settings.trajectory_body_threshold,
        face_threshold=settings.trajectory_face_threshold,
        min_track_quality=settings.trajectory_min_track_quality,
        min_frame_count=settings.trajectory_min_frame_count,
        max_templates=settings.trajectory_max_templates,
        default_transition_seconds=settings.trajectory_default_transition_seconds,
    )
    surveillance_metrics = SurveillanceMetrics()
    surveillance = SurveillanceService(
        repository=surveillance_repository,
        features=features,
        portraits=portrait_repository,
        trajectory=trajectory,
        state=state,
        policy=policy,
        audit=audit,
        alert_snapshot_retention_days=settings.surveillance_alert_snapshot_retention_days,
        metrics=surveillance_metrics,
    )
    search = SearchService(
        indexes=indexes,
        state=state,
        policy=policy,
        audit=audit,
        encoder=portrait_encoder,
        objects=objects,
    )
    models = ModelRegistry(production=settings.production, catalog=state)
    webhooks = WebhookService(
        state=state,
        secrets=secrets,
        audit=audit,
        policy=policy,
        allow_private_targets=settings.allow_private_webhook_targets,
    )
    feedback = FeedbackService(
        feedback_repository,
        state,
        state,
        objects,
        policy,
        audit,
        plugins.qualification_evidence_type,
    )
    runs = RunService(
        state=state,
        objects=objects,
        queue=queue,
        pipelines=pipelines,
        secrets=secrets,
        audit=audit,
        policy=policy,
        max_image_bytes=settings.max_image_bytes,
        max_media_bytes=settings.max_media_bytes,
        media_sample_interval_ms=settings.media_sample_interval_ms,
        stream_segment_duration_ms=settings.stream_segment_duration_ms,
        result_shard_units=settings.result_shard_units,
        raw_media_retention_days=settings.raw_media_retention_days,
        preview_retention_days=settings.preview_retention_days,
        structured_result_retention_days=settings.structured_result_retention_days,
        production=settings.production,
        allow_private_media_sources=settings.allow_private_media_sources,
        active_model_resolver=feedback,
        run_artifacts_enabled=settings.run_artifacts_enabled,
        run_artifact_crop_max_edge=settings.run_artifact_crop_max_edge,
        run_artifact_frame_max_edge=settings.run_artifact_frame_max_edge,
        indexes=indexes,
        registrars=([TrajectoryRegistrar(trajectory)] if settings.trajectory_enabled else []),
        observation_evaluators=(surveillance,),
    )
    surveillance.bind_run_service(runs)
    access = AccessService(access_repository, audit, policy)
    control_plane = ControlPlaneService(
        control_plane_store, policy, audit, indexes=indexes, access=access, audit_store=state
    )
    local_data = LocalDataPlatformAdapter(DatasetService(state, policy, audit), control_plane)
    data: DataPlatformClient
    if settings.data_platform_mode == "http":
        data = HttpDataPlatformClient(
            settings.data_platform_url,
            service_token=settings.data_platform_service_token,
            timeout_seconds=settings.data_platform_timeout_seconds,
            max_retries=settings.data_platform_max_retries,
            source_assets=state,
            source_bucket=settings.s3_bucket,
        )
    else:
        data = local_data
    search.profile_resolver = control_plane
    return Runtime(
        settings=settings,
        access=access,
        state=state,
        objects=objects,
        queue=queue,
        models=models,
        pipelines=pipelines,
        plugins=plugins,
        runs=runs,
        webhooks=webhooks,
        feedback=feedback,
        features=features,
        indexes=indexes,
        secrets=secrets,
        audit=audit,
        policy=policy,
        portrait=portrait,
        trajectory=trajectory,
        surveillance=surveillance,
        surveillance_metrics=surveillance_metrics,
        search=search,
        data=data,
        control_plane=control_plane,
        enterprise=enterprise,
    )


__all__ = ["Runtime", "build_runtime"]
