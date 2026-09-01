from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from scenara.bootstrap import Runtime
from scenara.platform.control_plane import (
    CreatePortraitAssociationRequest,
    CreatePortraitClusterRequest,
    CreatePortraitEventRequest,
    PortraitAssociation,
    PortraitCluster,
    PortraitEvent,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_portrait_intelligence_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v1/portrait/clusters", status_code=201, tags=["Portrait Intelligence"]
    )
    async def create_portrait_cluster(
        body: CreatePortraitClusterRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitCluster]:
        return envelope(
            request, await runtime.control_plane.create_cluster(context, body)
        )

    @router.get("/api/v1/portrait/clusters", tags=["Portrait Intelligence"])
    async def list_portrait_clusters(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[PortraitCluster]]:
        return envelope(request, await runtime.control_plane.list_clusters(context))

    @router.post(
        "/api/v1/portrait/associations", status_code=201, tags=["Portrait Intelligence"]
    )
    async def create_portrait_association(
        body: CreatePortraitAssociationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitAssociation]:
        return envelope(
            request, await runtime.control_plane.create_association(context, body)
        )

    @router.get("/api/v1/portrait/associations", tags=["Portrait Intelligence"])
    async def list_portrait_associations(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[PortraitAssociation]]:
        return envelope(request, await runtime.control_plane.list_associations(context))

    @router.post(
        "/api/v1/portrait/events", status_code=201, tags=["Portrait Intelligence"]
    )
    async def create_portrait_event(
        body: CreatePortraitEventRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[PortraitEvent]:
        return envelope(
            request, await runtime.control_plane.create_event(context, body)
        )

    @router.get("/api/v1/portrait/events", tags=["Portrait Intelligence"])
    async def list_portrait_events(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[PortraitEvent]]:
        return envelope(request, await runtime.control_plane.list_events(context))

    return router


__all__ = ["build_portrait_intelligence_router"]
