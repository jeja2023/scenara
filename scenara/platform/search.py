import time
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scenara.domains.portrait.encoder import PortraitEmbedding, PortraitImageEncoder, decode_portrait_image
from scenara.platform.audit import AuditLogger
from scenara.platform.index import IndexDefinition, IndexHit, IndexRecordKind, IndexStore, IndexStoreError
from scenara.platform.models import (
    CreateSavedSearchRequest,
    MediaKind,
    PrincipalContext,
    SavedSearch,
    SavedSearchPage,
    UpdateSavedSearchRequest,
)
from scenara.platform.objects import ObjectStore
from scenara.platform.policy import PolicyProvider, require_allowed
from scenara.platform.store import StateConflict, StateStore


class SearchTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    query: str = Field(min_length=1, max_length=10_000)
    profile_id: str | None = Field(default=None, min_length=2, max_length=128)
    domains: list[str] = Field(default_factory=list, max_length=16)
    media_kinds: list[MediaKind] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=50, ge=1, le=200)


class SearchAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    asset_id: str = Field(min_length=2, max_length=128)
    profile_id: str | None = Field(default=None, min_length=2, max_length=128)
    feature_space_id: str | None = Field(default=None, min_length=2, max_length=128)
    media_kinds: list[MediaKind] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=50, ge=1, le=200)
    threshold: float | None = Field(default=None, ge=-1, le=1)


class SearchImageInputSummary(BaseModel):
    face_count: int = Field(ge=0)
    selected_face_index: int = Field(ge=0)
    quality_score: float | None = None
    feature_space_id: str
    model_id: str
    model_version: str
    embedding_dimension: int = Field(gt=0)
    fallback: bool = False


class SearchResultHit(BaseModel):
    record_id: str
    index_id: str
    domain: str
    source: dict[str, Any]
    score: float | None = None
    distance: float | None = None
    text_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    media_kind: MediaKind | None = None
    resource_name: str | None = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    search_id: str
    mode: Literal["text", "portrait"]
    query: str | None = None
    feature_space_id: str | None = None
    query_summary: SearchImageInputSummary | None = None
    hits: list[SearchResultHit]
    total: int
    searched_indexes: list[str] = Field(default_factory=list)


class SearchError(RuntimeError):
    pass


class SavedSearchNotFound(SearchError):
    pass


class SavedSearchConflict(SearchError):
    pass


class SearchRankingProfileResolver(Protocol):
    async def get_search_profile(self, context: PrincipalContext, profile_id: str) -> Any | None: ...


class SearchService:
    def __init__(
        self,
        *,
        indexes: IndexStore,
        state: StateStore,
        policy: PolicyProvider,
        audit: AuditLogger,
        encoder: PortraitImageEncoder,
        objects: ObjectStore,
        profile_resolver: SearchRankingProfileResolver | None = None,
    ) -> None:
        self.indexes = indexes
        self.state = state
        self.policy = policy
        self.audit = audit
        self.encoder = encoder
        self.objects = objects
        self.profile_resolver = profile_resolver

    async def text(self, context: PrincipalContext, request: SearchTextRequest) -> SearchResponse:
        await require_allowed(self.policy, context, "query", "search_index", {"mode": "text"})
        profile = await self._profile(context, request.profile_id)
        definitions = await self.indexes.list_indexes(context.tenant_id, context.project_id)
        domain_filter = set(request.domains)
        media_filter = set(request.media_kinds)
        hits: list[SearchResultHit] = []
        searched: list[str] = []
        for definition in definitions:
            if not definition.index_id.startswith("result."):
                continue
            if domain_filter and definition.domain not in domain_filter:
                continue
            if definition.record_kind == IndexRecordKind.VECTOR:
                continue
            searched.append(definition.index_id)
            for hit in await self.indexes.query_text(
                context.tenant_id,
                context.project_id,
                definition.index_id,
                request.query,
                limit=200,
            ):
                enriched = await self._enrich(context, hit)
                if enriched.score is not None:
                    enriched = enriched.model_copy(update={"score": enriched.score * profile[0]})
                if media_filter and enriched.media_kind not in media_filter:
                    continue
                hits.append(enriched)
        hits = self._sort_hits(hits)[: request.limit]
        await self.audit.record(
            context,
            action="search.text",
            resource_type="search_index",
            evidence={
                "query_length": len(request.query),
                "hit_count": len(hits),
                "index_count": len(searched),
            },
        )
        return SearchResponse(
            search_id=f"sch_{uuid4().hex}",
            mode="text",
            query=request.query,
            hits=hits,
            total=len(hits),
            searched_indexes=searched,
        )

    async def portrait_image(
        self,
        context: PrincipalContext,
        data: bytes,
        *,
        feature_space_id: str | None = None,
        profile_id: str | None = None,
        media_kinds: list[MediaKind] | None = None,
        limit: int = 50,
        threshold: float | None = None,
    ) -> SearchResponse:
        await require_allowed(self.policy, context, "query", "search_index", {"mode": "portrait"})
        profile = await self._profile(context, profile_id)
        encoded = await self._encode(data)
        selected_space = feature_space_id or encoded.feature_space_id
        index_id = f"result.{selected_space}"
        definition = await self.indexes.get_index(index_id)
        hits: list[SearchResultHit] = []
        if definition is not None and definition.record_kind == IndexRecordKind.VECTOR:
            self._validate_vector_contract(encoded, definition)
            for hit in await self.indexes.query_vector(
                context.tenant_id,
                context.project_id,
                index_id,
                encoded.embedding,
                limit=min(200, limit),
                threshold=threshold,
            ):
                enriched = await self._enrich(context, hit)
                if enriched.score is not None:
                    enriched = enriched.model_copy(update={"score": enriched.score * profile[1]})
                if media_kinds and enriched.media_kind not in set(media_kinds):
                    continue
                hits.append(enriched)
        hits = self._sort_hits(hits)[:limit]
        await self.audit.record(
            context,
            action="search.portrait",
            resource_type="search_index",
            resource_id=index_id,
            evidence={
                "feature_space_id": selected_space,
                "face_count": encoded.face_count,
                "selected_face_index": encoded.selected_face_index,
                "hit_count": len(hits),
                "fallback": encoded.fallback,
            },
        )
        return SearchResponse(
            search_id=f"sch_{uuid4().hex}",
            mode="portrait",
            feature_space_id=selected_space,
            query_summary=SearchImageInputSummary(
                face_count=encoded.face_count,
                selected_face_index=encoded.selected_face_index,
                quality_score=encoded.quality_score,
                feature_space_id=encoded.feature_space_id,
                model_id=encoded.model_id,
                model_version=encoded.model_version,
                embedding_dimension=len(encoded.embedding),
                fallback=encoded.fallback,
            ),
            hits=hits,
            total=len(hits),
            searched_indexes=[index_id] if definition is not None else [],
        )

    async def create_saved_search(
        self, context: PrincipalContext, request: CreateSavedSearchRequest
    ) -> SavedSearch:
        await require_allowed(self.policy, context, "write", "saved_search")
        self._validate_saved_definition(request.mode.value, request.definition)
        now = time.time()
        saved = SavedSearch(
            saved_search_id=f"ss_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            name=request.name,
            description=request.description,
            mode=request.mode,
            definition=request.definition,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
        )
        try:
            created = await self.state.create_saved_search(saved)
        except StateConflict as exc:
            raise SavedSearchConflict(str(exc)) from exc
        await self.audit.record(
            context,
            action="search.saved.create",
            resource_type="saved_search",
            resource_id=created.saved_search_id,
            evidence={"mode": created.mode.value},
        )
        return created

    async def get_saved_search(self, context: PrincipalContext, saved_search_id: str) -> SavedSearch:
        await require_allowed(self.policy, context, "read", "saved_search", {"saved_search_id": saved_search_id})
        saved = await self.state.get_saved_search(context.tenant_id, context.project_id, saved_search_id)
        if saved is None:
            raise SavedSearchNotFound("saved search not found")
        return saved

    async def list_saved_searches(
        self, context: PrincipalContext, *, offset: int = 0, limit: int = 50
    ) -> SavedSearchPage:
        await require_allowed(self.policy, context, "list", "saved_search")
        items = await self.state.list_saved_searches(
            context.tenant_id, context.project_id, offset=offset, limit=limit
        )
        total = await self.state.count_saved_searches(context.tenant_id, context.project_id)
        return SavedSearchPage(items=items, offset=offset, limit=limit, total=total)

    async def update_saved_search(
        self, context: PrincipalContext, saved_search_id: str, request: UpdateSavedSearchRequest
    ) -> SavedSearch:
        current = await self.get_saved_search(context, saved_search_id)
        await require_allowed(self.policy, context, "write", "saved_search", {"saved_search_id": saved_search_id})
        definition = request.definition if request.definition is not None else current.definition
        self._validate_saved_definition(current.mode.value, definition)
        updated = current.model_copy(
            update={
                "name": request.name if request.name is not None else current.name,
                "description": request.description if request.description is not None else current.description,
                "definition": definition,
                "updated_at": time.time(),
            }
        )
        try:
            saved = await self.state.save_saved_search(updated)
        except StateConflict as exc:
            raise SavedSearchConflict(str(exc)) from exc
        await self.audit.record(
            context,
            action="search.saved.update",
            resource_type="saved_search",
            resource_id=saved_search_id,
        )
        return saved

    async def delete_saved_search(self, context: PrincipalContext, saved_search_id: str) -> None:
        await require_allowed(self.policy, context, "delete", "saved_search", {"saved_search_id": saved_search_id})
        deleted = await self.state.delete_saved_search(context.tenant_id, context.project_id, saved_search_id)
        if deleted is None:
            raise SavedSearchNotFound("saved search not found")
        await self.audit.record(
            context,
            action="search.saved.delete",
            resource_type="saved_search",
            resource_id=saved_search_id,
        )

    async def run_saved_search(self, context: PrincipalContext, saved_search_id: str) -> SearchResponse:
        saved = await self.get_saved_search(context, saved_search_id)
        if saved.mode.value == "text":
            result = await self.text(context, SearchTextRequest.model_validate(saved.definition))
        else:
            request = SearchAssetRequest.model_validate(saved.definition)
            await require_allowed(self.policy, context, "read", "media_asset", {"asset_id": request.asset_id})
            asset = await self.state.get_asset(context.tenant_id, context.project_id, request.asset_id)
            if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
                raise SavedSearchConflict("saved portrait search asset is unavailable")
            if asset.kind != MediaKind.IMAGE:
                raise SavedSearchConflict("saved portrait search asset must be an image")
            result = await self.portrait_image(
                context,
                await self._asset_bytes(asset.object_key),
                feature_space_id=request.feature_space_id,
                profile_id=request.profile_id,
                media_kinds=request.media_kinds,
                limit=request.limit,
                threshold=request.threshold,
            )
        updated = saved.model_copy(update={"last_run_at": time.time(), "updated_at": time.time()})
        await self.state.save_saved_search(updated)
        return result

    async def _asset_bytes(self, object_key: str) -> bytes:
        return await self.objects.get(object_key)

    async def _profile(self, context: PrincipalContext, profile_id: str | None) -> tuple[float, float]:
        if profile_id is None or self.profile_resolver is None:
            return 1.0, 1.0
        profile = await self.profile_resolver.get_search_profile(context, profile_id)
        if profile is None:
            raise ValueError("search ranking profile not found")
        return float(profile.exact_weight), float(profile.vector_weight)

    @staticmethod
    def _validate_saved_definition(mode: str, definition: dict[str, Any]) -> None:
        try:
            if mode == "text":
                SearchTextRequest.model_validate(definition)
            else:
                SearchAssetRequest.model_validate(definition)
        except Exception as exc:
            raise SavedSearchConflict("saved search definition is invalid") from exc

    async def _encode(self, data: bytes) -> PortraitEmbedding:
        return await self.encoder.encode(decode_portrait_image(data))

    @staticmethod
    def _validate_vector_contract(encoded: PortraitEmbedding, definition: IndexDefinition) -> None:
        if definition.vector_dimension != len(encoded.embedding):
            raise IndexStoreError("query embedding dimension does not match the result index contract")
        if definition.vector_model_id != encoded.model_id:
            raise IndexStoreError("query embedding model does not match the result index contract")
        if definition.vector_model_version != encoded.model_version:
            raise IndexStoreError("query embedding model version does not match the result index contract")

    async def _enrich(self, context: PrincipalContext, hit: IndexHit) -> SearchResultHit:
        media_kind: MediaKind | None = None
        resource_name: str | None = None
        if hit.source.asset_id:
            asset = await self.state.get_asset(context.tenant_id, context.project_id, hit.source.asset_id)
            if asset is not None and asset.deleted_at is None:
                media_kind = asset.kind
                resource_name = asset.filename
        source_id = hit.metadata.get("source_id")
        if media_kind is None and isinstance(source_id, str) and source_id:
            source = await self.state.get_source(context.tenant_id, context.project_id, source_id)
            if source is not None:
                media_kind = MediaKind.STREAM
                resource_name = source.name
        return SearchResultHit(
            record_id=hit.record_id,
            index_id=hit.index_id,
            domain=hit.domain,
            source=hit.source.model_dump(mode="json"),
            score=hit.score,
            distance=hit.distance,
            text_snippet=hit.text_snippet,
            metadata=hit.metadata,
            media_kind=media_kind,
            resource_name=resource_name,
        )

    @staticmethod
    def _sort_hits(hits: list[SearchResultHit]) -> list[SearchResultHit]:
        return sorted(
            hits,
            key=lambda item: (-float(item.score or 0), float(item.distance or 0), item.record_id),
        )


__all__ = [
    "SavedSearchConflict",
    "SavedSearchNotFound",
    "SearchAssetRequest",
    "SearchError",
    "SearchImageInputSummary",
    "SearchResponse",
    "SearchResultHit",
    "SearchService",
    "SearchTextRequest",
]
