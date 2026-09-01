from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from scenara.bootstrap import Runtime
from scenara.domains.portrait.service import PortraitNotFound
from scenara.platform.control_plane import (
    CreateIndexBackendRequest,
    CreateIndexRebuildRequest,
    CreateSearchEvaluationRequest,
    CreateSearchRankingProfileRequest,
    CreateSearchRelevanceFeedbackRequest,
    CreateSearchRerankerRequest,
    IndexBackend,
    IndexRebuildJob,
    SearchEvaluation,
    SearchRankingProfile,
    SearchRelevanceFeedback,
    SearchReranker,
)
from scenara.platform.index import (
    IndexDefinition,
    IndexHit,
    IndexRecordView,
    IndexTextQueryRequest,
    IndexVectorQueryRequest,
)
from scenara.platform.models import (
    ApiEnvelope,
    CreateSavedSearchRequest,
    MediaKind,
    PrincipalContext,
    SavedSearch,
    SavedSearchPage,
    UpdateSavedSearchRequest,
)
from scenara.platform.policy import require_allowed
from scenara.platform.search import (
    SearchAssetRequest,
    SearchResponse,
    SearchTextRequest,
)
from scenara.platform.services import ResourceNotFound
from typing import Annotated


EnvelopeFactory = Callable[[Request, Any], ApiEnvelope[Any]]
PrincipalDependency = Callable[..., Awaitable[PrincipalContext]]


def build_search_router(
    runtime: Runtime, principal_context: PrincipalDependency, envelope: EnvelopeFactory
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/search/text", tags=["Search"])
    async def search_text(
        body: SearchTextRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        result = await runtime.search.text(context, body)
        return envelope(request, result)

    @router.post("/api/v1/search/image", tags=["Search"])
    async def search_portrait_image(
        file: Annotated[UploadFile, File()],
        request: Request,
        feature_space_id: Annotated[str | None, Form()] = None,
        profile_id: Annotated[str | None, Form()] = None,
        media_kinds: Annotated[str | None, Form()] = None,
        limit: Annotated[int, Form(ge=1, le=200)] = 50,
        threshold: Annotated[float | None, Form(ge=-1, le=1)] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        data = await file.read(runtime.settings.max_image_bytes + 1)
        if len(data) > runtime.settings.max_image_bytes:
            raise ValueError(f"image exceeds {runtime.settings.max_image_bytes} bytes")
        selected_kinds = [
            MediaKind(value.strip())
            for value in (media_kinds or "").split(",")
            if value.strip()
        ]
        result = await runtime.search.portrait_image(
            context,
            data,
            feature_space_id=feature_space_id,
            profile_id=profile_id,
            media_kinds=selected_kinds,
            limit=limit,
            threshold=threshold,
        )
        return envelope(request, result)

    @router.post("/api/v1/search/asset", tags=["Search"])
    async def search_portrait_asset(
        body: SearchAssetRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        await require_allowed(
            runtime.policy, context, "read", "media_asset", {"asset_id": body.asset_id}
        )
        asset = await runtime.state.get_asset(
            context.tenant_id, context.project_id, body.asset_id
        )
        if (
            asset is None
            or asset.deleted_at is not None
            or asset.original_deleted_at is not None
        ):
            raise ResourceNotFound("search asset not found")
        if asset.kind != MediaKind.IMAGE:
            raise ValueError("portrait search assets must be images")
        result = await runtime.search.portrait_image(
            context,
            await runtime.objects.get(asset.object_key),
            feature_space_id=body.feature_space_id,
            profile_id=body.profile_id,
            media_kinds=body.media_kinds,
            limit=body.limit,
            threshold=body.threshold,
        )
        return envelope(request, result)

    @router.post("/api/v1/search/saved", status_code=201, tags=["Search"])
    async def create_saved_search(
        body: CreateSavedSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearch]:
        result = await runtime.search.create_saved_search(context, body)
        return envelope(request, result)

    @router.get("/api/v1/search/saved", tags=["Search"])
    async def list_saved_searches(
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearchPage]:
        result = await runtime.search.list_saved_searches(
            context, offset=offset, limit=limit
        )
        return envelope(request, result)

    @router.get("/api/v1/search/saved/{saved_search_id}", tags=["Search"])
    async def get_saved_search(
        saved_search_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearch]:
        result = await runtime.search.get_saved_search(context, saved_search_id)
        return envelope(request, result)

    @router.patch("/api/v1/search/saved/{saved_search_id}", tags=["Search"])
    async def update_saved_search(
        saved_search_id: str,
        body: UpdateSavedSearchRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SavedSearch]:
        result = await runtime.search.update_saved_search(
            context, saved_search_id, body
        )
        return envelope(request, result)

    @router.delete(
        "/api/v1/search/saved/{saved_search_id}", status_code=204, tags=["Search"]
    )
    async def delete_saved_search(
        saved_search_id: str,
        context: PrincipalContext = Depends(principal_context),
    ) -> Response:
        await runtime.search.delete_saved_search(context, saved_search_id)
        return Response(status_code=204)

    @router.post("/api/v1/search/saved/{saved_search_id}/run", tags=["Search"])
    async def run_saved_search(
        saved_search_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchResponse]:
        result = await runtime.search.run_saved_search(context, saved_search_id)
        return envelope(request, result)

    @router.get("/api/v1/indexes", tags=["Search"])
    async def list_search_indexes(
        request: Request,
        domain: Annotated[str | None, Query()] = None,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[IndexDefinition]]:
        await require_allowed(
            runtime.policy, context, "list", "search_index", {"domain": domain}
        )
        rows = await runtime.indexes.list_indexes(
            context.tenant_id, context.project_id, domain=domain
        )
        return envelope(request, rows)

    @router.post("/api/v1/indexes", status_code=201, tags=["Search"])
    async def create_search_index(
        body: IndexDefinition,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexDefinition]:
        await require_allowed(
            runtime.policy,
            context,
            "write",
            "search_index",
            {"index_id": body.index_id},
        )
        created = await runtime.indexes.create_index(body)
        await runtime.audit.record(
            context,
            action="index.create",
            resource_type="search_index",
            resource_id=created.index_id,
            evidence={
                "domain": created.domain,
                "record_kind": created.record_kind.value,
            },
        )
        return envelope(request, created)

    @router.get("/api/v1/indexes/{index_id}/records", tags=["Search"])
    async def list_search_index_records(
        index_id: str,
        request: Request,
        source_type: Annotated[str | None, Query()] = None,
        source_id: Annotated[str | None, Query()] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[IndexRecordView]]:
        await require_allowed(
            runtime.policy, context, "read", "search_index", {"index_id": index_id}
        )
        if await runtime.indexes.get_index(index_id) is None:
            raise PortraitNotFound("search index not found")
        rows = await runtime.indexes.list_records(
            context.tenant_id,
            context.project_id,
            index_id=index_id,
            source_type=source_type,
            source_id=source_id,
            offset=offset,
            limit=limit,
        )
        views = [
            IndexRecordView(
                record_id=row.record_id,
                index_id=row.index_id,
                domain=row.domain,
                kind=row.kind,
                source=row.source,
                feature_id=row.feature_id,
                has_vector=row.vector is not None or row.feature_id is not None,
                text_snippet=(row.text or "")[:240] or None,
                metadata=row.metadata,
                status=row.status,
                created_at=row.created_at,
                expires_at=row.expires_at,
                deleted_at=row.deleted_at,
            )
            for row in rows
        ]
        return envelope(request, views)

    @router.post("/api/v1/indexes/{index_id}/query/text", tags=["Search"])
    async def query_search_index_text(
        index_id: str,
        body: IndexTextQueryRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[dict[str, object]]]:
        await require_allowed(
            runtime.policy, context, "query", "search_index", {"index_id": index_id}
        )
        if await runtime.indexes.get_index(index_id) is None:
            raise PortraitNotFound("search index not found")
        hits = await runtime.indexes.query_text(
            context.tenant_id,
            context.project_id,
            index_id,
            body.query,
            limit=body.limit,
        )
        await runtime.audit.record(
            context,
            action="index.query.text",
            resource_type="search_index",
            resource_id=index_id,
            evidence={"query_length": len(body.query), "hit_count": len(hits)},
        )
        return envelope(request, [hit.model_dump(mode="json") for hit in hits])

    @router.post("/api/v1/indexes/{index_id}/query/vector", tags=["Search"])
    async def query_search_index_vector(
        index_id: str,
        body: IndexVectorQueryRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[list[IndexHit]]:
        await require_allowed(
            runtime.policy, context, "query", "search_index", {"index_id": index_id}
        )
        if await runtime.indexes.get_index(index_id) is None:
            raise PortraitNotFound("search index not found")
        hits = await runtime.indexes.query_vector(
            context.tenant_id,
            context.project_id,
            index_id,
            body.vector,
            limit=body.limit,
            threshold=body.threshold,
        )
        await runtime.audit.record(
            context,
            action="index.query.vector",
            resource_type="search_index",
            resource_id=index_id,
            evidence={"dimension": len(body.vector), "hit_count": len(hits)},
        )
        return envelope(request, hits)

    @router.post("/api/v1/search/ranking-profiles", status_code=201, tags=["Search"])
    async def create_search_ranking_profile(
        body: CreateSearchRankingProfileRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchRankingProfile]:
        return envelope(
            request, await runtime.control_plane.create_search_profile(context, body)
        )

    @router.get("/api/v1/search/ranking-profiles", tags=["Search"])
    async def list_search_ranking_profiles(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[SearchRankingProfile]]:
        return envelope(
            request, await runtime.control_plane.list_search_profiles(context)
        )

    @router.post("/api/v1/search/index-backends", status_code=201, tags=["Search"])
    async def register_index_backend(
        body: CreateIndexBackendRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexBackend]:
        return envelope(
            request, await runtime.control_plane.register_index_backend(context, body)
        )

    @router.get("/api/v1/search/index-backends", tags=["Search"])
    async def list_index_backends(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[IndexBackend]]:
        return envelope(
            request, await runtime.control_plane.list_index_backends(context)
        )

    @router.post("/api/v1/search/index-backends/{backend_id}/probe", tags=["Search"])
    async def probe_index_backend(
        backend_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexBackend]:
        return envelope(
            request,
            await runtime.control_plane.probe_index_backend(context, backend_id),
        )

    @router.post("/api/v1/search/rerankers", status_code=201, tags=["Search"])
    async def register_search_reranker(
        body: CreateSearchRerankerRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchReranker]:
        return envelope(
            request, await runtime.control_plane.register_search_reranker(context, body)
        )

    @router.get("/api/v1/search/rerankers", tags=["Search"])
    async def list_search_rerankers(
        request: Request, context: PrincipalContext = Depends(principal_context)
    ) -> ApiEnvelope[list[SearchReranker]]:
        return envelope(
            request, await runtime.control_plane.list_search_rerankers(context)
        )

    @router.post("/api/v1/search/rerankers/{reranker_id}/probe", tags=["Search"])
    async def probe_search_reranker(
        reranker_id: str,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchReranker]:
        return envelope(
            request,
            await runtime.control_plane.probe_search_reranker(context, reranker_id),
        )

    @router.post("/api/v1/search/relevance-feedback", status_code=201, tags=["Search"])
    async def submit_search_relevance_feedback(
        body: CreateSearchRelevanceFeedbackRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchRelevanceFeedback]:
        return envelope(
            request, await runtime.control_plane.submit_search_feedback(context, body)
        )

    @router.post("/api/v1/search/evaluations", status_code=201, tags=["Search"])
    async def evaluate_search(
        body: CreateSearchEvaluationRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[SearchEvaluation]:
        return envelope(
            request, await runtime.control_plane.evaluate_search(context, body)
        )

    @router.post("/api/v1/indexes/rebuild", status_code=202, tags=["Search"])
    async def rebuild_index(
        body: CreateIndexRebuildRequest,
        request: Request,
        context: PrincipalContext = Depends(principal_context),
    ) -> ApiEnvelope[IndexRebuildJob]:
        return envelope(
            request, await runtime.control_plane.rebuild_index(context, body)
        )

    return router


__all__ = ["build_search_router"]
