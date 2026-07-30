from __future__ import annotations

import time
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from scenara.platform.audit import AuditLogger
from scenara.platform.features import (
    DistanceMetric,
    FeatureMatch,
    FeatureRecord,
    FeatureSpace,
    FeatureStore,
    compare_embeddings,
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
    ) -> None:
        self.repository = repository
        self.features = features
        self.policy = policy
        self.audit = audit

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


__all__ = [
    "CreateIdentityRequest",
    "EnrollIdentityRequest",
    "MemoryPortraitRepository",
    "PortraitCompareRequest",
    "PortraitCompareResponse",
    "PortraitConflict",
    "PortraitEnrollment",
    "PortraitError",
    "PortraitIdentity",
    "PortraitIdentityPage",
    "PortraitModality",
    "PortraitNotFound",
    "PortraitRepository",
    "PortraitSearchMatch",
    "PortraitSearchRequest",
    "PortraitSearchResponse",
    "PortraitService",
]
