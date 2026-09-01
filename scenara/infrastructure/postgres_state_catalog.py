"""PostgreSQL catalog persistence mixin."""

from __future__ import annotations

from typing import Any

from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import PipelineDefinition
from scenara.platform.store import StateConflict


class PostgresCatalogMixin:
    """Pipeline and immutable model-package persistence for PostgreSQL state."""

    _pool: Any

    async def register_pipeline_definition(self, pipeline: PipelineDefinition) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT definition_sha256 FROM scenara_pipeline_versions
                   WHERE pipeline_id = %s AND version = %s FOR UPDATE""",
                (pipeline.pipeline_id, pipeline.version),
            )
            row = await cursor.fetchone()
            if row is not None:
                if str(row[0]) != pipeline.definition_sha256:
                    if pipeline.status == PipelineStatus.ACTIVE:
                        await conn.execute(
                            """UPDATE scenara_pipeline_versions
                               SET definition = %s, definition_sha256 = %s, domain = %s
                               WHERE pipeline_id = %s AND version = %s""",
                            (
                                Jsonb(pipeline.model_dump(mode="json")),
                                pipeline.definition_sha256,
                                pipeline.domain,
                                pipeline.pipeline_id,
                                pipeline.version,
                            ),
                        )
                        return
                    raise StateConflict("pipeline version definition is immutable")
                return
            try:
                if pipeline.status == PipelineStatus.ACTIVE:
                    await conn.execute(
                        """UPDATE scenara_pipeline_versions
                           SET status = 'retired' WHERE pipeline_id = %s AND status = 'active'""",
                        (pipeline.pipeline_id,),
                    )
                await conn.execute(
                    """INSERT INTO scenara_pipeline_versions
                       (pipeline_id, version, domain, status, definition, definition_sha256, activated_at)
                       VALUES (%s, %s, %s, %s, %s, %s,
                               CASE WHEN %s = 'active' THEN now() ELSE NULL END)""",
                    (
                        pipeline.pipeline_id,
                        pipeline.version,
                        pipeline.domain,
                        pipeline.status.value,
                        Jsonb(pipeline.model_dump(mode="json")),
                        pipeline.definition_sha256,
                        pipeline.status.value,
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict(
                        "pipeline already has an active version"
                    ) from exc
                raise

    async def get_pipeline_definition(
        self, pipeline_id: str, version: str
    ) -> PipelineDefinition | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT definition || jsonb_build_object('status', status) FROM scenara_pipeline_versions
                   WHERE pipeline_id = %s AND version = %s""",
                (pipeline_id, version),
            )
            row = await cursor.fetchone()
        return PipelineDefinition.model_validate(row[0]) if row else None

    async def list_pipeline_definitions(self) -> list[PipelineDefinition]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT definition || jsonb_build_object('status', status)
                   FROM scenara_pipeline_versions ORDER BY pipeline_id, version"""
            )
            rows = await cursor.fetchall()
        return [PipelineDefinition.model_validate(row[0]) for row in rows]

    async def transition_pipeline_definition(
        self, pipeline_id: str, version: str, target: PipelineStatus
    ) -> PipelineDefinition:
        allowed = {
            PipelineStatus.DRAFT: {PipelineStatus.VALIDATED},
            PipelineStatus.VALIDATED: {PipelineStatus.APPROVED, PipelineStatus.DRAFT},
            PipelineStatus.APPROVED: {PipelineStatus.ACTIVE, PipelineStatus.DRAFT},
            PipelineStatus.ACTIVE: {PipelineStatus.RETIRED},
            PipelineStatus.RETIRED: set(),
        }
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT status, definition FROM scenara_pipeline_versions
                   WHERE pipeline_id = %s AND version = %s FOR UPDATE""",
                (pipeline_id, version),
            )
            row = await cursor.fetchone()
            if row is None:
                raise StateConflict("pipeline version does not exist")
            current = PipelineStatus(str(row[0]))
            if target not in allowed[current]:
                raise StateConflict(
                    f"invalid pipeline transition: {current.value} -> {target.value}"
                )
            if target == PipelineStatus.ACTIVE:
                await conn.execute(
                    """UPDATE scenara_pipeline_versions
                       SET status = 'retired' WHERE pipeline_id = %s AND status = 'active'""",
                    (pipeline_id,),
                )
            await conn.execute(
                """UPDATE scenara_pipeline_versions
                   SET status = %s, activated_at = CASE WHEN %s = 'active' THEN now() ELSE activated_at END
                   WHERE pipeline_id = %s AND version = %s""",
                (target.value, target.value, pipeline_id, version),
            )
            payload = dict(row[1])
            payload["status"] = target.value
        return PipelineDefinition.model_validate(payload)

    async def register_model_package(self, package: ModelPackageManifest) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT sha256, manifest FROM scenara_model_packages
                   WHERE model_id = %s AND version = %s FOR UPDATE""",
                (package.model_id, package.version),
            )
            row = await cursor.fetchone()
            if row is not None:
                if (
                    str(row[0]) != package.sha256
                    or ModelPackageManifest.model_validate(row[1]) != package
                ):
                    raise StateConflict("model package version is immutable")
                return
            await conn.execute(
                """INSERT INTO scenara_model_packages
                   (model_id, version, capability, adapter, sha256, license_id, source_uri,
                    vram_mb, production_ready, manifest)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    package.model_id,
                    package.version,
                    package.capability,
                    package.adapter,
                    package.sha256,
                    package.license_id,
                    package.source_uri,
                    package.vram_mb,
                    package.production_ready,
                    Jsonb(package.model_dump(mode="json")),
                ),
            )

    async def list_model_packages(self) -> list[ModelPackageManifest]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT manifest FROM scenara_model_packages ORDER BY model_id, version"
            )
            rows = await cursor.fetchall()
        return [ModelPackageManifest.model_validate(row[0]) for row in rows]
