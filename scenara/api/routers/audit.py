from __future__ import annotations

import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any, TypedDict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse

from scenara.bootstrap import Runtime
from scenara.platform.audit import AuditEventPage, AuditEventView, audit_event_view
from scenara.platform.models import ApiEnvelope, PrincipalContext
from scenara.platform.policy import require_allowed

PrincipalDependency = Callable[..., Any]
Envelope = Callable[[Request, object], ApiEnvelope[object]]


class AuditFilters(TypedDict):
    action: str | None
    resource_type: str | None
    principal_id: str | None
    outcome: str | None
    created_after: float | None
    created_before: float | None


def build_audit_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: Envelope,
) -> APIRouter:
    router = APIRouter()

    async def query_audit_events(
        context: PrincipalContext,
        *,
        action: str | None,
        resource_type: str | None,
        principal_id: str | None,
        outcome: str | None,
        created_after: float | None,
        created_before: float | None,
        offset: int,
        limit: int | None,
    ) -> tuple[list[AuditEventView], int]:
        await require_allowed(runtime.policy, context, "read", "audit_event")
        events, total = await asyncio.gather(
            runtime.state.audit_events(
                context.tenant_id,
                context.project_id,
                action=action,
                resource_type=resource_type,
                principal_id=principal_id,
                outcome=outcome,
                created_after=created_after,
                created_before=created_before,
                offset=offset,
                limit=limit,
            ),
            runtime.state.count_audit_events(
                context.tenant_id,
                context.project_id,
                action=action,
                resource_type=resource_type,
                principal_id=principal_id,
                outcome=outcome,
                created_after=created_after,
                created_before=created_before,
            ),
        )
        return [audit_event_view(event) for event in events], total

    @router.get("/api/v1/audit/events", tags=["Operations"])
    async def list_audit_events(
        request: Request,
        action: Annotated[str | None, Query(max_length=128)] = None,
        resource_type: Annotated[str | None, Query(max_length=128)] = None,
        principal_id: Annotated[str | None, Query(max_length=128)] = None,
        outcome: Annotated[str | None, Query(max_length=32)] = None,
        created_after: Annotated[float | None, Query(ge=0)] = None,
        created_before: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AuditEventPage]:
        page, total = await query_audit_events(
            context,
            action=action,
            resource_type=resource_type,
            principal_id=principal_id,
            outcome=outcome,
            created_after=created_after,
            created_before=created_before,
            offset=offset,
            limit=limit,
        )
        return envelope(request, AuditEventPage(items=page, offset=offset, limit=limit, total=total))  # type: ignore[return-value]

    @router.get("/api/v1/audit/export", tags=["Operations"])
    async def export_audit_events(
        format: Annotated[str, Query(pattern="^(json|csv)$")] = "json",
        action: Annotated[str | None, Query(max_length=128)] = None,
        resource_type: Annotated[str | None, Query(max_length=128)] = None,
        principal_id: Annotated[str | None, Query(max_length=128)] = None,
        outcome: Annotated[str | None, Query(max_length=32)] = None,
        created_after: Annotated[float | None, Query(ge=0)] = None,
        created_before: Annotated[float | None, Query(ge=0)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await require_allowed(runtime.policy, context, "read", "audit_event")
        filters: AuditFilters = {
            "action": action,
            "resource_type": resource_type,
            "principal_id": principal_id,
            "outcome": outcome,
            "created_after": created_after,
            "created_before": created_before,
        }
        total = await runtime.state.count_audit_events(context.tenant_id, context.project_id, **filters)

        async def pages() -> AsyncIterator[list[AuditEventView]]:
            offset = 0
            page_size = 500
            while offset < total:
                events = await runtime.state.audit_events(
                    context.tenant_id,
                    context.project_id,
                    offset=offset,
                    limit=page_size,
                    **filters,
                )
                if not events:
                    return
                yield [audit_event_view(event) for event in events]
                offset += len(events)

        if format == "json":

            async def json_stream() -> AsyncIterator[str]:
                yield '{"items":['
                first = True
                async for page in pages():
                    for event in page:
                        if not first:
                            yield ","
                        first = False
                        yield json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
                yield f'],"offset":0,"limit":{total},"total":{total}}}'

            return StreamingResponse(
                json_stream(),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=scenara-audit.json"},
            )

        async def csv_stream() -> AsyncIterator[str]:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "event_id",
                    "created_at",
                    "principal_id",
                    "action",
                    "resource_type",
                    "resource_id",
                    "outcome",
                    "evidence",
                ]
            )
            yield output.getvalue()
            async for page in pages():
                output.seek(0)
                output.truncate(0)
                for event in page:
                    writer.writerow(
                        [
                            event.event_id,
                            event.created_at,
                            event.principal_id,
                            event.action,
                            event.resource_type,
                            event.resource_id or "",
                            event.outcome,
                            event.model_dump_json(include={"evidence"}),
                        ]
                    )
                yield output.getvalue()

        return StreamingResponse(
            csv_stream(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=scenara-audit.csv"},
        )

    return router
