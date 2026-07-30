from __future__ import annotations

from typing import Any

from scenara.enterprise.service import (
    ComplianceEvidence,
    EnterpriseRepository,
    Incident,
    SupportCase,
)
from scenara.platform.policy import PolicyDenied


class PostgresEnterpriseRepository(EnterpriseRepository):
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def consume_usage(
        self,
        tenant_id: str,
        metric: str,
        amount: int,
        limit: int | None,
    ) -> int:
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """INSERT INTO scenara_enterprise_usage (tenant_id, metric, used, updated_at)
                   VALUES (%s, %s, %s, now())
                   ON CONFLICT (tenant_id, metric) DO UPDATE SET
                     used = scenara_enterprise_usage.used + EXCLUDED.used,
                     updated_at = now()
                   WHERE %s IS NULL OR scenara_enterprise_usage.used + EXCLUDED.used <= %s
                   RETURNING used""",
                (tenant_id, metric, amount, limit, limit),
            )
            row = await cursor.fetchone()
        if row is None:
            raise PolicyDenied(f"enterprise quota exceeded: {metric}")
        return int(row[0])

    async def usage(self, tenant_id: str) -> dict[str, int]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT metric, used FROM scenara_enterprise_usage WHERE tenant_id = %s",
                (tenant_id,),
            )
            rows = await cursor.fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    async def create_incident(self, incident: Incident) -> Incident:
        await self._create_record("incident", incident.incident_id, incident)
        return incident.model_copy(deep=True)

    async def get_incident(
        self,
        tenant_id: str,
        project_id: str,
        incident_id: str,
    ) -> Incident | None:
        row = await self._get_record(tenant_id, project_id, "incident", incident_id)
        return Incident.model_validate(row) if row else None

    async def save_incident(self, incident: Incident) -> Incident:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """UPDATE scenara_enterprise_records
                   SET updated_at = to_timestamp(%s), document = %s
                   WHERE tenant_id = %s AND project_id = %s
                     AND record_type = 'incident' AND record_id = %s""",
                (
                    incident.updated_at,
                    Jsonb(incident.model_dump(mode="json")),
                    incident.tenant_id,
                    incident.project_id,
                    incident.incident_id,
                ),
            )
        if int(cursor.rowcount) != 1:
            raise ValueError("incident does not exist")
        return incident.model_copy(deep=True)

    async def list_incidents(self, tenant_id: str, project_id: str) -> list[Incident]:
        rows = await self._list_records(tenant_id, project_id, "incident")
        return [Incident.model_validate(row) for row in rows]

    async def create_support_case(self, case: SupportCase) -> SupportCase:
        await self._create_record("support_case", case.case_id, case)
        return case.model_copy(deep=True)

    async def list_support_cases(self, tenant_id: str, project_id: str) -> list[SupportCase]:
        rows = await self._list_records(tenant_id, project_id, "support_case")
        return [SupportCase.model_validate(row) for row in rows]

    async def create_evidence(self, evidence: ComplianceEvidence) -> ComplianceEvidence:
        await self._create_record("compliance_evidence", evidence.evidence_id, evidence)
        return evidence.model_copy(deep=True)

    async def list_evidence(self, tenant_id: str, project_id: str) -> list[ComplianceEvidence]:
        rows = await self._list_records(tenant_id, project_id, "compliance_evidence")
        return [ComplianceEvidence.model_validate(row) for row in rows]

    async def _create_record(self, record_type: str, record_id: str, model: Any) -> None:
        from psycopg.types.json import Jsonb

        async with self._pool.connection() as conn, conn.transaction():
            try:
                await conn.execute(
                    """INSERT INTO scenara_enterprise_records
                       (tenant_id, project_id, record_type, record_id, created_at, updated_at, document)
                       VALUES (%s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s)""",
                    (
                        model.tenant_id,
                        model.project_id,
                        record_type,
                        record_id,
                        model.created_at,
                        model.updated_at if hasattr(model, "updated_at") else model.created_at,
                        Jsonb(model.model_dump(mode="json")),
                    ),
                )
            except Exception as exc:
                if exc.__class__.__name__ in {"UniqueViolation", "IntegrityError"}:
                    raise ValueError(f"{record_type} already exists") from exc
                raise

    async def _get_record(
        self,
        tenant_id: str,
        project_id: str,
        record_type: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_enterprise_records
                   WHERE tenant_id = %s AND project_id = %s
                     AND record_type = %s AND record_id = %s""",
                (tenant_id, project_id, record_type, record_id),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def _list_records(
        self,
        tenant_id: str,
        project_id: str,
        record_type: str,
    ) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT document FROM scenara_enterprise_records
                   WHERE tenant_id = %s AND project_id = %s AND record_type = %s
                   ORDER BY created_at DESC, record_id DESC""",
                (tenant_id, project_id, record_type),
            )
            rows = await cursor.fetchall()
        return [row[0] for row in rows]


__all__ = ["PostgresEnterpriseRepository"]
