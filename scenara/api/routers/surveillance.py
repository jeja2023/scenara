from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from scenara.bootstrap import Runtime
from scenara.platform.models import ApiEnvelope, PrincipalContext
from scenara.platform.surveillance import (
    AlertPage,
    AlertRecord,
    AlertStatus,
    CreateAlertFeedbackRequest,
    CreateSurveillanceTaskRequest,
    CreateWatchlistMemberRequest,
    CreateWatchlistRequest,
    SurveillanceConflict,
    SurveillanceTask,
    SurveillanceTaskPage,
    TriageAlertRequest,
    UpdateSurveillanceTaskRequest,
    UpdateWatchlistMemberRequest,
    UpdateWatchlistRequest,
    Watchlist,
    WatchlistMember,
    WatchlistMemberPage,
    WatchlistPage,
)
from scenara.platform.feedback import (
    CreateFeedbackRequest,
    FeedbackKind,
    FeedbackRecord,
)

EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_surveillance_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v1/surveillance/watchlists", status_code=201, tags=["Surveillance"]
    )
    async def create_surveillance_watchlist(
        body: CreateWatchlistRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Watchlist]:
        return envelope(
            request, await runtime.surveillance.create_watchlist(context, body)
        )

    @router.get("/api/v1/surveillance/watchlists", tags=["Surveillance"])
    async def list_surveillance_watchlists(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistPage]:
        return envelope(
            request,
            await runtime.surveillance.list_watchlists(
                context, offset=offset, limit=limit
            ),
        )

    @router.get("/api/v1/surveillance/watchlists/{watchlist_id}", tags=["Surveillance"])
    async def get_surveillance_watchlist(
        watchlist_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Watchlist]:
        return envelope(
            request, await runtime.surveillance.get_watchlist(context, watchlist_id)
        )

    @router.patch(
        "/api/v1/surveillance/watchlists/{watchlist_id}", tags=["Surveillance"]
    )
    async def update_surveillance_watchlist(
        watchlist_id: str,
        body: UpdateWatchlistRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[Watchlist]:
        return envelope(
            request,
            await runtime.surveillance.update_watchlist(context, watchlist_id, body),
        )

    @router.delete(
        "/api/v1/surveillance/watchlists/{watchlist_id}",
        status_code=204,
        tags=["Surveillance"],
    )
    async def delete_surveillance_watchlist(
        watchlist_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.surveillance.delete_watchlist(context, watchlist_id)
        return Response(status_code=204)

    @router.post(
        "/api/v1/surveillance/watchlists/{watchlist_id}/members",
        status_code=201,
        tags=["Surveillance"],
    )
    async def create_surveillance_watchlist_member(
        watchlist_id: str,
        body: CreateWatchlistMemberRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistMember]:
        return envelope(
            request,
            await runtime.surveillance.create_member(context, watchlist_id, body),
        )

    @router.get(
        "/api/v1/surveillance/watchlists/{watchlist_id}/members", tags=["Surveillance"]
    )
    async def list_surveillance_watchlist_members(
        watchlist_id: str,
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistMemberPage]:
        page = await runtime.surveillance.list_members(
            context, watchlist_id, offset=offset, limit=limit
        )
        return envelope(request, page)

    @router.patch(
        "/api/v1/surveillance/watchlists/{watchlist_id}/members/{member_id}",
        tags=["Surveillance"],
    )
    async def update_surveillance_watchlist_member(
        watchlist_id: str,
        member_id: str,
        body: UpdateWatchlistMemberRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WatchlistMember]:
        result = await runtime.surveillance.update_member(
            context, watchlist_id, member_id, body
        )
        return envelope(request, result)

    @router.delete(
        "/api/v1/surveillance/watchlists/{watchlist_id}/members/{member_id}",
        status_code=204,
        tags=["Surveillance"],
    )
    async def delete_surveillance_watchlist_member(
        watchlist_id: str,
        member_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.surveillance.delete_member(context, watchlist_id, member_id)
        return Response(status_code=204)

    @router.post("/api/v1/surveillance/tasks", status_code=201, tags=["Surveillance"])
    async def create_surveillance_task(
        body: CreateSurveillanceTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return envelope(request, await runtime.surveillance.create_task(context, body))

    @router.get("/api/v1/surveillance/tasks", tags=["Surveillance"])
    async def list_surveillance_tasks(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTaskPage]:
        return envelope(
            request,
            await runtime.surveillance.list_tasks(context, offset=offset, limit=limit),
        )

    @router.get("/api/v1/surveillance/tasks/{task_id}", tags=["Surveillance"])
    async def get_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return envelope(request, await runtime.surveillance.get_task(context, task_id))

    @router.patch("/api/v1/surveillance/tasks/{task_id}", tags=["Surveillance"])
    async def update_surveillance_task(
        task_id: str,
        body: UpdateSurveillanceTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return envelope(
            request, await runtime.surveillance.update_task(context, task_id, body)
        )

    @router.post("/api/v1/surveillance/tasks/{task_id}/start", tags=["Surveillance"])
    async def start_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return envelope(
            request, await runtime.surveillance.start_task(context, task_id)
        )

    @router.post("/api/v1/surveillance/tasks/{task_id}/pause", tags=["Surveillance"])
    async def pause_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return envelope(
            request, await runtime.surveillance.pause_task(context, task_id)
        )

    @router.post("/api/v1/surveillance/tasks/{task_id}/resume", tags=["Surveillance"])
    async def resume_surveillance_task(
        task_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SurveillanceTask]:
        return envelope(
            request, await runtime.surveillance.resume_task(context, task_id)
        )

    @router.get("/api/v1/surveillance/alerts", tags=["Surveillance"])
    async def list_surveillance_alerts(
        request: Request,
        alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
        task_id: Annotated[str | None, Query(max_length=128)] = None,
        camera_id: Annotated[str | None, Query(max_length=128)] = None,
        watchlist_id: Annotated[str | None, Query(max_length=128)] = None,
        portrait_identity_id: Annotated[str | None, Query(max_length=128)] = None,
        since: Annotated[float | None, Query(ge=0)] = None,
        until: Annotated[float | None, Query(ge=0)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AlertPage]:
        page = await runtime.surveillance.list_alerts(
            context,
            status=alert_status,
            task_id=task_id,
            camera_id=camera_id,
            watchlist_id=watchlist_id,
            portrait_identity_id=portrait_identity_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return envelope(request, page)

    @router.get("/api/v1/surveillance/alerts/live-stream", tags=["Surveillance"])
    async def surveillance_alert_live_stream(
        request: Request,
        last_event_id_header: Annotated[
            int | None, Header(alias="Last-Event-ID")
        ] = None,
        last_event_id: Annotated[int, Query(ge=0)] = 0,
        context: PrincipalContext = Depends(principal_context),
    ) -> StreamingResponse:
        cursor = (
            last_event_id_header if last_event_id_header is not None else last_event_id
        )

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            heartbeat_at = asyncio.get_running_loop().time() + 15
            while True:
                if await request.is_disconnected():
                    return
                events = await runtime.surveillance.events_after(
                    context, cursor, limit=500
                )
                for event in events:
                    cursor = event.event_cursor
                    payload = json.dumps(
                        event.model_dump(mode="json"),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    yield f"id: {cursor}\nevent: {event.event_type}\ndata: {payload}\n\n"
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

    @router.get("/api/v1/surveillance/alerts/{alert_id}", tags=["Surveillance"])
    async def get_surveillance_alert(
        alert_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AlertRecord]:
        return envelope(
            request, await runtime.surveillance.get_alert(context, alert_id)
        )

    @router.patch(
        "/api/v1/surveillance/alerts/{alert_id}/status", tags=["Surveillance"]
    )
    async def triage_surveillance_alert(
        alert_id: str,
        body: TriageAlertRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AlertRecord]:
        return envelope(
            request, await runtime.surveillance.triage_alert(context, alert_id, body)
        )

    @router.post(
        "/api/v1/surveillance/alerts/{alert_id}/feedback",
        status_code=201,
        tags=["Surveillance"],
    )
    async def create_surveillance_alert_feedback(
        alert_id: str,
        body: CreateAlertFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FeedbackRecord]:
        alert = await runtime.surveillance.get_alert(context, alert_id)
        if alert.status != AlertStatus.FALSE_POSITIVE:
            raise SurveillanceConflict(
                "only a false-positive alert can create feedback"
            )
        binding = alert.model_bindings.get("face") or alert.model_bindings.get("body")
        if binding is None:
            raise SurveillanceConflict("alert has no model binding for feedback")
        feedback = await runtime.feedback.create(
            context,
            CreateFeedbackRequest(
                kind=FeedbackKind.FALSE_POSITIVE,
                run_id=alert.run_id,
                model_id=binding["model_id"],
                model_version=binding["model_version"],
                correction={
                    **body.correction,
                    "source": "surveillance_alert",
                    "alert_id": alert.alert_id,
                    "triage_reason": alert.triage_reason,
                    "review_outcome": "false_positive",
                },
                annotation_schema_id="scenara.portrait.surveillance-review.v1",
                authorized_for_training=False,
                deidentified=False,
            ),
        )
        return envelope(request, feedback)

    return router


__all__ = ["build_surveillance_router"]
