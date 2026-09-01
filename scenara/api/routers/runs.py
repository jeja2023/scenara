from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from scenara.bootstrap import Runtime
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    ApiEnvelope,
    CreateRunRequest,
    DomainId,
    MediaKind,
    PrincipalContext,
    ResultPage,
    ResultSummaryPage,
    RunPage,
    RunRecord,
    RunStatus,
    StreamSessionView,
)
from scenara.platform.services import sse_payload

EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_runs_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/runs", status_code=202, tags=["Runs"])
    async def create_run(
        body: CreateRunRequest,
        request: Request,
        response: Response,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        outcome = await runtime.runs.create_run(
            context, body, idempotency_key=idempotency_key
        )
        response.status_code = 202 if outcome.created else 200
        return envelope(request, outcome.run)

    @router.get("/api/v1/runs", tags=["Runs"])
    async def list_runs(
        request: Request,
        run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
        domain: DomainId | None = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunPage]:
        items, total = await runtime.runs.list_runs(
            context,
            status=run_status,
            domain=domain,
            offset=offset,
            limit=limit,
        )
        return envelope(
            request, RunPage(items=items, offset=offset, limit=limit, total=total)
        )

    @router.get("/api/v1/runs/{run_id}", tags=["Runs"])
    async def get_run(
        run_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        return envelope(request, await runtime.runs.get_run(context, run_id))

    @router.get("/api/v1/stream-sessions/{session_id}", tags=["Runs"])
    async def get_stream_session(
        session_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[StreamSessionView]:
        return envelope(request, await runtime.runs.stream_session(context, session_id))

    @router.post("/api/v1/stream-sessions/{session_id}/cancel", tags=["Runs"])
    async def cancel_stream_session(
        session_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[StreamSessionView]:
        return envelope(
            request, await runtime.runs.cancel_stream_session(context, session_id)
        )

    async def lifecycle(
        run_id: str, action: str, request: Request, context: PrincipalContext
    ) -> ApiEnvelope[RunRecord]:
        return envelope(request, await runtime.runs.transition(context, run_id, action))

    @router.post("/api/v1/runs/{run_id}/cancel", tags=["Runs"])
    async def cancel_run(
        run_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "cancel", request, context)

    @router.post("/api/v1/runs/{run_id}/pause", tags=["Runs"])
    async def pause_run(
        run_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "pause", request, context)

    @router.post("/api/v1/runs/{run_id}/resume", tags=["Runs"])
    async def resume_run(
        run_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[RunRecord]:
        return await lifecycle(run_id, "resume", request, context)

    @router.get("/api/v1/runs/{run_id}/result", tags=["Results"])
    async def get_result(
        run_id: str,
        request: Request,
        unit_offset: Annotated[int, Query(ge=0)] = 0,
        unit_limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ResultPage]:
        page = await runtime.runs.result_page(
            context,
            run_id,
            unit_offset=unit_offset,
            unit_limit=unit_limit,
        )
        return envelope(request, page)

    @router.get("/api/v1/results", tags=["Results"])
    async def list_results(
        request: Request,
        domain: DomainId | None = None,
        media_kind: MediaKind | None = None,
        query: Annotated[str | None, Query(max_length=256)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ResultSummaryPage]:
        items, total = await runtime.runs.list_results(
            context,
            domain=domain,
            media_kind=media_kind,
            query=query.strip() if query else None,
            offset=offset,
            limit=limit,
        )
        return envelope(
            request,
            ResultSummaryPage(items=items, offset=offset, limit=limit, total=total),
        )

    @router.get("/api/v1/runs/{run_id}/artifacts/{artifact_id}", tags=["Results"])
    async def get_result_artifact(
        run_id: str,
        artifact_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        """Return one derived image declared by the run result.

        Feature crops (``crop_artifact_id`` on an object) and unit frames
        (``frame_artifact_id`` on a media unit) are served from here.
        """
        data, content_type, sha256 = await runtime.runs.result_artifact(
            context, run_id, artifact_id
        )
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "ETag": f'"sha256:{sha256}"',
                "Cache-Control": "private, max-age=300",
            },
        )

    @router.get("/api/v1/runs/{run_id}/events", tags=["Runs"])
    async def run_events(
        run_id: str,
        request: Request,
        last_event_id_header: Annotated[
            int | None, Header(alias="Last-Event-ID")
        ] = None,
        last_event_id: Annotated[int, Query(ge=0)] = 0,
        context: PrincipalContext = Depends(principal_context),
    ) -> StreamingResponse:
        await runtime.runs.get_run(context, run_id)
        cursor = (
            last_event_id_header if last_event_id_header is not None else last_event_id
        )

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            heartbeat_at = asyncio.get_running_loop().time() + 15
            while True:
                if await request.is_disconnected():
                    return
                events = await runtime.state.events_after(
                    context.tenant_id, context.project_id, run_id, cursor
                )
                for event in events:
                    cursor = event.event_id
                    yield sse_payload(event)
                run = await runtime.runs.get_run(context, run_id)
                if run.status in TERMINAL_RUN_STATUSES and not events:
                    return
                now = asyncio.get_running_loop().time()
                if now >= heartbeat_at:
                    yield ": heartbeat\n\n"
                    heartbeat_at = now + 15
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return router


__all__ = ["build_runs_router"]
