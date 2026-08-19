from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest

from scenara.infrastructure.postgres_feedback import PostgresFeedbackRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.platform.feedback import (
    FeedbackKind,
    FeedbackRecord,
    FeedbackStatus,
    HardSampleItem,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelRelease,
    ModelReleaseStatus,
)

pytestmark = pytest.mark.integration

POSTGRES_DSN = os.getenv(
    "SCENARA_INTEGRATION_POSTGRES_DSN",
    "postgresql://scenara:scenara-integration@127.0.0.1:55432/scenara",
)


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


@pytest.mark.asyncio
async def test_feedback_and_model_release_postgres_persistence() -> None:
    suffix = uuid4().hex
    tenant_id = f"feedback_{suffix}"
    project_id = "qualification"
    state = PostgresStateStore(POSTGRES_DSN)
    await state.open()
    repository = PostgresFeedbackRepository(state.pool)
    now = time.time()
    feedback = FeedbackRecord(
        feedback_id=f"fbk_{suffix}",
        tenant_id=tenant_id,
        project_id=project_id,
        kind=FeedbackKind.FALSE_NEGATIVE,
        run_id=f"run_{suffix}",
        result_ref=f"s3://results/{suffix}.json",
        media_ref=f"s3://media/{suffix}.jpg",
        pipeline_id="portrait.full-analysis",
        pipeline_version="0.4.0",
        model_id="scenara.portrait.integration",
        model_version="1.0.0",
        correction={"label": "person"},
        authorized_for_training=True,
        deidentified=True,
        submitted_by="integration",
        created_at=now,
        updated_at=now,
    )
    try:
        await repository.create_feedback(feedback)
        saved = await repository.save_feedback(
            feedback.model_copy(
                update={
                    "status": FeedbackStatus.APPROVED,
                    "reviewed_by": "integration-reviewer",
                    "updated_at": time.time(),
                }
            ),
            FeedbackStatus.PENDING,
        )
        assert saved.status == FeedbackStatus.APPROVED
        assert [item.feedback_id for item in await repository.list_feedback(tenant_id, project_id)] == [
            feedback.feedback_id
        ]

        item = HardSampleItem(
            feedback_id=feedback.feedback_id,
            kind=feedback.kind,
            media_ref=feedback.media_ref,
            result_ref=feedback.result_ref,
            model_id=feedback.model_id,
            model_version=feedback.model_version,
            pipeline_id=feedback.pipeline_id,
            pipeline_version=feedback.pipeline_version,
            correction=feedback.correction,
        )
        manifest = HardSampleManifest(
            manifest_id=f"hsm_{suffix}",
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=f"portrait.integration-{suffix}",
            version="1.0.0",
            items=(item,),
            sha256="a" * 64,
            created_by="integration",
            created_at="2026-08-18T00:00:00Z",
        )
        await repository.create_manifest(manifest)
        assert (await repository.list_manifests(tenant_id, project_id))[0].sha256 == "a" * 64

        release = ModelRelease(
            tenant_id=tenant_id,
            project_id=project_id,
            model_id="scenara.portrait.integration",
            version="1.0.0",
            capability="person_detection",
            runtime_model_id="scenara.portrait/integration",
            package_sha256="b" * 64,
            created_by="integration",
            created_at="2026-08-18T00:00:00Z",
            updated_at=time.time(),
        )
        await repository.create_release(release)
        for target in (
            ModelReleaseStatus.VALIDATED,
            ModelReleaseStatus.APPROVED,
            ModelReleaseStatus.ACTIVE,
        ):
            transitioned, _ = await repository.transition_release(
                tenant_id,
                project_id,
                release.model_id,
                release.version,
                target,
            )
        assert transitioned.status == ModelReleaseStatus.ACTIVE
        event = ModelDeploymentEvent(
            event_id=f"mde_{suffix}",
            tenant_id=tenant_id,
            project_id=project_id,
            model_id=release.model_id,
            version=release.version,
            capability=release.capability,
            runtime_model_id=release.runtime_model_id,
            package_sha256=release.package_sha256,
            action="transition",
            from_status=ModelReleaseStatus.APPROVED,
            to_status=ModelReleaseStatus.ACTIVE,
            reason="integration qualification",
            operator_id="integration",
            audit_id=f"aud_{suffix}",
            created_at=time.time(),
        )
        await repository.append_deployment_event(event)
        assert (await repository.list_deployment_events(tenant_id, project_id, 10))[0].event_id == event.event_id
    finally:
        async with state.pool.connection() as connection, connection.transaction():
            for table in (
                "scenara_model_deployment_events",
                "scenara_model_releases",
                "scenara_hard_sample_manifests",
                "scenara_feedback",
            ):
                await connection.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
        await state.close()
