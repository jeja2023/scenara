from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass

from scenara.domains.ocr import OcrPlugin
from scenara.domains.ocr.factory import load_ocr_engine
from scenara.domains.ocr.operators import OcrEngine
from scenara.domains.portrait import PortraitPlugin
from scenara.domains.portrait.analysis import PortraitAnalysisBackend
from scenara.domains.portrait.encoder import RuntimePortraitImageEncoder
from scenara.domains.portrait.service import MemoryPortraitRepository, PortraitRepository, PortraitService
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
from scenara.infrastructure.postgres_feedback import PostgresFeedbackRepository
from scenara.infrastructure.postgres_index import PostgresIndexStore
from scenara.infrastructure.postgres_portrait import PostgresPortraitRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.postgres_trajectory import PostgresTrajectoryRepository
from scenara.infrastructure.queue import InlineRunQueue, RedisRunQueue
from scenara.platform.access import AccessRepository, AccessService, MemoryAccessRepository
from scenara.platform.audit import AuditLogger
from scenara.platform.control_plane import ControlPlaneService
from scenara.platform.control_plane_store import ControlPlaneStore, MemoryControlPlaneStore
from scenara.platform.dataset import DatasetService
from scenara.platform.features import FeatureStore, MemoryFeatureStore
from scenara.platform.feedback import FeedbackRepository, FeedbackService, MemoryFeedbackRepository
from scenara.platform.index import IndexStore, MemoryIndexStore
from scenara.platform.media import DecodeImageOperator
from scenara.platform.media_batch import DecodeMediaOperator
from scenara.platform.model_runtime import ModelRegistry
from scenara.platform.objects import ObjectStore
from scenara.platform.pipeline import PipelineRegistry
from scenara.platform.plugins import DomainPluginRegistry
from scenara.platform.policy import DenyUnavailablePolicyProvider, DevelopmentPolicyProvider, PolicyProvider
from scenara.platform.queue import RunQueue
from scenara.platform.search import SearchService
from scenara.platform.secrets import EncryptedObjectSecretStore, MemorySecretStore, SecretStore
from scenara.platform.services import RunService
from scenara.platform.store import StateStore
from scenara.platform.webhook_service import WebhookService
from scenara.settings import Settings, load_settings


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
    search: SearchService
    datasets: DatasetService
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
        await self.models.close()
        await self.objects.close()
        await self.state.close()

    async def _session_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(3_600)
            try:
                await self.control_plane.purge_expired_sessions(time.time())
            except Exception:
                # 会话清理采用尽力而为策略；即使控制面数据库短暂离线，
                # 认证功能也必须保持可用。
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
    portrait_backend: PortraitAnalysisBackend | None = None,
) -> Runtime:
    settings = settings or load_settings()
    if ocr_engine is None and settings.ocr_engine_factory:
        ocr_engine = load_ocr_engine(settings.ocr_engine_factory)
    control_plane_store: ControlPlaneStore
    if settings.state_backend == "postgres":
        postgres_state = PostgresStateStore(settings.postgres_dsn)
        state: StateStore = postgres_state
        access_repository: AccessRepository = PostgresAccessRepository(postgres_state.pool)
        features: FeatureStore = PostgresFeatureStore(postgres_state.pool)
        indexes: IndexStore = PostgresIndexStore(postgres_state.pool)
        portrait_repository: PortraitRepository = PostgresPortraitRepository(postgres_state.pool)
        enterprise_repository: EnterpriseRepository = PostgresEnterpriseRepository(postgres_state.pool)
        feedback_repository: FeedbackRepository = PostgresFeedbackRepository(postgres_state.pool)
        control_plane_store = PostgresControlPlaneStore(postgres_state.pool)
        trajectory_repository: TrajectoryRepository = PostgresTrajectoryRepository(postgres_state.pool)
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
    else:
        raise RuntimeError(f"unsupported state backend: {settings.state_backend}")

    if settings.object_backend == "s3":
        objects: ObjectStore = S3ObjectStore(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
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
        policy = DenyUnavailablePolicyProvider()
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
    search = SearchService(
        indexes=indexes,
        state=state,
        policy=policy,
        audit=audit,
        encoder=portrait_encoder,
        objects=objects,
    )
    datasets = DatasetService(state, policy, audit)
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
        max_media_units=settings.max_media_units,
        media_sample_interval_ms=settings.media_sample_interval_ms,
        result_shard_units=settings.result_shard_units,
        raw_media_retention_days=settings.raw_media_retention_days,
        preview_retention_days=settings.preview_retention_days,
        structured_result_retention_days=settings.structured_result_retention_days,
        production=settings.production,
        allow_private_media_sources=settings.allow_private_media_sources,
        active_model_resolver=feedback,
        run_artifacts_enabled=settings.run_artifacts_enabled,
        run_artifact_max_crops=settings.run_artifact_max_crops,
        run_artifact_max_frames=settings.run_artifact_max_frames,
        run_artifact_crop_max_edge=settings.run_artifact_crop_max_edge,
        run_artifact_frame_max_edge=settings.run_artifact_frame_max_edge,
        indexes=indexes,
        registrars=([TrajectoryRegistrar(trajectory)] if settings.trajectory_enabled else []),
    )
    access = AccessService(access_repository, audit, policy)
    control_plane = ControlPlaneService(
        control_plane_store, policy, audit, indexes=indexes, access=access, audit_store=state
    )
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
        search=search,
        datasets=datasets,
        control_plane=control_plane,
        enterprise=enterprise,
    )


__all__ = ["Runtime", "build_runtime"]
