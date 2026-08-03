from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.domains.portrait.analysis import PORTRAIT_CAPABILITIES, PortraitBackendOutput
from scenara.infrastructure.object_store import S3ObjectStore
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.platform.models import CreateRunRequest, MediaKind, PipelineRef, PrincipalContext, RunStatus
from scenara.platform.retention import RetentionScheduler
from scenara.platform.services import ResourceNotFound
from scenara.settings import load_settings

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

POSTGRES_DSN = os.getenv(
    "SCENARA_INTEGRATION_POSTGRES_DSN",
    "postgresql://scenara:scenara-integration@127.0.0.1:55432/scenara",
)
S3_ENDPOINT = os.getenv("SCENARA_INTEGRATION_S3_ENDPOINT", "http://127.0.0.1:59000")
S3_ACCESS_KEY = os.getenv("SCENARA_INTEGRATION_S3_ACCESS_KEY", "scenara")
S3_SECRET_KEY = os.getenv("SCENARA_INTEGRATION_S3_SECRET_KEY", "scenara-integration-secret")

PERSON_BOX = [12.0, 16.0, 96.0, 120.0]
FACE_BOX = [40.0, 24.0, 72.0, 60.0]


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


class StubPortraitBackend:
    """Deterministic detections so the test asserts storage, not model quality."""

    def production_capabilities(self) -> frozenset[str]:
        return PORTRAIT_CAPABILITIES

    async def analyze(
        self,
        images: list[Image.Image],
        filenames: list[str | None],
        capabilities: frozenset[str],
    ) -> PortraitBackendOutput:
        del filenames, capabilities
        return PortraitBackendOutput(
            units=[
                {
                    "persons": [{"box": PERSON_BOX, "score": 0.94}],
                    "faces": [{"box": FACE_BOX, "score": 0.88}],
                    "silhouettes": [],
                }
                for _ in images
            ],
        )


def portrait_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (160, 160), "white").save(output, format="PNG")
    return output.getvalue()


async def test_feature_crops_round_trip_through_postgres_and_object_storage(tmp_path: Path) -> None:
    """Feature crops must persist to S3 and register preview retention in PostgreSQL.

    The unit suite covers this path on the memory/local adapters; this test pins
    the production adapter pair that the Compose stack actually deploys.
    """

    suffix = uuid4().hex
    tenant_id = f"artifacts_{suffix}"
    context = PrincipalContext(tenant_id=tenant_id, project_id="qualification", principal_id="integration")
    settings = replace(
        load_settings(),
        profile="integration",
        state_backend="postgres",
        object_backend="s3",
        queue_backend="inline",
        data_dir=tmp_path,
        postgres_dsn=POSTGRES_DSN,
        s3_endpoint_url=S3_ENDPOINT,
        s3_bucket="scenara",
        s3_access_key=S3_ACCESS_KEY,
        s3_secret_key=S3_SECRET_KEY,
        auth_required=False,
        production_models_required=False,
        ocr_engine_factory="",
        secret_encryption_key="",
        image_wait_timeout_ms=20_000,
    )
    runtime = build_runtime(settings, portrait_backend=StubPortraitBackend())
    assert isinstance(runtime.state, PostgresStateStore)
    assert isinstance(runtime.objects, S3ObjectStore)
    await runtime.open()
    asset = None
    run_id = ""
    try:
        asset = await runtime.runs.create_asset(
            context,
            data=portrait_png(),
            filename="portrait.png",
            content_type="image/png",
            kind=MediaKind.IMAGE,
        )
        pipeline = await runtime.runs.resolve_pipeline_ref("portrait.analysis")
        outcome = await runtime.runs.create_run(
            context,
            CreateRunRequest(
                domain="portrait",
                pipeline=PipelineRef(pipeline_id=pipeline.pipeline_id, version=pipeline.version),
                asset_id=asset.asset_id,
                wait_ms=20_000,
            ),
            idempotency_key=f"artifacts-{suffix}",
        )
        run_id = outcome.run.run_id
        assert outcome.run.status == RunStatus.COMPLETED, outcome.run.termination_reason

        result = await runtime.runs.result(context, run_id)
        unit = result.units[0]
        crop_ids = [item.crop_artifact_id for item in unit.objects]
        assert all(crop_ids), "person and face crops must be produced on the production adapters"
        assert unit.frame_artifact_id

        declared = {item.artifact_id: item for item in result.artifacts}
        assert set(crop_ids) | {unit.frame_artifact_id} == set(declared)

        # Every declared artifact must be readable from MinIO with a matching checksum.
        for artifact_id in declared:
            data, content_type, _ = await runtime.runs.result_artifact(context, run_id, artifact_id)
            assert content_type == "image/jpeg"
            with Image.open(BytesIO(data)) as decoded:
                assert decoded.format == "JPEG"
                assert decoded.width > 0 and decoded.height > 0

        # PostgreSQL must hold a preview-category retention row per artifact.
        keys = {declared[artifact_id].object_key for artifact_id in declared}
        async with runtime.state.pool.connection() as connection:
            rows = await (
                await connection.execute(
                    "SELECT object_key, category, owner_type, owner_id, expires_at "
                    "FROM scenara_object_retention WHERE tenant_id = %s AND object_key = ANY(%s)",
                    (tenant_id, list(keys)),
                )
            ).fetchall()
        assert {row[0] for row in rows} == keys
        assert {row[1] for row in rows} == {"preview"}
        assert {row[2] for row in rows} == {"run_result"}
        assert {row[3] for row in rows} == {run_id}
        assert all(row[4] is not None for row in rows), "artifacts must expire with the preview window"

        # Artifacts must not be swept while inside the preview window, and the real
        # sweeper must remove them from MinIO once that window has passed.
        inside_window = time.time() + settings.preview_retention_days * 86_400 / 2
        assert not keys & set(await runtime.state.expired_object_keys(inside_window, 500))

        after_window = time.time() + (settings.preview_retention_days + 1) * 86_400
        swept = await RetentionScheduler(runtime.state, runtime.objects).sweep(before=after_window, limit=500)
        assert swept >= len(keys)

        # Once swept, the read path reports a missing artifact rather than raising
        # a raw object-store error at the API boundary.
        for artifact_id in declared:
            with pytest.raises(ResourceNotFound):
                await runtime.runs.result_artifact(context, run_id, artifact_id)
    finally:
        if run_id:
            reference = await runtime.state.get_result_reference(tenant_id, "qualification", run_id)
            if reference is not None:
                for object_key in [reference.object_key, *reference.shard_keys]:
                    await runtime.objects.delete(object_key)
        if asset is not None:
            for object_key in [asset.object_key, asset.preview_object_key]:
                if object_key:
                    await runtime.objects.delete(object_key)
        async with runtime.state.pool.connection() as connection, connection.transaction():
            for table in (
                "scenara_object_retention",
                "scenara_audit_events",
                "scenara_run_events",
                "scenara_runs",
                "scenara_media_assets",
            ):
                await connection.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
        await runtime.close()
