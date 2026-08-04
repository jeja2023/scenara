from __future__ import annotations

import time
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scenara.domains.portrait.encoder import (
    PortraitEmbedding,
    PortraitImageEncoder,
    RuntimePortraitImageEncoder,
    decode_portrait_image,
)
from scenara.platform.audit import AuditLogger
from scenara.platform.features import (
    DistanceMetric,
    FeatureMatch,
    FeatureRecord,
    FeatureSpace,
    FeatureStore,
    compare_embeddings,
)
from scenara.platform.index import (
    IndexDefinition,
    IndexHit,
    IndexRecord,
    IndexRecordKind,
    IndexSourceRef,
    IndexStore,
)
from scenara.platform.models import PrincipalContext
from scenara.platform.policy import PolicyProvider, require_allowed

PortraitModality = Literal["face", "body", "gait", "appearance"]


class PortraitModel(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class PortraitIdentity(PortraitModel):
    identity_id: str
    tenant_id: str
    project_id: str
    display_name: str = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    updated_at: float


class PortraitEnrollment(PortraitModel):
    enrollment_id: str
    tenant_id: str
    project_id: str
    identity_id: str
    feature_id: str
    feature_space_id: str
    modality: PortraitModality
    quality: float = Field(ge=0, le=1)
    created_at: float
    expires_at: float | None = None
    index_record_id: str | None = None


class CreateIdentityRequest(PortraitModel):
    display_name: str = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnrollIdentityRequest(PortraitModel):
    feature_space_id: str = Field(min_length=2, max_length=128)
    modality: PortraitModality
    model_id: str = Field(min_length=2, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    distance_metric: DistanceMetric = DistanceMetric.COSINE
    threshold: float | None = Field(default=None, ge=-1, le=1)
    embedding: list[float] = Field(min_length=1, max_length=65_536)
    quality: float = Field(ge=0, le=1)
    expires_at: float | None = None


class PortraitSearchRequest(PortraitModel):
    feature_space_id: str = Field(min_length=2, max_length=128)
    embedding: list[float] = Field(min_length=1, max_length=65_536)
    limit: int = Field(default=20, ge=1, le=200)
    threshold: float | None = Field(default=None, ge=-1, le=1)


class PortraitCompareRequest(PortraitModel):
    feature_space_id: str = Field(min_length=2, max_length=128)
    left: list[float] = Field(min_length=1, max_length=65_536)
    right: list[float] = Field(min_length=1, max_length=65_536)


class PortraitSearchMatch(PortraitModel):
    identity: PortraitIdentity
    enrollment_id: str
    modality: PortraitModality
    score: float
    distance: float


class PortraitSearchResponse(PortraitModel):
    feature_space_id: str
    matches: list[PortraitSearchMatch]


class PortraitCompareResponse(PortraitModel):
    feature_space_id: str
    score: float
    distance: float
    threshold: float | None
    matched: bool | None
    mode: Literal["vector", "image", "asset", "mixed"] = "vector"
    comparison_id: str | None = None
    left: PortraitInputSummary | None = None
    right: PortraitInputSummary | None = None


class PortraitInputSummary(PortraitModel):
    face_count: int = Field(ge=0)
    selected_face_index: int = Field(ge=0)
    selected_face_box: list[float] | None = None
    quality_score: float | None = None
    model_id: str
    model_version: str
    embedding_dimension: int = Field(gt=0)
    fallback: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortraitAssetCompareRequest(PortraitModel):
    left_asset_id: str = Field(min_length=2, max_length=128)
    right_asset_id: str = Field(min_length=2, max_length=128)
    feature_space_id: str | None = Field(default=None, min_length=2, max_length=128)
    threshold: float | None = Field(default=None, ge=-1, le=1)


PortraitCompareResponse.model_rebuild()


class PortraitIdentityPage(PortraitModel):
    items: list[PortraitIdentity]
    offset: int
    limit: int
    total: int


class PortraitError(RuntimeError):
    pass


class PortraitNotFound(PortraitError):
    pass


class PortraitConflict(PortraitError):
    pass


class PortraitRepository(Protocol):
    async def create_identity(self, identity: PortraitIdentity) -> PortraitIdentity: ...

    async def get_identity(
        self,
        tenant_id: str,
        project_id: str,
        identity_id: str,
    ) -> PortraitIdentity | None: ...

    async def list_identities(self, tenant_id: str, project_id: str) -> list[PortraitIdentity]: ...

    async def delete_identity(self, tenant_id: str, project_id: str, identity_id: str) -> bool: ...

    async def create_enrollment(self, enrollment: PortraitEnrollment) -> PortraitEnrollment: ...

    async def get_enrollment_by_feature(
        self,
        tenant_id: str,
        project_id: str,
        feature_id: str,
    ) -> PortraitEnrollment | None: ...


class MemoryPortraitRepository:
    def __init__(self) -> None:
        self._identities: dict[tuple[str, str, str], PortraitIdentity] = {}
        self._enrollments: dict[tuple[str, str, str], PortraitEnrollment] = {}

    async def create_identity(self, identity: PortraitIdentity) -> PortraitIdentity:
        key = (identity.tenant_id, identity.project_id, identity.identity_id)
        if key in self._identities:
            raise PortraitConflict("portrait identity already exists")
        self._identities[key] = identity.model_copy(deep=True)
        return identity.model_copy(deep=True)

    async def get_identity(
        self,
        tenant_id: str,
        project_id: str,
        identity_id: str,
    ) -> PortraitIdentity | None:
        identity = self._identities.get((tenant_id, project_id, identity_id))
        return identity.model_copy(deep=True) if identity else None

    async def list_identities(self, tenant_id: str, project_id: str) -> list[PortraitIdentity]:
        rows = [
            identity.model_copy(deep=True)
            for (row_tenant, row_project, _), identity in self._identities.items()
            if (row_tenant, row_project) == (tenant_id, project_id)
        ]
        return sorted(rows, key=lambda row: (row.created_at, row.identity_id), reverse=True)

    async def delete_identity(self, tenant_id: str, project_id: str, identity_id: str) -> bool:
        key = (tenant_id, project_id, identity_id)
        if self._identities.pop(key, None) is None:
            return False
        for enrollment_key, enrollment in list(self._enrollments.items()):
            if (
                enrollment.tenant_id,
                enrollment.project_id,
                enrollment.identity_id,
            ) == (tenant_id, project_id, identity_id):
                self._enrollments.pop(enrollment_key)
        return True

    async def create_enrollment(self, enrollment: PortraitEnrollment) -> PortraitEnrollment:
        key = (enrollment.tenant_id, enrollment.project_id, enrollment.feature_id)
        if key in self._enrollments:
            raise PortraitConflict("portrait enrollment already exists")
        self._enrollments[key] = enrollment.model_copy(deep=True)
        return enrollment.model_copy(deep=True)

    async def get_enrollment_by_feature(
        self,
        tenant_id: str,
        project_id: str,
        feature_id: str,
    ) -> PortraitEnrollment | None:
        enrollment = self._enrollments.get((tenant_id, project_id, feature_id))
        return enrollment.model_copy(deep=True) if enrollment else None


class PortraitService:
    def __init__(
        self,
        repository: PortraitRepository,
        features: FeatureStore,
        policy: PolicyProvider,
        audit: AuditLogger,
        *,
        indexes: IndexStore | None = None,
        encoder: PortraitImageEncoder | None = None,
    ) -> None:
        self.repository = repository
        self.features = features
        self.policy = policy
        self.audit = audit
        self.indexes = indexes
        self.encoder = encoder or RuntimePortraitImageEncoder()

    async def create_identity(
        self,
        context: PrincipalContext,
        request: CreateIdentityRequest,
    ) -> PortraitIdentity:
        await require_allowed(self.policy, context, "create", "portrait_identity")
        now = time.time()
        identity = PortraitIdentity(
            identity_id=f"idn_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            display_name=request.display_name,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )
        stored = await self.repository.create_identity(identity)
        await self.audit.record(
            context,
            action="portrait.identity.create",
            resource_type="portrait_identity",
            resource_id=identity.identity_id,
        )
        return stored

    async def get_identity(self, context: PrincipalContext, identity_id: str) -> PortraitIdentity:
        await require_allowed(self.policy, context, "read", "portrait_identity", {"identity_id": identity_id})
        identity = await self.repository.get_identity(context.tenant_id, context.project_id, identity_id)
        if identity is None:
            raise PortraitNotFound("portrait identity not found")
        return identity

    async def list_identities(
        self,
        context: PrincipalContext,
        *,
        offset: int,
        limit: int,
    ) -> PortraitIdentityPage:
        await require_allowed(self.policy, context, "list", "portrait_identity")
        rows = await self.repository.list_identities(context.tenant_id, context.project_id)
        return PortraitIdentityPage(
            items=rows[offset : offset + limit],
            offset=offset,
            limit=limit,
            total=len(rows),
        )

    async def delete_identity(self, context: PrincipalContext, identity_id: str) -> None:
        await require_allowed(self.policy, context, "delete", "portrait_identity", {"identity_id": identity_id})
        identity = await self.repository.get_identity(context.tenant_id, context.project_id, identity_id)
        if identity is None:
            raise PortraitNotFound("portrait identity not found")
        await self.audit.record(
            context,
            action="portrait.identity.delete",
            resource_type="portrait_identity",
            resource_id=identity_id,
            evidence={"biometric_deletion": True},
        )
        await self.features.delete_subject(
            context.tenant_id,
            context.project_id,
            "portrait_identity",
            identity_id,
        )
        if self.indexes is not None:
            await self.indexes.delete_source(context.tenant_id, context.project_id, "portrait_identity", identity_id)
        if not await self.repository.delete_identity(context.tenant_id, context.project_id, identity_id):
            raise PortraitConflict("portrait identity changed during deletion")

    async def enroll(
        self,
        context: PrincipalContext,
        identity_id: str,
        request: EnrollIdentityRequest,
    ) -> PortraitEnrollment:
        await require_allowed(
            self.policy,
            context,
            "enroll",
            "portrait_identity",
            {"identity_id": identity_id, "modality": request.modality},
        )
        await self.get_identity(context, identity_id)
        space = FeatureSpace(
            feature_space_id=request.feature_space_id,
            domain="portrait",
            modality=request.modality,
            model_id=request.model_id,
            model_version=request.model_version,
            dimension=len(request.embedding),
            distance_metric=request.distance_metric,
            threshold=request.threshold,
        )
        await self.features.create_space(space)
        feature_id = f"feat_{uuid4().hex}"
        index_record_id = f"idxr_{uuid4().hex}"
        enrollment = PortraitEnrollment(
            enrollment_id=f"enr_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            identity_id=identity_id,
            feature_id=feature_id,
            feature_space_id=request.feature_space_id,
            modality=request.modality,
            quality=request.quality,
            created_at=time.time(),
            expires_at=request.expires_at,
            index_record_id=index_record_id,
        )
        await self.features.add(
            FeatureRecord(
                feature_id=feature_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                feature_space_id=request.feature_space_id,
                subject_type="portrait_identity",
                subject_id=identity_id,
                embedding=request.embedding,
                expires_at=request.expires_at,
            )
        )
        await self._index_enrollment(context, enrollment, request.embedding, request.model_id, request.model_version)
        stored = await self.repository.create_enrollment(enrollment)
        await self.audit.record(
            context,
            action="portrait.enrollment.create",
            resource_type="portrait_enrollment",
            resource_id=enrollment.enrollment_id,
            evidence={
                "identity_id": identity_id,
                "feature_space_id": request.feature_space_id,
                "modality": request.modality,
                "quality": request.quality,
            },
        )
        return stored

    async def search(
        self,
        context: PrincipalContext,
        request: PortraitSearchRequest,
    ) -> PortraitSearchResponse:
        await require_allowed(
            self.policy,
            context,
            "search",
            "portrait_feature",
            {"feature_space_id": request.feature_space_id},
        )
        matches = await self.features.search(
            context.tenant_id,
            context.project_id,
            request.feature_space_id,
            request.embedding,
            limit=request.limit,
            threshold=request.threshold,
        )
        resolved: list[PortraitSearchMatch] = []
        for match in matches:
            item = await self._resolve_match(context, match)
            if item is not None:
                resolved.append(item)
        await self.audit.record(
            context,
            action="portrait.search",
            resource_type="portrait_feature",
            evidence={"feature_space_id": request.feature_space_id, "match_count": len(resolved)},
        )
        return PortraitSearchResponse(feature_space_id=request.feature_space_id, matches=resolved)

    async def compare(
        self,
        context: PrincipalContext,
        request: PortraitCompareRequest,
    ) -> PortraitCompareResponse:
        await require_allowed(
            self.policy,
            context,
            "compare",
            "portrait_feature",
            {"feature_space_id": request.feature_space_id},
        )
        space = await self.features.get_space(request.feature_space_id)
        if space is None or space.domain != "portrait":
            raise PortraitNotFound("portrait feature space not found")
        score, distance = compare_embeddings(space, request.left, request.right)
        matched = None if space.threshold is None else score >= space.threshold
        await self.audit.record(
            context,
            action="portrait.compare",
            resource_type="portrait_feature",
            evidence={"feature_space_id": request.feature_space_id, "matched": matched},
        )
        return PortraitCompareResponse(
            feature_space_id=request.feature_space_id,
            score=score,
            distance=distance,
            threshold=space.threshold,
            matched=matched,
        )

    async def enroll_image(
        self,
        context: PrincipalContext,
        identity_id: str,
        data: bytes,
        *,
        feature_space_id: str | None = None,
        quality_override: float | None = None,
        expires_at: float | None = None,
    ) -> PortraitEnrollment:
        await require_allowed(
            self.policy,
            context,
            "enroll",
            "portrait_identity",
            {"identity_id": identity_id, "modality": "face"},
        )
        await self.get_identity(context, identity_id)
        encoded = await self._encode_image(data)
        selected_space = feature_space_id or encoded.feature_space_id
        if selected_space != encoded.feature_space_id:
            space = await self.features.get_space(selected_space)
            if space is None:
                raise PortraitConflict("image embedding does not match the requested feature space")
            self._validate_encoding_contract(encoded, space)
            model_id, model_version = space.model_id, space.model_version
        else:
            space = await self.features.get_space(selected_space)
            if space is not None:
                self._validate_encoding_contract(encoded, space)
            model_id, model_version = encoded.model_id, encoded.model_version
        await self._ensure_space(
            feature_space_id=selected_space,
            model_id=model_id,
            model_version=model_version,
            dimension=len(encoded.embedding),
            threshold=0.8,
        )
        request = EnrollIdentityRequest(
            feature_space_id=selected_space,
            modality="face",
            model_id=model_id,
            model_version=model_version,
            distance_metric=DistanceMetric.COSINE,
            threshold=0.8,
            embedding=encoded.embedding,
            quality=(
                quality_override
                if quality_override is not None
                else max(0.0, min(1.0, encoded.quality_score or 0.0))
            ),
            expires_at=expires_at,
        )
        stored = await self.enroll(context, identity_id, request)
        await self.audit.record(
            context,
            action="portrait.enrollment.image",
            resource_type="portrait_enrollment",
            resource_id=stored.enrollment_id,
            evidence={
                "identity_id": identity_id,
                "feature_space_id": selected_space,
                "face_count": encoded.face_count,
                "selected_face_index": encoded.selected_face_index,
                "fallback": encoded.fallback,
            },
        )
        return stored

    async def search_image(
        self,
        context: PrincipalContext,
        data: bytes,
        *,
        feature_space_id: str | None = None,
        limit: int = 20,
        threshold: float | None = None,
    ) -> PortraitSearchResponse:
        encoded = await self._encode_image(data)
        selected_space = feature_space_id or encoded.feature_space_id
        space = await self.features.get_space(selected_space)
        if space is None:
            raise PortraitNotFound("portrait feature space is not enrolled")
        self._validate_encoding_contract(encoded, space)
        if self.indexes is None:
            result = await self.search(
                context,
                PortraitSearchRequest(
                    feature_space_id=selected_space,
                    embedding=encoded.embedding,
                    limit=limit,
                    threshold=threshold,
                ),
            )
        else:
            index_id = f"portrait.identity.{selected_space}"
            if await self.indexes.get_index(index_id) is None:
                raise PortraitNotFound("portrait image index is not enrolled")
            hits = await self.indexes.query_vector(
                context.tenant_id,
                context.project_id,
                index_id,
                encoded.embedding,
                limit=limit,
                threshold=threshold,
            )
            resolved: list[PortraitSearchMatch] = []
            for hit in hits:
                item = await self._resolve_index_match(context, hit)
                if item is not None:
                    resolved.append(item)
            result = PortraitSearchResponse(feature_space_id=selected_space, matches=resolved)
        await self.audit.record(
            context,
            action="portrait.search.image",
            resource_type="portrait_feature",
            evidence={
                "feature_space_id": selected_space,
                "face_count": encoded.face_count,
                "selected_face_index": encoded.selected_face_index,
                "fallback": encoded.fallback,
                "match_count": len(result.matches),
            },
        )
        return result

    async def compare_images(
        self,
        context: PrincipalContext,
        left_data: bytes,
        right_data: bytes,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
        mode: Literal["image", "asset"] = "image",
    ) -> PortraitCompareResponse:
        await require_allowed(
            self.policy,
            context,
            "compare",
            "portrait_feature",
            {"feature_space_id": feature_space_id},
        )
        left = await self._encode_image(left_data)
        right = await self._encode_image(right_data)
        if left.feature_space_id != right.feature_space_id:
            raise PortraitConflict("the two images were encoded by different feature contracts")
        selected_space = feature_space_id or left.feature_space_id
        space = await self.features.get_space(selected_space)
        if space is None:
            if feature_space_id is not None:
                raise PortraitNotFound("portrait feature space is not enrolled")
            await self._ensure_space(
                feature_space_id=selected_space,
                model_id=left.model_id,
                model_version=left.model_version,
                dimension=len(left.embedding),
                threshold=threshold if threshold is not None else 0.8,
            )
            space = await self.features.get_space(selected_space)
        if space is None or space.domain != "portrait" or space.dimension != len(left.embedding):
            raise PortraitConflict("image embedding does not match the feature space")
        self._validate_encoding_contract(left, space)
        self._validate_encoding_contract(right, space)
        score, distance = compare_embeddings(space, left.embedding, right.embedding)
        effective_threshold = space.threshold if threshold is None else threshold
        await self.audit.record(
            context,
            action="portrait.compare.image",
            resource_type="portrait_feature",
            evidence={
                "feature_space_id": selected_space,
                "left_face_count": left.face_count,
                "right_face_count": right.face_count,
                "left_selected_face_index": left.selected_face_index,
                "right_selected_face_index": right.selected_face_index,
                "matched": None if effective_threshold is None else score >= effective_threshold,
                "fallback": left.fallback or right.fallback,
            },
        )
        return PortraitCompareResponse(
            feature_space_id=selected_space,
            score=score,
            distance=distance,
            threshold=effective_threshold,
            matched=None if effective_threshold is None else score >= effective_threshold,
            mode=mode,
            comparison_id=f"cmp_{uuid4().hex}",
            left=self._summary(left),
            right=self._summary(right),
        )

    async def _encode_image(self, data: bytes) -> PortraitEmbedding:
        return await self.encoder.encode(decode_portrait_image(data))

    @staticmethod
    def _validate_encoding_contract(encoded: PortraitEmbedding, space: FeatureSpace) -> None:
        if (
            space.domain != "portrait"
            or space.dimension != len(encoded.embedding)
            or space.model_id != encoded.model_id
            or space.model_version != encoded.model_version
        ):
            raise PortraitConflict("image embedding does not match the feature space contract")

    async def _ensure_space(
        self,
        *,
        feature_space_id: str,
        model_id: str,
        model_version: str,
        dimension: int,
        threshold: float | None,
    ) -> FeatureSpace:
        space = FeatureSpace(
            feature_space_id=feature_space_id,
            domain="portrait",
            modality="face",
            model_id=model_id,
            model_version=model_version,
            dimension=dimension,
            distance_metric=DistanceMetric.COSINE,
            threshold=threshold,
        )
        await self.features.create_space(space)
        return space

    async def _index_enrollment(
        self,
        context: PrincipalContext,
        enrollment: PortraitEnrollment,
        embedding: list[float],
        model_id: str,
        model_version: str,
    ) -> None:
        if self.indexes is None or enrollment.index_record_id is None:
            return
        index_id = f"portrait.identity.{enrollment.feature_space_id}"
        await self.indexes.create_index(
            IndexDefinition(
                index_id=index_id,
                domain="portrait",
                record_kind=IndexRecordKind.VECTOR,
                vector_dimension=len(embedding),
                vector_model_id=model_id,
                vector_model_version=model_version,
                distance_metric=DistanceMetric.COSINE,
                threshold=0.8,
            )
        )
        await self.indexes.upsert(
            IndexRecord(
                record_id=enrollment.index_record_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                index_id=index_id,
                domain="portrait",
                kind=IndexRecordKind.VECTOR,
                source=IndexSourceRef(source_type="portrait_identity", source_id=enrollment.identity_id),
                feature_id=enrollment.feature_id,
                vector=embedding,
                metadata={
                    "enrollment_id": enrollment.enrollment_id,
                    "feature_space_id": enrollment.feature_space_id,
                    "modality": enrollment.modality,
                    "quality": enrollment.quality,
                },
                expires_at=enrollment.expires_at,
            )
        )

    @staticmethod
    def _summary(value: PortraitEmbedding) -> PortraitInputSummary:
        return PortraitInputSummary(
            face_count=value.face_count,
            selected_face_index=value.selected_face_index,
            selected_face_box=value.selected_face_box,
            quality_score=value.quality_score,
            model_id=value.model_id,
            model_version=value.model_version,
            embedding_dimension=len(value.embedding),
            fallback=value.fallback,
            metadata=value.metadata,
        )

    async def _resolve_match(
        self,
        context: PrincipalContext,
        match: FeatureMatch,
    ) -> PortraitSearchMatch | None:
        enrollment = await self.repository.get_enrollment_by_feature(
            context.tenant_id,
            context.project_id,
            match.feature_id,
        )
        if enrollment is None:
            return None
        identity = await self.repository.get_identity(
            context.tenant_id,
            context.project_id,
            enrollment.identity_id,
        )
        if identity is None:
            return None
        return PortraitSearchMatch(
            identity=identity,
            enrollment_id=enrollment.enrollment_id,
            modality=enrollment.modality,
            score=match.score,
            distance=match.distance,
        )

    async def _resolve_index_match(
        self,
        context: PrincipalContext,
        match: IndexHit,
    ) -> PortraitSearchMatch | None:
        if match.feature_id is None:
            return None
        enrollment = await self.repository.get_enrollment_by_feature(
            context.tenant_id,
            context.project_id,
            match.feature_id,
        )
        if enrollment is None:
            return None
        identity = await self.repository.get_identity(
            context.tenant_id,
            context.project_id,
            enrollment.identity_id,
        )
        if identity is None:
            return None
        return PortraitSearchMatch(
            identity=identity,
            enrollment_id=enrollment.enrollment_id,
            modality=enrollment.modality,
            score=float(match.score or 0.0),
            distance=float(match.distance or 0.0),
        )


__all__ = [
    "CreateIdentityRequest",
    "EnrollIdentityRequest",
    "MemoryPortraitRepository",
    "PortraitAssetCompareRequest",
    "PortraitCompareRequest",
    "PortraitCompareResponse",
    "PortraitConflict",
    "PortraitEnrollment",
    "PortraitError",
    "PortraitIdentity",
    "PortraitIdentityPage",
    "PortraitInputSummary",
    "PortraitModality",
    "PortraitNotFound",
    "PortraitRepository",
    "PortraitSearchMatch",
    "PortraitSearchRequest",
    "PortraitSearchResponse",
    "PortraitService",
]
