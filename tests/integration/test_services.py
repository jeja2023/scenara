from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import uuid4

import pytest
import pytest_asyncio
import httpx
from PIL import Image
from io import BytesIO

from scenara.infrastructure.object_store import S3ObjectStore
from scenara.bootstrap import build_runtime
from scenara.server import create_app
from scenara.infrastructure.postgres_features import PostgresFeatureStore
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.queue import RedisRunQueue
from scenara.platform.features import DistanceMetric, FeatureRecord, FeatureSpace
from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import (
    MediaAsset,
    MediaKind,
    ObjectRetentionRecord,
    PipelineRef,
    PipelineStatus,
    ResultReference,
    RunEvent,
    RunRecord,
    RunStatus,
    WebhookSubscription,
)
from scenara.platform.pipeline import PipelineDefinition, PipelineNode
from scenara.queue_recovery import rebuild_redis_run_queue
from scenara.platform.store import StateConflict
from tests.object_store_contract import assert_object_store_contract

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

POSTGRES_DSN = os.getenv(
    "SCENARA_INTEGRATION_POSTGRES_DSN",
    "postgresql://scenara:scenara-integration@127.0.0.1:55432/scenara",
)
REDIS_URL = os.getenv("SCENARA_INTEGRATION_REDIS_URL", "redis://127.0.0.1:56379/15")
S3_ENDPOINT = os.getenv("SCENARA_INTEGRATION_S3_ENDPOINT", "http://127.0.0.1:59000")
S3_ACCESS_KEY = os.getenv("SCENARA_INTEGRATION_S3_ACCESS_KEY", "scenara")
S3_SECRET_KEY = os.getenv("SCENARA_INTEGRATION_S3_SECRET_KEY", "scenara-integration-secret")


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest_asyncio.fixture
async def postgres() -> AsyncIterator[PostgresStateStore]:
    store = PostgresStateStore(POSTGRES_DSN)
    await store.open()
    try:
        yield store
    finally:
        await store.close()


def _run(identifier: str, *, tenant_id: str = "integration") -> RunRecord:
    now = time.time()
    return RunRecord(
        run_id=f"run_{identifier}",
        tenant_id=tenant_id,
        project_id="qualification",
        domain="ocr",
        pipeline=PipelineRef(pipeline_id="ocr.document", version="0.1.0"),
        asset_id=f"ast_{identifier}",
        created_at=now,
        updated_at=now,
    )


async def test_postgres_idempotency_locking_events_and_pgvector(postgres: PostgresStateStore) -> None:
    suffix = uuid4().hex
    tenant_id = f"integration_{suffix}"
    asset = MediaAsset(
        asset_id=f"ast_{suffix}",
        tenant_id=tenant_id,
        project_id="qualification",
        kind=MediaKind.IMAGE,
        filename="sample.png",
        content_type="image/png",
        size_bytes=3,
        sha256=hashlib.sha256(b"png").hexdigest(),
        object_key=f"integration/{suffix}/sample.png",
        created_at=time.time(),
    )
    run = _run(suffix, tenant_id=tenant_id)
    try:
        await postgres.create_asset(asset)
        assert await postgres.get_asset(tenant_id, "qualification", asset.asset_id) == asset

        created, is_new = await postgres.create_run_idempotent(
            run,
            idempotency_key=f"idem_{suffix}",
            request_hash="a" * 64,
        )
        replay, replay_is_new = await postgres.create_run_idempotent(
            run,
            idempotency_key=f"idem_{suffix}",
            request_hash="a" * 64,
        )
        assert is_new is True
        assert replay_is_new is False
        assert replay.run_id == created.run_id
        with pytest.raises(StateConflict):
            await postgres.create_run_idempotent(
                run,
                idempotency_key=f"idem_{suffix}",
                request_hash="b" * 64,
            )

        running = await postgres.save_run(
            run.model_copy(update={"status": RunStatus.RUNNING, "updated_at": time.time()}),
            expected_revision=1,
        )
        assert running.revision == 2
        with pytest.raises(StateConflict):
            await postgres.save_run(run, expected_revision=1)

        webhook = WebhookSubscription(
            endpoint_id=f"whk_{suffix}",
            tenant_id=tenant_id,
            project_id="qualification",
            name="integration sink",
            url="https://events.example.test/scenara",
            secret_ref=f"secret://webhooks/{suffix}",
            event_types=frozenset({"run.completed"}),
            created_at=time.time(),
        )
        await postgres.create_webhook_subscription(webhook)

        first = await postgres.append_event(
            tenant_id,
            "qualification",
            RunEvent(
                run_id=run.run_id,
                event_id=1,
                event_type="run.running",
                status=RunStatus.RUNNING,
                created_at=time.time(),
            ),
        )
        second = await postgres.append_event(
            tenant_id,
            "qualification",
            RunEvent(
                run_id=run.run_id,
                event_id=1,
                event_type="run.completed",
                status=RunStatus.COMPLETED,
                created_at=time.time(),
            ),
        )
        assert (first.event_id, second.event_id) == (1, 2)
        claimed = await postgres.claim_webhook_deliveries(time.time() + 1, time.time() + 60, 10)
        assert len(claimed) == 1
        assert claimed[0].event_id == f"{run.run_id}:2"
        assert claimed[0].payload["event_type"] == "run.completed"
        delivered_at = time.time()
        await postgres.save_webhook_delivery(
            claimed[0].model_copy(
                update={
                    "status": "delivered",
                    "attempts": 1,
                    "status_code": 204,
                    "updated_at": delivered_at,
                    "delivered_at": delivered_at,
                }
            )
        )
        deliveries = await postgres.list_webhook_deliveries(tenant_id, "qualification", 10)
        assert deliveries[0].status == "delivered"

        features = PostgresFeatureStore(postgres.pool)
        space = FeatureSpace(
            feature_space_id=f"space_{suffix}",
            domain="portrait",
            modality="face",
            model_id="scenara.portrait.integration",
            model_version="1.0.0",
            dimension=3,
            distance_metric=DistanceMetric.COSINE,
            threshold=0.9,
        )
        await features.create_space(space)
        await features.add(
            FeatureRecord(
                tenant_id=tenant_id,
                project_id="qualification",
                feature_id=f"feature_{suffix}",
                feature_space_id=space.feature_space_id,
                subject_type="identity",
                subject_id="alice",
                embedding=[1.0, 0.0, 0.0],
            )
        )
        await features.add(
            FeatureRecord(
                tenant_id=f"other_{suffix}",
                project_id="qualification",
                feature_id=f"other_feature_{suffix}",
                feature_space_id=space.feature_space_id,
                subject_type="identity",
                subject_id="other",
                embedding=[1.0, 0.0, 0.0],
            )
        )
        matches = await features.search(
            tenant_id,
            "qualification",
            space.feature_space_id,
            [1.0, 0.0, 0.0],
            limit=10,
        )
        assert [match.subject_id for match in matches] == ["alice"]
        assert matches[0].score == pytest.approx(1.0)
        await features.add(
            FeatureRecord(
                tenant_id=tenant_id,
                project_id="qualification",
                feature_id=f"expired_feature_{suffix}",
                feature_space_id=space.feature_space_id,
                subject_type="identity",
                subject_id="expired",
                embedding=[0.0, 1.0, 0.0],
                expires_at=time.time() - 1,
            )
        )
        assert await features.delete_expired(time.time(), 10) == 1
        assert await features.delete_expired(time.time(), 10) == 0

        pipeline = PipelineDefinition(
            pipeline_id=f"integration.pipeline-{suffix}",
            version="1.0.0",
            domain="ocr",
            status=PipelineStatus.DRAFT,
            nodes=[
                PipelineNode(
                    node_id="decode",
                    operator_id="platform.media.decode",
                    inputs={"media": "$media.input"},
                )
            ],
            output="decode.batch",
        )
        await postgres.register_pipeline_definition(pipeline)
        assert await postgres.get_pipeline_definition(pipeline.pipeline_id, pipeline.version) == pipeline
        mutated = pipeline.model_copy(update={"output": "decode.other"})
        with pytest.raises(StateConflict, match="immutable"):
            await postgres.register_pipeline_definition(mutated)
        for target in (PipelineStatus.VALIDATED, PipelineStatus.APPROVED, PipelineStatus.ACTIVE):
            transitioned = await postgres.transition_pipeline_definition(
                pipeline.pipeline_id,
                pipeline.version,
                target,
            )
            assert transitioned.status == target

        package = ModelPackageManifest(
            model_id=f"integration.model-{suffix}",
            version="1.0.0",
            capability="integration-test",
            adapter="test-adapter",
            runtime_model_id="integration/model-test",
            sha256="d" * 64,
            source_uri=f"internal://integration-test#sha256={'d' * 64}",
            license_id="Proprietary",
            model_card=f"internal://model-card.yml#sha256={'e' * 64}",
            evaluation_evidence=(f"internal://evaluation.json#sha256={'f' * 64}",),
            vram_mb=1,
            regression_samples=("sample-1",),
            production_ready=True,
        )
        await postgres.register_model_package(package)
        assert package in await postgres.list_model_packages()

        result_key = f"integration/{suffix}/result.json"
        await postgres.save_result_reference(
            tenant_id,
            "qualification",
            ResultReference(
                run_id=run.run_id,
                object_key=result_key,
                sha256="c" * 64,
                unit_count=0,
                domain="ocr",
                created_at=time.time(),
            ),
        )
        expired_at = time.time() - 1
        await postgres.track_object(
            ObjectRetentionRecord(
                tenant_id=tenant_id,
                project_id="qualification",
                object_key=asset.object_key,
                category="raw_media",
                owner_type="media_asset",
                owner_id=asset.asset_id,
                created_at=expired_at - 1,
                expires_at=expired_at,
            )
        )
        await postgres.track_object(
            ObjectRetentionRecord(
                tenant_id=tenant_id,
                project_id="qualification",
                object_key=result_key,
                category="structured_result",
                owner_type="run_result",
                owner_id=run.run_id,
                created_at=expired_at - 1,
                expires_at=expired_at,
            )
        )
        expired = await postgres.expired_object_keys(time.time(), 10)
        assert {asset.object_key, result_key} <= set(expired)
        await postgres.mark_objects_deleted([asset.object_key, result_key], time.time())
        retained_asset = await postgres.get_asset(tenant_id, "qualification", asset.asset_id)
        assert retained_asset is not None and retained_asset.original_deleted_at is not None
        assert await postgres.get_result_reference(tenant_id, "qualification", run.run_id) is None
    finally:
        async with postgres.pool.connection() as connection, connection.transaction():
            await connection.execute("DELETE FROM scenara_object_retention WHERE tenant_id = %s", (tenant_id,))
            await connection.execute(
                "DELETE FROM scenara_features WHERE feature_id IN (%s, %s)",
                (f"feature_{suffix}", f"other_feature_{suffix}"),
            )
            await connection.execute(
                "DELETE FROM scenara_feature_spaces WHERE feature_space_id = %s", (f"space_{suffix}",)
            )
            await connection.execute(
                "DELETE FROM scenara_pipeline_versions WHERE pipeline_id = %s", (f"integration.pipeline-{suffix}",)
            )
            await connection.execute(
                "DELETE FROM scenara_model_packages WHERE model_id = %s", (f"integration.model-{suffix}",)
            )
        await postgres.delete_run(tenant_id, "qualification", run.run_id)
        await postgres.delete_asset(tenant_id, "qualification", asset.asset_id)


async def test_postgres_run_filters_pagination_and_active_reference_lookup(postgres: PostgresStateStore) -> None:
    suffix = uuid4().hex
    tenant_id = f"pagination_{suffix}"
    runs = (
        _run(f"{suffix}_old", tenant_id=tenant_id).model_copy(
            update={"created_at": 1.0, "updated_at": 1.0},
        ),
        _run(f"{suffix}_done", tenant_id=tenant_id).model_copy(
            update={
                "domain": "portrait",
                "status": RunStatus.COMPLETED,
                "created_at": 2.0,
                "updated_at": 2.0,
            },
        ),
        _run(f"{suffix}_new", tenant_id=tenant_id).model_copy(
            update={"created_at": 3.0, "updated_at": 3.0},
        ),
    )
    try:
        for index, run in enumerate(runs):
            await postgres.create_run_idempotent(
                run,
                idempotency_key=f"page_{suffix}_{index}",
                request_hash=str(index),
            )

        page = await postgres.list_runs(
            tenant_id,
            "qualification",
            domain="ocr",
            offset=1,
            limit=1,
        )

        assert [item.run_id for item in page] == [runs[0].run_id]
        assert await postgres.count_runs(tenant_id, "qualification", domain="ocr") == 2
        assert await postgres.count_runs(tenant_id, "qualification", status=RunStatus.COMPLETED) == 1
        assert (
            await postgres.has_non_terminal_run(
                tenant_id,
                "qualification",
                asset_id=runs[0].asset_id,
            )
            is True
        )
        assert (
            await postgres.has_non_terminal_run(
                tenant_id,
                "qualification",
                asset_id=runs[1].asset_id,
            )
            is False
        )
    finally:
        for run in runs:
            await postgres.delete_run(tenant_id, "qualification", run.run_id)
        await postgres.delete_webhook_subscription(tenant_id, "qualification", f"whk_{suffix}")


async def test_redis_delivery_and_pending_recovery() -> None:
    suffix = uuid4().hex
    stream = f"scenara:integration:{suffix}"
    failed = RedisRunQueue(REDIS_URL, stream=stream, group=f"workers-{suffix}", visibility_timeout_ms=50)

    async def fail_once(tenant_id: str, project_id: str, run_id: str) -> None:
        del tenant_id, project_id, run_id
        raise RuntimeError("simulated worker loss")

    failed.set_handler(fail_once)
    await failed.open()
    await failed.enqueue(_run(suffix))
    first_consumer = asyncio.create_task(
        failed.consume_forever(consumer=f"failed-{suffix}", block_ms=25),
    )
    with pytest.raises(RuntimeError, match="simulated worker loss"):
        await asyncio.wait_for(first_consumer, timeout=5)
    await failed.close()

    delivered = asyncio.Event()
    received: list[tuple[str, str, str]] = []
    recovered = RedisRunQueue(REDIS_URL, stream=stream, group=f"workers-{suffix}", visibility_timeout_ms=50)

    async def handle(tenant_id: str, project_id: str, run_id: str) -> None:
        received.append((tenant_id, project_id, run_id))
        delivered.set()

    recovered.set_handler(handle)
    await recovered.open()
    await asyncio.sleep(0.075)
    second_consumer = asyncio.create_task(
        recovered.consume_forever(consumer=f"recovered-{suffix}", block_ms=25),
    )
    await asyncio.wait_for(delivered.wait(), timeout=5)
    client = recovered._client
    for _ in range(100):
        pending = await client.xpending(stream + ":batch", f"workers-{suffix}:batch")
        if pending["pending"] == 0:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("Redis message was handled but not acknowledged")
    await client.delete(stream + ":batch", stream + ":stream")
    await recovered.close()
    second_consumer.cancel()
    await asyncio.gather(second_consumer, return_exceptions=True)
    assert received == [("integration", "qualification", f"run_{suffix}")]


async def test_empty_redis_run_streams_rebuild_from_postgres_and_minio(
    postgres: PostgresStateStore,
) -> None:
    suffix = uuid4().hex
    tenant_id = f"queue_rebuild_{suffix}"
    stream = f"scenara:integration:rebuild:{suffix}"
    asset_data = b"persisted-media"
    asset = MediaAsset(
        asset_id=f"ast_{suffix}",
        tenant_id=tenant_id,
        project_id="qualification",
        kind=MediaKind.IMAGE,
        filename="rebuild.png",
        content_type="image/png",
        size_bytes=len(asset_data),
        sha256=hashlib.sha256(asset_data).hexdigest(),
        object_key=f"integration/{suffix}/rebuild.png",
        created_at=time.time(),
    )
    run = _run(suffix, tenant_id=tenant_id).model_copy(update={"asset_id": asset.asset_id})
    store = S3ObjectStore(
        bucket="scenara",
        endpoint_url=S3_ENDPOINT,
        region="us-east-1",
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
    )
    queue = RedisRunQueue(REDIS_URL, stream=stream, group=f"workers-{suffix}")
    await store.open()
    try:
        await postgres.create_asset(asset)
        await postgres.create_run_idempotent(
            run,
            idempotency_key=f"rebuild-{suffix}",
            request_hash="a" * 64,
        )
        await store.put(asset.object_key, asset_data, asset.content_type)

        raw_redis = __import__("redis.asyncio", fromlist=["Redis"]).from_url(REDIS_URL)
        await raw_redis.delete(f"{stream}:batch", f"{stream}:stream")
        await raw_redis.aclose()
        await queue.open()

        summary = await rebuild_redis_run_queue(postgres, store, queue)

        assert summary.recoverable_runs == 1
        assert summary.enqueued_runs == 1
        assert summary.assets_verified == 1
        assert summary.sources_verified == 0
        messages = await queue._client.xrange(f"{stream}:batch")
        assert [fields["run_id"] for _, fields in messages] == [run.run_id]
        with pytest.raises(RuntimeError, match="must be empty"):
            await rebuild_redis_run_queue(postgres, store, queue)
    finally:
        if queue._client is not None:
            await queue._client.delete(f"{stream}:batch", f"{stream}:stream")
            await queue.close()
        with suppress(Exception):
            await store.delete(asset.object_key)
        await store.close()
        await postgres.delete_run(tenant_id, "qualification", run.run_id)
        await postgres.delete_asset(tenant_id, "qualification", asset.asset_id)


async def test_minio_object_round_trip_and_delete() -> None:
    suffix = uuid4().hex
    key = f"integration/{suffix}/object.bin"
    store = S3ObjectStore(
        bucket="scenara",
        endpoint_url=S3_ENDPOINT,
        region="us-east-1",
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
    )
    await store.open()
    try:
        await store.put(key, b"scenara-integration", "application/octet-stream")
        assert await store.get(key) == b"scenara-integration"
        assert await store.delete(key) is True
        with pytest.raises(ValueError):
            await store.put("../escape", b"bad", "application/octet-stream")
    finally:
        with suppress(Exception):
            await store.delete(key)
        await store.close()


async def test_s3_provider_satisfies_object_store_contract(tmp_path) -> None:
    def factory() -> S3ObjectStore:
        return S3ObjectStore(
            bucket="scenara",
            endpoint_url=S3_ENDPOINT,
            region="us-east-1",
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            multipart_threshold_bytes=5 * 1024 * 1024,
            multipart_chunk_bytes=5 * 1024 * 1024,
        )

    await assert_object_store_contract(factory, tmp_path)


async def test_s3_provider_installs_category_lifecycle_rules() -> None:
    store = S3ObjectStore(
        bucket="scenara",
        endpoint_url=S3_ENDPOINT,
        region="us-east-1",
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
        raw_media_retention_days=7,
        preview_retention_days=30,
        structured_result_retention_days=180,
    )
    try:
        await store.configure_lifecycle()
        configured = await asyncio.to_thread(
            store.client.get_bucket_lifecycle_configuration,
            Bucket="scenara",
        )
        rules = {rule["ID"]: rule for rule in configured["Rules"]}
        assert rules["scenara-raw_media"]["Expiration"]["Days"] == 8
        assert rules["scenara-preview"]["Expiration"]["Days"] == 31
        assert rules["scenara-structured_result"]["Expiration"]["Days"] == 181
        assert rules["scenara-pending_upload"]["Expiration"]["Days"] == 1
    finally:
        await store.close()


async def test_presigned_media_upload_and_download_bypass_api_payload(development_settings) -> None:
    image_buffer = BytesIO()
    Image.new("RGB", (32, 24), "white").save(image_buffer, format="PNG")
    payload = image_buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    settings = replace(
        development_settings,
        object_backend="s3",
        s3_endpoint_url=S3_ENDPOINT,
        s3_bucket="scenara",
        s3_access_key=S3_ACCESS_KEY,
        s3_secret_key=S3_SECRET_KEY,
        s3_presigned_urls_enabled=True,
        api_token="example-integration-direct-upload-signing-key",
    )
    runtime = build_runtime(settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        presigned = await api.post(
            "/api/v1/media/uploads/presign",
            json={
                "filename": "direct.png",
                "content_type": "image/png",
                "kind": "image",
                "size_bytes": len(payload),
                "sha256": digest,
            },
        )
        assert presigned.status_code == 200, presigned.text
        upload = presigned.json()["data"]
        async with httpx.AsyncClient() as direct:
            uploaded = await direct.put(upload["url"], content=payload, headers=upload["headers"])
        assert uploaded.status_code in {200, 201}, uploaded.text

        completed = await api.post(
            "/api/v1/media/uploads/complete",
            json={
                "filename": "direct.png",
                "content_type": "image/png",
                "kind": "image",
                "size_bytes": len(payload),
                "sha256": digest,
                "upload_id": upload["upload_id"],
                "upload_token": upload["upload_token"],
                "expires_at": upload["expires_at"],
            },
        )
        assert completed.status_code == 201, completed.text
        asset = completed.json()["data"]
        assert asset["sha256"] == digest

        download = await api.get(f"/api/v1/media/assets/{asset['asset_id']}/download-url")
        assert download.status_code == 200, download.text
        async with httpx.AsyncClient() as direct:
            downloaded = await direct.get(download.json()["data"]["url"])
        assert downloaded.status_code == 200
        assert downloaded.content == payload
        assert (await api.delete(f"/api/v1/media/assets/{asset['asset_id']}")).status_code == 204
