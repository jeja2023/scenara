from __future__ import annotations

from typing import Any

from scenara.domains.portrait.service import (
    PortraitConflict,
    PortraitEnrollment,
    PortraitIdentity,
)


class PostgresPortraitRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_identity(self, identity: PortraitIdentity) -> PortraitIdentity:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_portrait_identities
                       (tenant_id, project_id, identity_id, display_name, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        identity.tenant_id,
                        identity.project_id,
                        identity.identity_id,
                        identity.display_name,
                        identity.created_at,
                        identity.updated_at,
                        Jsonb(identity.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise PortraitConflict("portrait identity already exists") from exc
                raise
        return identity.model_copy(deep=True)

    async def get_identity(
        self,
        tenant_id: str,
        project_id: str,
        identity_id: str,
    ) -> PortraitIdentity | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_portrait_identities
                   WHERE tenant_id = %s AND project_id = %s AND identity_id = %s""",
                (tenant_id, project_id, identity_id),
            )
            row = await cursor.fetchone()
        return PortraitIdentity.model_validate(row[0]) if row else None

    async def list_identities(self, tenant_id: str, project_id: str) -> list[PortraitIdentity]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_portrait_identities
                   WHERE tenant_id = %s AND project_id = %s
                   ORDER BY created_at DESC, identity_id DESC""",
                (tenant_id, project_id),
            )
            rows = await cursor.fetchall()
        return [PortraitIdentity.model_validate(row[0]) for row in rows]

    async def delete_identity(self, tenant_id: str, project_id: str, identity_id: str) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_portrait_identities
                   WHERE tenant_id = %s AND project_id = %s AND identity_id = %s""",
                (tenant_id, project_id, identity_id),
            )
        return int(cursor.rowcount) == 1

    async def create_enrollment(self, enrollment: PortraitEnrollment) -> PortraitEnrollment:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_portrait_enrollments
                       (tenant_id, project_id, enrollment_id, identity_id, feature_id,
                        feature_space_id, modality, quality, created_at, document)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s)""",
                    (
                        enrollment.tenant_id,
                        enrollment.project_id,
                        enrollment.enrollment_id,
                        enrollment.identity_id,
                        enrollment.feature_id,
                        enrollment.feature_space_id,
                        enrollment.modality,
                        enrollment.quality,
                        enrollment.created_at,
                        Jsonb(enrollment.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise PortraitConflict("portrait enrollment already exists") from exc
                raise
        return enrollment.model_copy(deep=True)

    async def get_enrollment_by_feature(
        self,
        tenant_id: str,
        project_id: str,
        feature_id: str,
    ) -> PortraitEnrollment | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_portrait_enrollments
                   WHERE tenant_id = %s AND project_id = %s AND feature_id = %s""",
                (tenant_id, project_id, feature_id),
            )
            row = await cursor.fetchone()
        return PortraitEnrollment.model_validate(row[0]) if row else None


__all__ = ["PostgresPortraitRepository"]
