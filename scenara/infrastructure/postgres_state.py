from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from scenara.platform.audit import AuditEvent
from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    DatasetRecord,
    DatasetVersion,
    MediaAsset,
    MediaSource,
    ObjectRetentionRecord,
    PipelineStatus,
    ResultReference,
    RunEvent,
    RunRecord,
    RunStatus,
    SavedSearch,
    WebhookDeliveryRecord,
    WebhookSubscription,
)
from scenara.platform.pipeline import PipelineDefinition
from scenara.platform.store import StateConflict


async def _register_pgvector(connection: Any) -> None:
    try:
        from pgvector.psycopg import register_vector_async
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError("pgvector is required for the PostgreSQL state backend") from exc
    await register_vector_async(connection)


class PostgresStateStore:
    """PostgreSQL adapter. Documents retain contract fidelity; columns support operational queries."""

    def __init__(self, dsn: str) -> None:
        try:
            from psycopg_pool import AsyncConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg-pool is required for the PostgreSQL state backend") from exc
        self._pool: Any = AsyncConnectionPool(dsn, open=False, min_size=1, max_size=10, configure=_register_pgvector)

    @property
    def pool(self) -> Any:
        return self._pool

    async def open(self) -> None:
        await self._pool.open()
        await self._apply_pending_migrations()

    async def _apply_pending_migrations(self) -> None:
        from pathlib import Path

        migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        if not migrations_dir.is_dir():
            return
        async with self._pool.connection() as conn:
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS scenara_schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )"""
            )
            cursor = await conn.execute("SELECT version FROM scenara_schema_migrations")
            applied = {str(row[0]) for row in await cursor.fetchall()}
            for sql_file in sorted(migrations_dir.glob("*.sql")):
                version = sql_file.stem
                if version not in applied:
                    sql_content = sql_file.read_text(encoding="utf-8")
                    await conn.execute(sql_content)
                    await conn.execute(
                        "INSERT INTO scenara_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
                        (version,),
                    )

    async def close(self) -> None:
        await self._pool.close()

    async def health_check(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("SELECT 1")

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
                    raise StateConflict("pipeline already has an active version") from exc
                raise

    async def get_pipeline_definition(self, pipeline_id: str, version: str) -> PipelineDefinition | None:
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
                raise StateConflict(f"invalid pipeline transition: {current.value} -> {target.value}")
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
                if str(row[0]) != package.sha256 or ModelPackageManifest.model_validate(row[1]) != package:
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
            cursor = await conn.execute("SELECT manifest FROM scenara_model_packages ORDER BY model_id, version")
            rows = await cursor.fetchall()
        return [ModelPackageManifest.model_validate(row[0]) for row in rows]

    async def create_webhook_subscription(self, endpoint: WebhookSubscription) -> WebhookSubscription:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_webhook_subscriptions
                       (tenant_id, project_id, endpoint_id, url, enabled, event_types, created_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)""",
                    (
                        endpoint.tenant_id,
                        endpoint.project_id,
                        endpoint.endpoint_id,
                        endpoint.url,
                        endpoint.enabled,
                        list(endpoint.event_types),
                        endpoint.created_at,
                        Jsonb(endpoint.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("webhook subscription already exists") from exc
                raise
        return endpoint.model_copy(deep=True)

    async def get_webhook_subscription(
        self, tenant_id: str, project_id: str, endpoint_id: str
    ) -> WebhookSubscription | None:
        row = await self._get_document(
            "scenara_webhook_subscriptions", "endpoint_id", tenant_id, project_id, endpoint_id
        )
        return WebhookSubscription.model_validate(row) if row else None

    async def list_webhook_subscriptions(self, tenant_id: str, project_id: str) -> list[WebhookSubscription]:
        rows = await self._list_documents("scenara_webhook_subscriptions", "endpoint_id", tenant_id, project_id)
        return [WebhookSubscription.model_validate(row) for row in rows]

    async def delete_webhook_subscription(
        self, tenant_id: str, project_id: str, endpoint_id: str
    ) -> WebhookSubscription | None:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_webhook_subscriptions
                   WHERE tenant_id = %s AND project_id = %s AND endpoint_id = %s RETURNING document""",
                (tenant_id, project_id, endpoint_id),
            )
            row = await cursor.fetchone()
        return WebhookSubscription.model_validate(row[0]) if row else None

    async def claim_webhook_deliveries(
        self, before: float, lease_until: float, limit: int
    ) -> list[WebhookDeliveryRecord]:
        from psycopg.types.json import Jsonb

        claimed: list[WebhookDeliveryRecord] = []
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT document FROM scenara_webhook_deliveries
                   WHERE status IN ('pending', 'delivering') AND next_attempt_at <= to_timestamp(%s)
                   ORDER BY next_attempt_at, created_at, delivery_id
                   FOR UPDATE SKIP LOCKED LIMIT %s""",
                (before, limit),
            )
            for row in await cursor.fetchall():
                delivery = WebhookDeliveryRecord.model_validate(row[0]).model_copy(
                    update={"status": "delivering", "next_attempt_at": lease_until, "updated_at": before}
                )
                await conn.execute(
                    """UPDATE scenara_webhook_deliveries
                       SET status = %s, next_attempt_at = to_timestamp(%s), updated_at = to_timestamp(%s), document = %s
                       WHERE tenant_id = %s AND project_id = %s AND delivery_id = %s""",
                    (
                        delivery.status,
                        delivery.next_attempt_at,
                        delivery.updated_at,
                        Jsonb(delivery.model_dump(mode="json")),
                        delivery.tenant_id,
                        delivery.project_id,
                        delivery.delivery_id,
                    ),
                )
                claimed.append(delivery)
        return claimed

    async def save_webhook_delivery(self, delivery: WebhookDeliveryRecord) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_webhook_deliveries
                   SET status = %s, attempts = %s, next_attempt_at = to_timestamp(%s),
                       updated_at = to_timestamp(%s), document = %s
                   WHERE tenant_id = %s AND project_id = %s AND delivery_id = %s""",
                (
                    delivery.status,
                    delivery.attempts,
                    delivery.next_attempt_at,
                    delivery.updated_at,
                    Jsonb(delivery.model_dump(mode="json")),
                    delivery.tenant_id,
                    delivery.project_id,
                    delivery.delivery_id,
                ),
            )
            if cursor.rowcount != 1:
                raise StateConflict("webhook delivery does not exist")

    async def list_webhook_deliveries(self, tenant_id: str, project_id: str, limit: int) -> list[WebhookDeliveryRecord]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_webhook_deliveries
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY created_at DESC, delivery_id DESC LIMIT %s""",
                (tenant_id, project_id, limit),
            )
            rows = await cursor.fetchall()
        return [WebhookDeliveryRecord.model_validate(row[0]) for row in rows]

    async def create_asset(self, asset: MediaAsset) -> MediaAsset:
        await self._insert_document("scenara_media_assets", "asset_id", asset.asset_id, asset)
        return asset.model_copy(deep=True)

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None:
        row = await self._get_document("scenara_media_assets", "asset_id", tenant_id, project_id, asset_id)
        return MediaAsset.model_validate(row) if row else None

    async def list_assets(
        self,
        tenant_id: str,
        project_id: str,
        *,
        domain: str | None = None,
        include_deleted: bool = True,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[MediaAsset]:
        conditions = ["tenant_id = %s", "project_id = %s"]
        parameters: list[Any] = [tenant_id, project_id]
        if not include_deleted:
            conditions.append("document ->> 'deleted_at' IS NULL")
        if domain is not None:
            conditions.append("document ->> 'domain' = %s")
            parameters.append(domain)
        query = f"""SELECT document FROM scenara_media_assets
                    WHERE {" AND ".join(conditions)}
                    ORDER BY created_at DESC, asset_id DESC"""
        if limit is not None:
            query += " LIMIT %s"
            parameters.append(limit)
        if offset:
            query += " OFFSET %s"
            parameters.append(offset)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(query, parameters)
            result = await cursor.fetchall()
        rows = [row[0] for row in result]
        return [MediaAsset.model_validate(row) for row in rows]

    async def count_assets(
        self,
        tenant_id: str,
        project_id: str,
        *,
        domain: str | None = None,
        include_deleted: bool = True,
    ) -> int:
        conditions = ["tenant_id = %s", "project_id = %s"]
        parameters: list[Any] = [tenant_id, project_id]
        if not include_deleted:
            conditions.append("document ->> 'deleted_at' IS NULL")
        if domain is not None:
            conditions.append("document ->> 'domain' = %s")
            parameters.append(domain)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT count(*) FROM scenara_media_assets
                    WHERE {" AND ".join(conditions)}""",
                parameters,
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def delete_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_media_assets
                   WHERE tenant_id = %s AND project_id = %s AND asset_id = %s RETURNING document""",
                (tenant_id, project_id, asset_id),
            )
            row = await cursor.fetchone()
        return MediaAsset.model_validate(row[0]) if row else None

    async def create_source(self, source: MediaSource) -> MediaSource:
        await self._insert_document("scenara_media_sources", "source_id", source.source_id, source)
        return source.model_copy(deep=True)

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None:
        row = await self._get_document("scenara_media_sources", "source_id", tenant_id, project_id, source_id)
        return MediaSource.model_validate(row) if row else None

    async def list_sources(
        self,
        tenant_id: str,
        project_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[MediaSource]:
        query = """SELECT document FROM scenara_media_sources
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY created_at DESC, source_id DESC"""
        parameters: list[Any] = [tenant_id, project_id]
        if limit is not None:
            query += " LIMIT %s"
            parameters.append(limit)
        if offset:
            query += " OFFSET %s"
            parameters.append(offset)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(query, parameters)
            result = await cursor.fetchall()
        rows = [row[0] for row in result]
        return [MediaSource.model_validate(row) for row in rows]

    async def count_sources(self, tenant_id: str, project_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT count(*) FROM scenara_media_sources
                   WHERE tenant_id = %s AND project_id = %s""",
                (tenant_id, project_id),
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def delete_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_media_sources
                   WHERE tenant_id = %s AND project_id = %s AND source_id = %s RETURNING document""",
                (tenant_id, project_id, source_id),
            )
            row = await cursor.fetchone()
        return MediaSource.model_validate(row[0]) if row else None

    async def create_dataset(self, dataset: DatasetRecord) -> DatasetRecord:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO scenara_datasets
                   (tenant_id, project_id, dataset_id, created_at, updated_at, status, document)
                   VALUES (%s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s)""",
                (
                    dataset.tenant_id,
                    dataset.project_id,
                    dataset.dataset_id,
                    dataset.created_at,
                    dataset.updated_at,
                    dataset.status.value,
                    Jsonb(dataset.model_dump(mode="json")),
                ),
            )
        return dataset.model_copy(deep=True)

    async def get_dataset(self, tenant_id: str, project_id: str, dataset_id: str) -> DatasetRecord | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_datasets
                   WHERE tenant_id = %s AND project_id = %s AND dataset_id = %s""",
                (tenant_id, project_id, dataset_id),
            )
            row = await cursor.fetchone()
        return DatasetRecord.model_validate(row[0]) if row else None

    async def list_datasets(
        self, tenant_id: str, project_id: str, *, offset: int = 0, limit: int = 50
    ) -> list[DatasetRecord]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_datasets
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY updated_at DESC, dataset_id DESC LIMIT %s OFFSET %s""",
                (tenant_id, project_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return [DatasetRecord.model_validate(row[0]) for row in rows]

    async def count_datasets(self, tenant_id: str, project_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT count(*) FROM scenara_datasets
                   WHERE tenant_id = %s AND project_id = %s""",
                (tenant_id, project_id),
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def save_dataset(self, dataset: DatasetRecord) -> DatasetRecord:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_datasets
                   SET updated_at = to_timestamp(%s), status = %s, document = %s
                   WHERE tenant_id = %s AND project_id = %s AND dataset_id = %s""",
                (
                    dataset.updated_at,
                    dataset.status.value,
                    Jsonb(dataset.model_dump(mode="json")),
                    dataset.tenant_id,
                    dataset.project_id,
                    dataset.dataset_id,
                ),
            )
            if cursor.rowcount != 1:
                raise StateConflict("dataset not found")
        return dataset.model_copy(deep=True)

    async def create_dataset_version(self, version: DatasetVersion) -> DatasetVersion:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO scenara_dataset_versions
                   (tenant_id, project_id, version_id, dataset_id, version, status,
                    manifest_sha256, created_at, updated_at, document)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                (
                    version.tenant_id,
                    version.project_id,
                    version.version_id,
                    version.dataset_id,
                    version.version,
                    version.status.value,
                    version.manifest_sha256,
                    version.created_at,
                    version.updated_at,
                    Jsonb(version.model_dump(mode="json")),
                ),
            )
        return version.model_copy(deep=True)

    async def get_dataset_version(
        self, tenant_id: str, project_id: str, version_id: str
    ) -> DatasetVersion | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_dataset_versions
                   WHERE tenant_id = %s AND project_id = %s AND version_id = %s""",
                (tenant_id, project_id, version_id),
            )
            row = await cursor.fetchone()
        return DatasetVersion.model_validate(row[0]) if row else None

    async def save_dataset_version(self, version: DatasetVersion) -> DatasetVersion:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_dataset_versions
                   SET updated_at = to_timestamp(%s), status = %s, document = %s
                   WHERE tenant_id = %s AND project_id = %s AND version_id = %s""",
                (
                    version.updated_at,
                    version.status.value,
                    Jsonb(version.model_dump(mode="json")),
                    version.tenant_id,
                    version.project_id,
                    version.version_id,
                ),
            )
            if cursor.rowcount != 1:
                raise StateConflict("dataset version not found")
        return version.model_copy(deep=True)

    async def list_dataset_versions(
        self,
        tenant_id: str,
        project_id: str,
        dataset_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[DatasetVersion]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_dataset_versions
                   WHERE tenant_id = %s AND project_id = %s AND dataset_id = %s
                   ORDER BY created_at DESC, version_id DESC LIMIT %s OFFSET %s""",
                (tenant_id, project_id, dataset_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return [DatasetVersion.model_validate(row[0]) for row in rows]

    async def count_dataset_versions(self, tenant_id: str, project_id: str, dataset_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT count(*) FROM scenara_dataset_versions
                   WHERE tenant_id = %s AND project_id = %s AND dataset_id = %s""",
                (tenant_id, project_id, dataset_id),
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def create_saved_search(self, saved_search: SavedSearch) -> SavedSearch:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn:
            try:
                await conn.execute(
                    """INSERT INTO scenara_saved_searches
                       (tenant_id, project_id, saved_search_id, name, mode, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        saved_search.tenant_id,
                        saved_search.project_id,
                        saved_search.saved_search_id,
                        saved_search.name,
                        saved_search.mode.value,
                        saved_search.created_at,
                        saved_search.updated_at,
                        Jsonb(saved_search.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("saved search already exists") from exc
                raise
        return saved_search.model_copy(deep=True)

    async def get_saved_search(
        self, tenant_id: str, project_id: str, saved_search_id: str
    ) -> SavedSearch | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_saved_searches
                   WHERE tenant_id = %s AND project_id = %s AND saved_search_id = %s""",
                (tenant_id, project_id, saved_search_id),
            )
            row = await cursor.fetchone()
        return SavedSearch.model_validate(row[0]) if row else None

    async def list_saved_searches(
        self, tenant_id: str, project_id: str, *, offset: int = 0, limit: int = 50
    ) -> list[SavedSearch]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_saved_searches
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY updated_at DESC, saved_search_id DESC LIMIT %s OFFSET %s""",
                (tenant_id, project_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return [SavedSearch.model_validate(row[0]) for row in rows]

    async def count_saved_searches(self, tenant_id: str, project_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT count(*) FROM scenara_saved_searches
                   WHERE tenant_id = %s AND project_id = %s""",
                (tenant_id, project_id),
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def save_saved_search(self, saved_search: SavedSearch) -> SavedSearch:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                cursor = await conn.execute(
                    """UPDATE scenara_saved_searches
                       SET name = %s, mode = %s, updated_at = to_timestamp(%s), document = %s
                       WHERE tenant_id = %s AND project_id = %s AND saved_search_id = %s""",
                    (
                        saved_search.name,
                        saved_search.mode.value,
                        saved_search.updated_at,
                        Jsonb(saved_search.model_dump(mode="json")),
                        saved_search.tenant_id,
                        saved_search.project_id,
                        saved_search.saved_search_id,
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("saved search name already exists") from exc
                raise
            if cursor.rowcount != 1:
                raise StateConflict("saved search not found")
        return saved_search.model_copy(deep=True)

    async def delete_saved_search(
        self, tenant_id: str, project_id: str, saved_search_id: str
    ) -> SavedSearch | None:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_saved_searches
                   WHERE tenant_id = %s AND project_id = %s AND saved_search_id = %s
                   RETURNING document""",
                (tenant_id, project_id, saved_search_id),
            )
            row = await cursor.fetchone()
        return SavedSearch.model_validate(row[0]) if row else None

    async def create_run_idempotent(
        self,
        run: RunRecord,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[RunRecord, bool]:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT request_hash, run_id FROM scenara_idempotency_keys
                   WHERE tenant_id = %s AND project_id = %s AND idempotency_key = %s FOR UPDATE""",
                (run.tenant_id, run.project_id, idempotency_key),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                if existing[0] != request_hash:
                    raise StateConflict("idempotency key was already used for a different request")
                cursor = await conn.execute(
                    """SELECT document FROM scenara_runs
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                    (run.tenant_id, run.project_id, existing[1]),
                )
                stored = await cursor.fetchone()
                if stored is None:
                    raise StateConflict("idempotent run is missing")
                return RunRecord.model_validate(stored[0]), False
            try:
                await conn.execute(
                    """INSERT INTO scenara_runs
                       (tenant_id, project_id, run_id, domain, status, revision, priority,
                        created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        run.tenant_id,
                        run.project_id,
                        run.run_id,
                        run.domain,
                        run.status,
                        run.revision,
                        run.priority,
                        run.created_at,
                        run.updated_at,
                        Jsonb(run.model_dump(mode="json")),
                    ),
                )
                await conn.execute(
                    """INSERT INTO scenara_idempotency_keys
                       (tenant_id, project_id, idempotency_key, request_hash, run_id, created_at)
                       VALUES (%s, %s, %s, %s, %s, now())""",
                    (run.tenant_id, run.project_id, idempotency_key, request_hash, run.run_id),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("run already exists") from exc
                raise
            return run.model_copy(deep=True), True

    async def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None:
        row = await self._get_document("scenara_runs", "run_id", tenant_id, project_id, run_id)
        return RunRecord.model_validate(row) if row else None

    async def get_runs(self, tenant_id: str, project_id: str, run_ids: Sequence[str]) -> list[RunRecord]:
        if not run_ids:
            return []
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = ANY(%s)""",
                (tenant_id, project_id, list(run_ids)),
            )
            rows = await cursor.fetchall()
        return [RunRecord.model_validate(row[0]) for row in rows]

    async def list_runs(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: RunStatus | None = None,
        domain: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[RunRecord]:
        conditions = ["tenant_id = %s", "project_id = %s"]
        parameters: list[Any] = [tenant_id, project_id]
        if status is not None:
            conditions.append("status = %s")
            parameters.append(status.value)
        if domain is not None:
            conditions.append("domain = %s")
            parameters.append(domain)
        query = f"""SELECT document FROM scenara_runs
                    WHERE {" AND ".join(conditions)}
                    ORDER BY created_at DESC, run_id DESC"""
        if limit is not None:
            query += " LIMIT %s"
            parameters.append(limit)
        if offset:
            query += " OFFSET %s"
            parameters.append(offset)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(query, parameters)
            rows = await cursor.fetchall()
        return [RunRecord.model_validate(row[0]) for row in rows]

    async def count_runs(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: RunStatus | None = None,
        domain: str | None = None,
    ) -> int:
        conditions = ["tenant_id = %s", "project_id = %s"]
        parameters: list[Any] = [tenant_id, project_id]
        if status is not None:
            conditions.append("status = %s")
            parameters.append(status.value)
        if domain is not None:
            conditions.append("domain = %s")
            parameters.append(domain)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT count(*) FROM scenara_runs WHERE {' AND '.join(conditions)}",
                parameters,
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def recoverable_runs(self) -> list[RunRecord]:
        terminal_statuses = sorted(status.value for status in TERMINAL_RUN_STATUSES)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_runs
                   WHERE status NOT IN (%s, %s, %s)
                   ORDER BY created_at ASC, run_id ASC""",
                terminal_statuses,
            )
            rows = await cursor.fetchall()
        return [RunRecord.model_validate(row[0]) for row in rows]

    async def has_non_terminal_run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        asset_id: str | None = None,
        source_id: str | None = None,
    ) -> bool:
        if (asset_id is None) == (source_id is None):
            raise ValueError("exactly one of asset_id or source_id is required")
        reference_field = "asset_id" if asset_id is not None else "source_id"
        reference_id = asset_id if asset_id is not None else source_id
        terminal_statuses = sorted(status.value for status in TERMINAL_RUN_STATUSES)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT EXISTS (
                    SELECT 1 FROM scenara_runs
                    WHERE tenant_id = %s AND project_id = %s
                      AND status NOT IN (%s, %s, %s)
                      AND document ->> '{reference_field}' = %s
                )""",
                (tenant_id, project_id, *terminal_statuses, reference_id),
            )
            row = await cursor.fetchone()
        return bool(row[0])

    async def delete_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s RETURNING document""",
                (tenant_id, project_id, run_id),
            )
            row = await cursor.fetchone()
        return RunRecord.model_validate(row[0]) if row else None

    async def save_run(self, run: RunRecord, *, expected_revision: int) -> RunRecord:
        from psycopg.types.json import Jsonb

        saved = run.model_copy(update={"revision": expected_revision + 1}, deep=True)
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_runs
                   SET status = %s, revision = %s, updated_at = to_timestamp(%s), document = %s
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND revision = %s""",
                (
                    saved.status,
                    saved.revision,
                    saved.updated_at,
                    Jsonb(saved.model_dump(mode="json")),
                    saved.tenant_id,
                    saved.project_id,
                    saved.run_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise StateConflict("run revision conflict")
        return saved

    async def append_event(self, tenant_id: str, project_id: str, event: RunEvent) -> RunEvent:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """SELECT revision FROM scenara_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s FOR UPDATE""",
                (tenant_id, project_id, event.run_id),
            )
            cursor = await conn.execute(
                """SELECT COALESCE(MAX(event_id), 0) + 1 FROM scenara_run_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (tenant_id, project_id, event.run_id),
            )
            next_id = int((await cursor.fetchone())[0])
            stored = event.model_copy(update={"event_id": next_id}, deep=True)
            await conn.execute(
                """INSERT INTO scenara_run_events
                   (tenant_id, project_id, run_id, event_id, event_type, status, created_at, payload, document)
                   VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s)""",
                (
                    tenant_id,
                    project_id,
                    stored.run_id,
                    stored.event_id,
                    stored.event_type,
                    stored.status,
                    stored.created_at,
                    Jsonb(stored.payload),
                    Jsonb(stored.model_dump(mode="json")),
                ),
            )
            cursor = await conn.execute(
                """SELECT document FROM scenara_webhook_subscriptions
                   WHERE tenant_id = %s AND project_id = %s AND enabled
                     AND %s = ANY(event_types)""",
                (tenant_id, project_id, stored.event_type),
            )
            for row in await cursor.fetchall():
                endpoint = WebhookSubscription.model_validate(row[0])
                delivery = WebhookDeliveryRecord(
                    delivery_id=f"whd_{uuid4().hex}",
                    tenant_id=tenant_id,
                    project_id=project_id,
                    endpoint_id=endpoint.endpoint_id,
                    event_id=f"{stored.run_id}:{stored.event_id}",
                    event_type=stored.event_type,
                    payload=stored.model_dump(mode="json"),
                    next_attempt_at=stored.created_at,
                    created_at=stored.created_at,
                    updated_at=stored.created_at,
                )
                await conn.execute(
                    """INSERT INTO scenara_webhook_deliveries
                       (tenant_id, project_id, delivery_id, endpoint_id, event_id, event_type,
                        status, attempts, next_attempt_at, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s),
                               to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        delivery.tenant_id,
                        delivery.project_id,
                        delivery.delivery_id,
                        delivery.endpoint_id,
                        delivery.event_id,
                        delivery.event_type,
                        delivery.status,
                        delivery.attempts,
                        delivery.next_attempt_at,
                        delivery.created_at,
                        delivery.updated_at,
                        Jsonb(delivery.model_dump(mode="json")),
                    ),
                )
        return stored

    async def enqueue_webhook_event(
        self,
        tenant_id: str,
        project_id: str,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, object],
        created_at: float,
    ) -> None:
        from psycopg.types.json import Jsonb
        envelope_payload = dict(payload)
        envelope_payload.setdefault("tenant_id", tenant_id)
        envelope_payload.setdefault("project_id", project_id)
        envelope_payload.setdefault("producer", "scenara")
        envelope_payload.setdefault("event_version", "1.0")

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """SELECT document FROM scenara_webhook_subscriptions
                   WHERE tenant_id = %s AND project_id = %s AND enabled
                     AND %s = ANY(event_types)""",
                (tenant_id, project_id, event_type),
            )
            for row in await cursor.fetchall():
                endpoint = WebhookSubscription.model_validate(row[0])
                delivery = WebhookDeliveryRecord(
                    delivery_id=f"whd_{uuid4().hex}",
                    tenant_id=tenant_id,
                    project_id=project_id,
                    endpoint_id=endpoint.endpoint_id,
                    event_id=event_id,
                    event_type=event_type,
                    payload=envelope_payload,
                    next_attempt_at=created_at,
                    created_at=created_at,
                    updated_at=created_at,
                )
                await conn.execute(
                    """INSERT INTO scenara_webhook_deliveries
                       (tenant_id, project_id, delivery_id, endpoint_id, event_id, event_type,
                        status, attempts, next_attempt_at, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s),
                               to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        delivery.tenant_id,
                        delivery.project_id,
                        delivery.delivery_id,
                        delivery.endpoint_id,
                        delivery.event_id,
                        delivery.event_type,
                        delivery.status,
                        delivery.attempts,
                        delivery.next_attempt_at,
                        delivery.created_at,
                        delivery.updated_at,
                        Jsonb(delivery.model_dump(mode="json")),
                    ),
                )

    async def events_after(self, tenant_id: str, project_id: str, run_id: str, event_id: int) -> list[RunEvent]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_run_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND event_id > %s
                   ORDER BY event_id ASC""",
                (tenant_id, project_id, run_id, event_id),
            )
            rows = await cursor.fetchall()
        return [RunEvent.model_validate(row[0]) for row in rows]

    async def save_result_reference(self, tenant_id: str, project_id: str, result: ResultReference) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_run_results
                   (tenant_id, project_id, run_id, domain, schema_version, object_key, sha256,
                    unit_count, created_at, summary)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)
                   ON CONFLICT (tenant_id, project_id, run_id) DO UPDATE SET
                     domain = EXCLUDED.domain, schema_version = EXCLUDED.schema_version,
                     object_key = EXCLUDED.object_key, sha256 = EXCLUDED.sha256,
                     unit_count = EXCLUDED.unit_count, created_at = EXCLUDED.created_at, summary = EXCLUDED.summary""",
                (
                    tenant_id,
                    project_id,
                    result.run_id,
                    result.domain,
                    result.schema_version,
                    result.object_key,
                    result.sha256,
                    result.unit_count,
                    result.created_at,
                    Jsonb(result.model_dump(mode="json")),
                ),
            )

    async def append_audit(self, event: AuditEvent) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                """INSERT INTO scenara_audit_events
                   (tenant_id, project_id, principal_id, action, resource_type, resource_id,
                    outcome, request_id, evidence, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s))""",
                (
                    event.tenant_id,
                    event.project_id,
                    event.principal_id,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.outcome,
                    event.request_id,
                    Jsonb(event.evidence),
                    event.created_at,
                ),
            )

    async def append_external_event_audit(self, event: AuditEvent, payload_hash: str) -> bool:
        from psycopg.types.json import Jsonb

        event_id = str(event.evidence.get("event_id", ""))
        async with self._pool.connection() as conn, conn.transaction():
            inserted = await conn.execute(
                """
                INSERT INTO scenara_external_events
                    (tenant_id, project_id, event_id, payload_hash, received_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (tenant_id, project_id, event_id) DO NOTHING
                RETURNING event_id
                """,
                (event.tenant_id, event.project_id, event_id, payload_hash),
            )
            if await inserted.fetchone() is None:
                existing = await conn.execute(
                    """
                    SELECT payload_hash FROM scenara_external_events
                    WHERE tenant_id = %s AND project_id = %s AND event_id = %s
                    """,
                    (event.tenant_id, event.project_id, event_id),
                )
                row = await existing.fetchone()
                if row is None or str(row[0]) != payload_hash:
                    raise StateConflict("external event id was reused with different content")
                return False
            await conn.execute(
                """INSERT INTO scenara_audit_events
                   (tenant_id, project_id, principal_id, action, resource_type, resource_id,
                    outcome, request_id, evidence, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s))""",
                (
                    event.tenant_id,
                    event.project_id,
                    event.principal_id,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.outcome,
                    event.request_id,
                    Jsonb(event.evidence),
                    event.created_at,
                ),
            )
            return True

    async def audit_events(
        self,
        tenant_id: str,
        project_id: str,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        principal_id: str | None = None,
        outcome: str | None = None,
        created_after: float | None = None,
        created_before: float | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[AuditEvent]:
        clauses = ["tenant_id = %s", "project_id = %s"]
        params: list[object] = [tenant_id, project_id]
        for column, value in (
            ("action", action),
            ("resource_type", resource_type),
            ("principal_id", principal_id),
            ("outcome", outcome),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(value)
        if created_after is not None:
            clauses.append("created_at >= to_timestamp(%s)")
            params.append(created_after)
        if created_before is not None:
            clauses.append("created_at <= to_timestamp(%s)")
            params.append(created_before)
        params.extend([offset])
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT %s"
            params.append(limit)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT audit_id, principal_id, action, resource_type, resource_id, outcome,
                          request_id, evidence, extract(epoch from created_at)
                   FROM scenara_audit_events
                   WHERE {' AND '.join(clauses)} ORDER BY audit_id DESC
                   OFFSET %s{limit_sql}""",
                tuple(params),
            )
            rows = await cursor.fetchall()
        return [
            AuditEvent(
                event_id=f"aud_{row[0]}",
                tenant_id=tenant_id,
                project_id=project_id,
                principal_id=row[1],
                action=row[2],
                resource_type=row[3],
                resource_id=row[4],
                outcome=row[5],
                request_id=row[6],
                evidence=row[7],
                created_at=row[8],
            )
            for row in rows
        ]

    async def count_audit_events(
        self,
        tenant_id: str,
        project_id: str,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        principal_id: str | None = None,
        outcome: str | None = None,
        created_after: float | None = None,
        created_before: float | None = None,
    ) -> int:
        clauses = ["tenant_id = %s", "project_id = %s"]
        params: list[object] = [tenant_id, project_id]
        for column, value in (
            ("action", action),
            ("resource_type", resource_type),
            ("principal_id", principal_id),
            ("outcome", outcome),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(value)
        if created_after is not None:
            clauses.append("created_at >= to_timestamp(%s)")
            params.append(created_after)
        if created_before is not None:
            clauses.append("created_at <= to_timestamp(%s)")
            params.append(created_before)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT count(*) FROM scenara_audit_events WHERE {' AND '.join(clauses)}",
                tuple(params),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def delete_audit_events_before(self, tenant_id: str, project_id: str, before: float) -> int:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                (
                    "DELETE FROM scenara_audit_events "
                    "WHERE tenant_id = %s AND project_id = %s "
                    "AND created_at < to_timestamp(%s)"
                ),
                (tenant_id, project_id, before),
            )
        return int(cursor.rowcount)

    async def track_object(self, record: ObjectRetentionRecord) -> None:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """INSERT INTO scenara_object_retention
                   (tenant_id, project_id, object_key, category, owner_type, owner_id,
                    created_at, expires_at, deleted_at)
                   VALUES (%s, %s, %s, %s, %s, %s,
                           to_timestamp(%s), to_timestamp(%s::double precision), to_timestamp(%s::double precision))
                   ON CONFLICT (tenant_id, project_id, object_key) DO NOTHING""",
                (
                    record.tenant_id,
                    record.project_id,
                    record.object_key,
                    record.category,
                    record.owner_type,
                    record.owner_id,
                    record.created_at,
                    record.expires_at,
                    record.deleted_at,
                ),
            )
            if cursor.rowcount != 1:
                raise StateConflict("object retention record already exists")

    async def protect_object_for_alert(
        self,
        tenant_id: str,
        project_id: str,
        object_key: str,
        alert_id: str,
        expires_at: float,
    ) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_object_retention
                   SET category = 'alert_snapshot', owner_type = 'surveillance_alert', owner_id = %s,
                       expires_at = GREATEST(COALESCE(expires_at, '-infinity'::timestamptz), to_timestamp(%s))
                   WHERE tenant_id = %s AND project_id = %s AND object_key = %s AND deleted_at IS NULL""",
                (alert_id, expires_at, tenant_id, project_id, object_key),
            )
        return int(cursor.rowcount) == 1

    async def expired_object_keys(self, before: float, limit: int) -> list[str]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT object_key FROM scenara_object_retention
                   WHERE expires_at IS NOT NULL AND expires_at <= to_timestamp(%s) AND deleted_at IS NULL
                   ORDER BY expires_at ASC, object_key ASC LIMIT %s""",
                (before, limit),
            )
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def mark_objects_deleted(self, object_keys: list[str], deleted_at: float) -> None:
        from psycopg.types.json import Jsonb

        if not object_keys:
            return
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_object_retention SET deleted_at = to_timestamp(%s)
                   WHERE object_key = ANY(%s) AND deleted_at IS NULL
                   RETURNING tenant_id, project_id, category, owner_type, owner_id""",
                (deleted_at, object_keys),
            )
            owners = await cursor.fetchall()
            asset_categories: dict[tuple[str, str, str], set[str]] = {}
            run_result_owners: set[tuple[str, str, str]] = set()
            for tenant_id, project_id, category, owner_type, owner_id in set(owners):
                if owner_type == "media_asset":
                    asset_categories.setdefault((tenant_id, project_id, owner_id), set()).add(category)
                if owner_type == "run_result":
                    run_result_owners.add((tenant_id, project_id, owner_id))
            if run_result_owners:
                tenants = [key[0] for key in run_result_owners]
                projects = [key[1] for key in run_result_owners]
                owner_ids = [key[2] for key in run_result_owners]
                cursor = await conn.execute(
                    """SELECT tenant_id, project_id, owner_id
                       FROM scenara_object_retention
                       WHERE owner_type = 'run_result' AND deleted_at IS NULL
                         AND (tenant_id, project_id, owner_id) IN (
                             SELECT unnest(%s::text[]), unnest(%s::text[]), unnest(%s::text[]))""",
                    (tenants, projects, owner_ids),
                )
                remaining = {(row[0], row[1], row[2]) for row in await cursor.fetchall()}
                to_delete = [key for key in run_result_owners if key not in remaining]
                if to_delete:
                    await conn.execute(
                        """DELETE FROM scenara_run_results
                           WHERE (tenant_id, project_id, run_id) IN (
                               SELECT unnest(%s::text[]), unnest(%s::text[]), unnest(%s::text[]))""",
                        (
                            [key[0] for key in to_delete],
                            [key[1] for key in to_delete],
                            [key[2] for key in to_delete],
                        ),
                    )
            if asset_categories:
                tenants = [key[0] for key in asset_categories]
                projects = [key[1] for key in asset_categories]
                asset_ids = [key[2] for key in asset_categories]
                cursor = await conn.execute(
                    """SELECT tenant_id, project_id, asset_id, document FROM scenara_media_assets
                       WHERE (tenant_id, project_id, asset_id) IN (
                           SELECT unnest(%s::text[]), unnest(%s::text[]), unnest(%s::text[]))
                       FOR UPDATE""",
                    (tenants, projects, asset_ids),
                )
                assets = {
                    (row[0], row[1], row[2]): MediaAsset.model_validate(row[3])
                    for row in await cursor.fetchall()
                }
                for key, categories in asset_categories.items():
                    asset = assets.get(key)
                    if asset is None:
                        continue
                    tenant_id, project_id, asset_id = key
                    updates: dict[str, object] = {}
                    if "raw_media" in categories:
                        updates["original_deleted_at"] = deleted_at
                    if "preview" in categories:
                        updates.update(
                            {
                                "preview_object_key": None,
                                "preview_content_type": None,
                                "preview_sha256": None,
                            }
                        )
                        if "raw_media" in categories or asset.original_deleted_at is not None:
                            updates["deleted_at"] = deleted_at
                    updated = asset.model_copy(update=updates)
                    await conn.execute(
                        """UPDATE scenara_media_assets SET document = %s
                           WHERE tenant_id = %s AND project_id = %s AND asset_id = %s""",
                        (Jsonb(updated.model_dump(mode="json")), tenant_id, project_id, asset_id),
                    )

    async def get_result_reference(self, tenant_id: str, project_id: str, run_id: str) -> ResultReference | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT summary FROM scenara_run_results
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (tenant_id, project_id, run_id),
            )
            row = await cursor.fetchone()
        return ResultReference.model_validate(row[0]) if row else None

    async def list_result_references(
        self,
        tenant_id: str,
        project_id: str,
        *,
        domain: str | None = None,
        media_kind: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ResultReference]:
        clauses = ["tenant_id = %s", "project_id = %s"]
        parameters: list[Any] = [tenant_id, project_id]
        if domain:
            clauses.append("domain = %s")
            parameters.append(domain)
        if media_kind:
            clauses.append("summary->>'media_kind' = %s")
            parameters.append(media_kind)
        if query:
            clauses.append(
                "(lower(coalesce(summary->>'resource_name', '')) LIKE lower(%s) "
                "OR run_id ILIKE %s "
                "OR coalesce(summary->>'asset_id', '') ILIKE %s "
                "OR coalesce(summary->>'source_id', '') ILIKE %s)"
            )
            search = f"%{query}%"
            parameters.extend([search, search, search, search])
        query_sql = (
            "SELECT summary FROM scenara_run_results WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, run_id DESC"
        )
        if limit is not None:
            query_sql += " LIMIT %s"
            parameters.append(limit)
        if offset:
            query_sql += " OFFSET %s"
            parameters.append(offset)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(query_sql, parameters)
            rows = await cursor.fetchall()
        return [ResultReference.model_validate(row[0]) for row in rows]

    async def count_result_references(
        self,
        tenant_id: str,
        project_id: str,
        *,
        domain: str | None = None,
        media_kind: str | None = None,
        query: str | None = None,
    ) -> int:
        clauses = ["tenant_id = %s", "project_id = %s"]
        parameters: list[Any] = [tenant_id, project_id]
        if domain:
            clauses.append("domain = %s")
            parameters.append(domain)
        if media_kind:
            clauses.append("summary->>'media_kind' = %s")
            parameters.append(media_kind)
        if query:
            clauses.append(
                "(lower(coalesce(summary->>'resource_name', '')) LIKE lower(%s) "
                "OR run_id ILIKE %s "
                "OR coalesce(summary->>'asset_id', '') ILIKE %s "
                "OR coalesce(summary->>'source_id', '') ILIKE %s)"
            )
            search = f"%{query}%"
            parameters.extend([search, search, search, search])
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT count(*) FROM scenara_run_results WHERE " + " AND ".join(clauses),
                parameters,
            )
            row = await cursor.fetchone()
        return int(row[0])

    async def _insert_document(self, table: str, id_column: str, value_id: str, model: Any) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    f"""INSERT INTO {table} (tenant_id, project_id, {id_column}, created_at, document)
                        VALUES (%s, %s, %s, to_timestamp(%s), %s)""",
                    (
                        model.tenant_id,
                        model.project_id,
                        value_id,
                        model.created_at,
                        Jsonb(model.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise StateConflict("record already exists") from exc
                raise

    async def _get_document(
        self,
        table: str,
        id_column: str,
        tenant_id: str,
        project_id: str,
        value_id: str,
    ) -> dict[str, Any] | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT document FROM {table}
                    WHERE tenant_id = %s AND project_id = %s AND {id_column} = %s""",
                (tenant_id, project_id, value_id),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def _list_documents(
        self,
        table: str,
        id_column: str,
        tenant_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT document FROM {table}
                    WHERE tenant_id = %s AND project_id = %s ORDER BY created_at DESC, {id_column} DESC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [row[0] for row in rows]


__all__ = ["PostgresStateStore"]
