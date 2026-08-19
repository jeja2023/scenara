from __future__ import annotations

from typing import Any

from scenara.platform.feedback import (
    FeedbackConflict,
    FeedbackNotFound,
    FeedbackRecord,
    FeedbackStatus,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelRelease,
    ModelReleaseStatus,
    utc_epoch,
    validate_release_transition,
)


class PostgresFeedbackRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord:
        from psycopg.types.json import Jsonb

        try:
            async with self._pool.connection() as connection, connection.transaction():
                await connection.execute(
                    """INSERT INTO scenara_feedback
                       (tenant_id, project_id, feedback_id, status, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        record.tenant_id,
                        record.project_id,
                        record.feedback_id,
                        record.status.value,
                        record.created_at,
                        record.updated_at,
                        Jsonb(record.model_dump(mode="json")),
                    ),
                )
        except Exception as exc:
            if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                raise FeedbackConflict("feedback already exists") from exc
            raise
        return record

    async def get_feedback(self, tenant_id: str, project_id: str, feedback_id: str) -> FeedbackRecord | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """SELECT document FROM scenara_feedback
                   WHERE tenant_id = %s AND project_id = %s AND feedback_id = %s""",
                (tenant_id, project_id, feedback_id),
            )
            row = await cursor.fetchone()
        return FeedbackRecord.model_validate(row[0]) if row else None

    async def list_feedback(self, tenant_id: str, project_id: str) -> list[FeedbackRecord]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """SELECT document FROM scenara_feedback
                   WHERE tenant_id = %s AND project_id = %s ORDER BY created_at DESC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [FeedbackRecord.model_validate(row[0]) for row in rows]

    async def save_feedback(self, record: FeedbackRecord, expected_status: FeedbackStatus) -> FeedbackRecord:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """UPDATE scenara_feedback
                   SET status = %s, updated_at = to_timestamp(%s), document = %s
                   WHERE tenant_id = %s AND project_id = %s AND feedback_id = %s AND status = %s""",
                (
                    record.status.value,
                    record.updated_at,
                    Jsonb(record.model_dump(mode="json")),
                    record.tenant_id,
                    record.project_id,
                    record.feedback_id,
                    expected_status.value,
                ),
            )
            if cursor.rowcount != 1:
                exists = await connection.execute(
                    """SELECT 1 FROM scenara_feedback
                       WHERE tenant_id = %s AND project_id = %s AND feedback_id = %s""",
                    (record.tenant_id, record.project_id, record.feedback_id),
                )
                if await exists.fetchone() is None:
                    raise FeedbackNotFound("feedback not found")
                raise FeedbackConflict("feedback status changed concurrently")
        return record

    async def create_manifest(self, manifest: HardSampleManifest) -> HardSampleManifest:
        from psycopg.types.json import Jsonb

        try:
            async with self._pool.connection() as connection, connection.transaction():
                await connection.execute(
                    """INSERT INTO scenara_hard_sample_manifests
                       (tenant_id, project_id, manifest_id, dataset_id, version, sha256, created_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)""",
                    (
                        manifest.tenant_id,
                        manifest.project_id,
                        manifest.manifest_id,
                        manifest.dataset_id,
                        manifest.version,
                        manifest.sha256,
                        utc_epoch(manifest.created_at),
                        Jsonb(manifest.model_dump(mode="json")),
                    ),
                )
        except Exception as exc:
            if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                raise FeedbackConflict("hard-sample manifest version already exists") from exc
            raise
        return manifest

    async def list_manifests(self, tenant_id: str, project_id: str) -> list[HardSampleManifest]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """SELECT document FROM scenara_hard_sample_manifests
                   WHERE tenant_id = %s AND project_id = %s ORDER BY created_at DESC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [HardSampleManifest.model_validate(row[0]) for row in rows]

    async def create_release(self, release: ModelRelease) -> ModelRelease:
        from psycopg.types.json import Jsonb

        try:
            async with self._pool.connection() as connection, connection.transaction():
                await connection.execute(
                    """INSERT INTO scenara_model_releases
                       (tenant_id, project_id, model_id, version, capability, status, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        release.tenant_id,
                        release.project_id,
                        release.model_id,
                        release.version,
                        release.capability,
                        release.status.value,
                        release.created_at,
                        release.updated_at,
                        Jsonb(release.model_dump(mode="json")),
                    ),
                )
        except Exception as exc:
            if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                raise FeedbackConflict("model release already exists") from exc
            raise
        return release

    async def get_release(
        self, tenant_id: str, project_id: str, model_id: str, version: str
    ) -> ModelRelease | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """SELECT document FROM scenara_model_releases
                   WHERE tenant_id = %s AND project_id = %s AND model_id = %s AND version = %s""",
                (tenant_id, project_id, model_id, version),
            )
            row = await cursor.fetchone()
        return ModelRelease.model_validate(row[0]) if row else None

    async def list_releases(self, tenant_id: str, project_id: str) -> list[ModelRelease]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """SELECT document FROM scenara_model_releases
                   WHERE tenant_id = %s AND project_id = %s ORDER BY model_id, version""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [ModelRelease.model_validate(row[0]) for row in rows]

    async def transition_release(
        self,
        tenant_id: str,
        project_id: str,
        model_id: str,
        version: str,
        target: ModelReleaseStatus,
        *,
        rollback: bool = False,
    ) -> tuple[ModelRelease, ModelRelease | None]:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """SELECT model_id, version, document FROM scenara_model_releases
                   WHERE tenant_id = %s AND project_id = %s
                     AND capability = (
                         SELECT capability FROM scenara_model_releases
                         WHERE tenant_id = %s AND project_id = %s AND model_id = %s AND version = %s
                     )
                   FOR UPDATE""",
                (tenant_id, project_id, tenant_id, project_id, model_id, version),
            )
            rows = await cursor.fetchall()
            releases = {
                (str(row[0]), str(row[1])): ModelRelease.model_validate(row[2])
                for row in rows
            }
            current = releases.get((model_id, version))
            if current is None:
                raise FeedbackNotFound("model release not found")
            validate_release_transition(current.status, target, rollback=rollback)
            now = __import__("time").time()
            previous: ModelRelease | None = None
            if target == ModelReleaseStatus.ACTIVE:
                previous = next(
                    (
                        item
                        for item in releases.values()
                        if (item.model_id, item.version) != (model_id, version)
                        and item.status == ModelReleaseStatus.ACTIVE
                    ),
                    None,
                )
                if previous is not None:
                    previous = previous.model_copy(
                        update={"status": ModelReleaseStatus.RETIRED, "retired_at": now, "updated_at": now}
                    )
                    await connection.execute(
                        """UPDATE scenara_model_releases
                           SET status = %s, updated_at = to_timestamp(%s), document = %s
                           WHERE tenant_id = %s AND project_id = %s AND model_id = %s AND version = %s""",
                        (
                            previous.status.value,
                            now,
                            Jsonb(previous.model_dump(mode="json")),
                            tenant_id,
                            project_id,
                            model_id,
                            previous.version,
                        ),
                    )
            updated = current.model_copy(
                update={
                    "status": target,
                    "updated_at": now,
                    "activated_at": now if target == ModelReleaseStatus.ACTIVE else current.activated_at,
                    "retired_at": now if target == ModelReleaseStatus.RETIRED else None,
                }
            )
            await connection.execute(
                """UPDATE scenara_model_releases
                   SET status = %s, updated_at = to_timestamp(%s), document = %s
                   WHERE tenant_id = %s AND project_id = %s AND model_id = %s AND version = %s""",
                (
                    updated.status.value,
                    now,
                    Jsonb(updated.model_dump(mode="json")),
                    tenant_id,
                    project_id,
                    model_id,
                    version,
                ),
            )
        return updated, previous

    async def append_deployment_event(self, event: ModelDeploymentEvent) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                """INSERT INTO scenara_model_deployment_events
                   (tenant_id, project_id, event_id, model_id, version, created_at, document)
                   VALUES (%s, %s, %s, %s, %s, to_timestamp(%s), %s)""",
                (
                    event.tenant_id,
                    event.project_id,
                    event.event_id,
                    event.model_id,
                    event.version,
                    utc_epoch(event.created_at),
                    Jsonb(event.model_dump(mode="json")),
                ),
            )

    async def list_deployment_events(
        self, tenant_id: str, project_id: str, limit: int
    ) -> list[ModelDeploymentEvent]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """SELECT document FROM scenara_model_deployment_events
                   WHERE tenant_id = %s AND project_id = %s ORDER BY created_at DESC LIMIT %s""",
                (tenant_id, project_id, limit),
            )
            rows = await cursor.fetchall()
        return [ModelDeploymentEvent.model_validate(row[0]) for row in rows]


__all__ = ["PostgresFeedbackRepository"]
