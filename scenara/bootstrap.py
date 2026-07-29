from __future__ import annotations

from dataclasses import dataclass

from scenara.domains.ocr import OcrPlugin
from scenara.domains.ocr.operators import OcrEngine
from scenara.domains.portrait import PortraitPlugin
from scenara.infrastructure.memory_state import MemoryStateStore
from scenara.infrastructure.object_store import LocalObjectStore, S3ObjectStore
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.queue import InlineRunQueue, RedisRunQueue
from scenara.platform.media import DecodeImageOperator
from scenara.platform.objects import ObjectStore
from scenara.platform.pipeline import PipelineRegistry
from scenara.platform.plugins import DomainPluginRegistry
from scenara.platform.queue import RunQueue
from scenara.platform.services import RunService
from scenara.platform.store import StateStore
from scenara.settings import Settings, load_settings


@dataclass(slots=True)
class Runtime:
    settings: Settings
    state: StateStore
    objects: ObjectStore
    queue: RunQueue
    pipelines: PipelineRegistry
    plugins: DomainPluginRegistry
    runs: RunService

    async def open(self) -> None:
        await self.state.open()
        await self.objects.open()
        await self.queue.open()

    async def close(self) -> None:
        await self.queue.close()
        await self.objects.close()
        await self.state.close()


def build_runtime(settings: Settings | None = None, *, ocr_engine: OcrEngine | None = None) -> Runtime:
    settings = settings or load_settings()
    if settings.state_backend == "postgres":
        state: StateStore = PostgresStateStore(settings.postgres_dsn)
    elif settings.state_backend == "memory":
        state = MemoryStateStore()
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
    if settings.queue_backend == "redis":
        queue: RunQueue = RedisRunQueue(settings.redis_url)
    elif settings.queue_backend == "inline":
        queue = InlineRunQueue()
    else:
        raise RuntimeError(f"unsupported queue backend: {settings.queue_backend}")
    pipelines = PipelineRegistry()
    pipelines.register_operator(DecodeImageOperator())
    plugins = DomainPluginRegistry(pipelines)
    plugins.register(PortraitPlugin())
    plugins.register(OcrPlugin(ocr_engine))
    runs = RunService(
        state=state,
        objects=objects,
        queue=queue,
        pipelines=pipelines,
        max_image_bytes=settings.max_image_bytes,
    )
    return Runtime(
        settings=settings,
        state=state,
        objects=objects,
        queue=queue,
        pipelines=pipelines,
        plugins=plugins,
        runs=runs,
    )


__all__ = ["Runtime", "build_runtime"]
