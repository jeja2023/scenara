from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from scenara.bootstrap import Runtime
from scenara.platform.control_plane import (
    AnnotationProvider,
    AnnotationTask,
    AutoRollbackModelRequest,
    CreateAnnotationProviderRequest,
    CreateAnnotationTaskRequest,
    ModelHealthSnapshot,
    ModelMetricPoint,
    ReviewAnnotationTaskRequest,
)
from scenara.platform.models import ApiEnvelope, PrincipalContext


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_data_governance_router(
    runtime: Runtime,
    principal_context: PrincipalDependency,
    envelope: EnvelopeFactory,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/data/annotation-tasks", status_code=201, tags=["Data"])
    async def create_annotation_task(
        body: CreateAnnotationTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationTask]:
        return envelope(
            request, await runtime.data.create_annotation_task(context, body)
        )

    @router.get("/api/v1/data/annotation-tasks", tags=["Data"])
    async def list_annotation_tasks(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AnnotationTask]]:
        return envelope(request, await runtime.data.list_annotation_tasks(context))

    @router.post("/api/v1/data/annotation-providers", status_code=201, tags=["Data"])
    async def register_annotation_provider(
        body: CreateAnnotationProviderRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationProvider]:
        return envelope(
            request, await runtime.data.register_annotation_provider(context, body)
        )

    @router.get("/api/v1/data/annotation-providers", tags=["Data"])
    async def list_annotation_providers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[AnnotationProvider]]:
        return envelope(request, await runtime.data.list_annotation_providers(context))

    @router.post("/api/v1/data/annotation-providers/{provider_id}/probe", tags=["Data"])
    async def probe_annotation_provider(
        provider_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationProvider]:
        return envelope(
            request, await runtime.data.probe_annotation_provider(context, provider_id)
        )

    @router.post("/api/v1/data/annotation-tasks/{task_id}/review", tags=["Data"])
    async def review_annotation_task(
        task_id: str,
        body: ReviewAnnotationTaskRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[AnnotationTask]:
        return envelope(
            request, await runtime.data.review_annotation_task(context, task_id, body)
        )

    @router.post(
        "/api/v1/platform/model-metrics", status_code=201, tags=["Model Governance"]
    )
    async def record_model_metric(
        body: ModelMetricPoint,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelMetricPoint]:
        return envelope(
            request, await runtime.control_plane.record_model_metric(context, body)
        )

    @router.get("/api/v1/platform/model-health", tags=["Model Governance"])
    async def model_health(
        model_id: str,
        model_version: str,
        capability: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelHealthSnapshot]:
        return envelope(
            request,
            await runtime.control_plane.model_health(
                context, model_id, model_version, capability
            ),
        )

    @router.post(
        "/api/v1/platform/model-health/auto-rollback", tags=["Model Governance"]
    )
    async def auto_rollback_model(
        body: AutoRollbackModelRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[dict[str, object]]:
        health = await runtime.control_plane.model_health(
            context, body.model_id, body.model_version, body.capability
        )
        if not health.rollback_recommended:
            return envelope(request, {"rolled_back": False, "health": health})
        release = await runtime.feedback.auto_rollback(
            context,
            body.model_id,
            body.model_version,
            reason=body.reason,
        )
        return envelope(
            request, {"rolled_back": True, "health": health, "release": release}
        )

    return router


__all__ = ["build_data_governance_router"]
