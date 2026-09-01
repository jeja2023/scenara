from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from scenara.bootstrap import Runtime
from scenara.platform.feedback import (
    CreateFeedbackRequest,
    CreateHardSampleManifestRequest,
    CreateModelReleaseRequest,
    FeedbackRecord,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelRelease,
    ReviewFeedbackRequest,
    RollbackModelReleaseRequest,
    TransitionModelReleaseRequest,
)
from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import (
    ApiEnvelope,
    CreateWebhookSubscriptionRequest,
    PipelineTransitionRequest,
    PrincipalContext,
    WebhookDeliveryRecord,
    WebhookSubscriptionView,
)
from scenara.platform.policy import require_allowed
from typing import Annotated


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_feedback_router(
    runtime: Runtime, principal_context: PrincipalDependency, envelope: EnvelopeFactory
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/pipelines", tags=["Pipelines"])
    async def list_pipelines(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[dict[str, object]]]:
        await require_allowed(runtime.policy, context, "list", "pipeline")
        rows = [
            pipeline.model_dump(mode="json")
            for pipeline in await runtime.runs.sync_pipeline_catalog()
        ]
        return envelope(request, rows)

    @router.post(
        "/api/v1/pipelines/{pipeline_id}/versions/{version}/transition",
        tags=["Pipelines"],
    )
    async def transition_pipeline(
        pipeline_id: str,
        version: str,
        body: PipelineTransitionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[dict[str, object]]:
        pipeline = await runtime.runs.transition_pipeline(
            context, pipeline_id, version, body.status
        )
        return envelope(request, pipeline.model_dump(mode="json"))

    @router.post("/api/v1/feedback", status_code=201, tags=["Feedback"])
    async def create_feedback(
        body: CreateFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FeedbackRecord]:
        result = await runtime.feedback.create(context, body)
        return envelope(request, result)

    @router.get("/api/v1/feedback", tags=["Feedback"])
    async def list_feedback(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[FeedbackRecord]]:
        rows = await runtime.feedback.feedback_records(context)
        return envelope(request, rows)

    @router.post("/api/v1/feedback/{feedback_id}/review", tags=["Feedback"])
    async def review_feedback(
        feedback_id: str,
        body: ReviewFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[FeedbackRecord]:
        result = await runtime.feedback.review(context, feedback_id, body)
        return envelope(request, result)

    @router.post("/api/v1/hard-sample-manifests", status_code=201, tags=["Feedback"])
    async def create_hard_sample_manifest(
        body: CreateHardSampleManifestRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[HardSampleManifest]:
        result = await runtime.feedback.create_manifest(context, body)
        # Core owns qualification; Data owns idempotent intake and dataset construction.
        if runtime.settings.data_platform_mode == "http":
            await runtime.data.submit_hard_sample_manifest(context, result)
        return envelope(request, result)

    @router.get("/api/v1/hard-sample-manifests", tags=["Feedback"])
    async def list_hard_sample_manifests(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[HardSampleManifest]]:
        rows = await runtime.feedback.list_manifests(context)
        return envelope(request, rows)

    @router.post("/api/v1/model-releases", status_code=201, tags=["Model Governance"])
    async def create_model_release(
        body: CreateModelReleaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelRelease]:
        result = await runtime.feedback.create_release(context, body)
        return envelope(request, result)

    @router.post(
        "/api/v1/model-packages/admissions", status_code=201, tags=["Model Governance"]
    )
    async def admit_model_package(
        body: ModelPackageManifest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelPackageManifest]:
        result = await runtime.feedback.admit_package(context, body)
        return envelope(request, result)

    @router.get("/api/v1/model-releases", tags=["Model Governance"])
    async def list_model_releases(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ModelRelease]]:
        rows = await runtime.feedback.list_releases(context)
        return envelope(request, rows)

    @router.post(
        "/api/v1/model-releases/{model_id}/versions/{version}/transition",
        tags=["Model Governance"],
    )
    async def transition_model_release(
        model_id: str,
        version: str,
        body: TransitionModelReleaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelRelease]:
        result = await runtime.feedback.transition_release(
            context, model_id, version, body
        )
        return envelope(request, result)

    @router.post(
        "/api/v1/model-releases/{model_id}/rollback", tags=["Model Governance"]
    )
    async def rollback_model_release(
        model_id: str,
        body: RollbackModelReleaseRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[ModelRelease]:
        result = await runtime.feedback.rollback(context, model_id, body)
        return envelope(request, result)

    @router.get("/api/v1/model-deployment-events", tags=["Model Governance"])
    async def list_model_deployment_events(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[ModelDeploymentEvent]]:
        rows = await runtime.feedback.deployment_events(context, limit)
        return envelope(request, rows)

    @router.post("/api/v1/webhooks/subscriptions", status_code=201, tags=["Webhooks"])
    async def create_webhook_subscription(
        body: CreateWebhookSubscriptionRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[WebhookSubscriptionView]:
        endpoint = await runtime.webhooks.create(context, body)
        return envelope(request, endpoint)

    @router.get("/api/v1/webhooks/subscriptions", tags=["Webhooks"])
    async def list_webhook_subscriptions(
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[WebhookSubscriptionView]]:
        rows = await runtime.webhooks.subscriptions(context)
        return envelope(request, rows)

    @router.delete(
        "/api/v1/webhooks/subscriptions/{endpoint_id}",
        status_code=204,
        tags=["Webhooks"],
    )
    async def delete_webhook_subscription(
        endpoint_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.webhooks.delete(context, endpoint_id)
        return Response(status_code=204)

    @router.get("/api/v1/webhooks/deliveries", tags=["Webhooks"])
    async def list_webhook_deliveries(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[WebhookDeliveryRecord]]:
        rows = await runtime.webhooks.deliveries(context, limit=limit)
        return envelope(request, rows)

    return router


__all__ = ["build_feedback_router"]
