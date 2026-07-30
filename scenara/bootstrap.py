from __future__ import annotations

from dataclasses import dataclass

from scenara.domains.ocr import OcrPlugin
from scenara.domains.ocr.factory import load_ocr_engine
from scenara.domains.ocr.operators import OcrEngine
from scenara.domains.portrait import PortraitPlugin
from scenara.domains.portrait.analysis import PortraitAnalysisBackend
from scenara.domains.portrait.service import MemoryPortraitRepository, PortraitRepository, PortraitService
from scenara.enterprise.license import EnterprisePolicyProvider, load_verified_license
from scenara.enterprise.service import (
    EnterpriseRepository,
    EnterpriseService,
    MemoryEnterpriseRepository,
)
from scenara.infrastructure.memory_state import MemoryStateStore
from scenara.infrastructure.object_store import LocalObjectStore, S3ObjectStore
from scenara.infrastructure.postgres_enterprise import PostgresEnterpriseRepository
from scenara.infrastructure.postgres_features import PostgresFeatureStore
from scenara.infrastructure.postgres_feedback import PostgresFeedbackRepository
from scenara.infrastructure.postgres_portrait import PostgresPortraitRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.queue import InlineRunQueue, RedisRunQueue
from scenara.platform.audit import AuditLogger
from scenara.platform.features import FeatureStore, MemoryFeatureStore
from scenara.platform.feedback import FeedbackRepository, FeedbackService, MemoryFeedbackRepository
from scenara.platform.media import DecodeImageOperator
from scenara.platform.media_batch import DecodeMediaOperator
from scenara.platform.model_runtime import ModelRegistry
from scenara.platform.objects import ObjectStore
from scenara.platform.pipeline import PipelineRegistry
from scenara.platform.plugins import DomainPluginRegistry
from scenara.platform.policy import DenyUnavailablePolicyProvider, DevelopmentPolicyProvider, PolicyProvider
from scenara.platform.queue import RunQueue
from scenara.platform.secrets import EncryptedObjectSecretStore, MemorySecretStore, SecretStore
from scenara.platform.services import RunService
from scenara.platform.store import StateStore
from scenara.platform.webhook_service import WebhookService
from scenara.settings import Settings, load_settings


@dataclass(slots=True)
class Runtime:
    settings: Settings
    features: FeatureStore
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
    enterprise: EnterpriseService | None

    async def open(self) -> None:
        await self.state.open()
        await self.runs.sync_pipeline_catalog()
        await self.objects.open()
        await self.queue.open()

    async def close(self) -> None:
        await self.queue.close()
        await self.models.close()
        await self.objects.close()
        await self.state.close()

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
    if settings.state_backend == "postgres":
        postgres_state = PostgresStateStore(settings.postgres_dsn)
        state: StateStore = postgres_state
        features: FeatureStore = PostgresFeatureStore(postgres_state.pool)
        portrait_repository: PortraitRepository = PostgresPortraitRepository(postgres_state.pool)
        enterprise_repository: EnterpriseRepository = PostgresEnterpriseRepository(postgres_state.pool)
        feedback_repository: FeedbackRepository = PostgresFeedbackRepository(postgres_state.pool)
    elif settings.state_backend == "memory":
        state = MemoryStateStore()
        features = MemoryFeatureStore()
        portrait_repository = MemoryPortraitRepository()
        enterprise_repository = MemoryEnterpriseRepository()
        feedback_repository = MemoryFeedbackRepository()
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
    portrait = PortraitService(portrait_repository, features, policy, audit)
    models = ModelRegistry(production=settings.production, catalog=state)
    webhooks = WebhookService(
        state=state,
        secrets=secrets,
        audit=audit,
        policy=policy,
        allow_private_targets=settings.allow_private_webhook_targets,
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
    )
    feedback = FeedbackService(feedback_repository, state, state, objects, policy, audit)
    return Runtime(
        settings=settings,
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
        secrets=secrets,
        audit=audit,
        policy=policy,
        portrait=portrait,
        enterprise=enterprise,
    )


__all__ = ["Runtime", "build_runtime"]
