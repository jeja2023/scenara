from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from scenara.platform.audit import AuditLogger
from scenara.platform.model_runtime import ModelCatalog, ModelPackageManifest, RuntimeModelBinding
from scenara.platform.models import PrincipalContext, ResultEnvelope, RunStatus
from scenara.platform.objects import ObjectStore, validate_object_key
from scenara.platform.policy import PolicyProvider, require_allowed
from scenara.platform.store import StateStore


class FeedbackModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VerifiedFeedbackTrace(TypedDict):
    result_ref: str
    media_ref: str
    pipeline_id: str
    pipeline_version: str


class FeedbackKind(StrEnum):
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    WRONG_ATTRIBUTE = "wrong_attribute"
    WRONG_IDENTITY = "wrong_identity"
    OCR_CORRECTION = "ocr_correction"


class FeedbackStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ModelReleaseStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"


class CreateFeedbackRequest(FeedbackModel):
    kind: FeedbackKind
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9]+$")
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    correction: dict[str, Any]
    authorized_for_training: bool = False
    deidentified: bool = False


class ReviewFeedbackRequest(FeedbackModel):
    status: FeedbackStatus
    notes: str = Field(default="", max_length=2000)

    @field_validator("status")
    @classmethod
    def final_status(cls, value: FeedbackStatus) -> FeedbackStatus:
        if value == FeedbackStatus.PENDING:
            raise ValueError("review status cannot return to pending")
        return value


class FeedbackRecord(FeedbackModel):
    schema_version: Literal["1.0"] = "1.0"
    feedback_id: str
    tenant_id: str
    project_id: str
    kind: FeedbackKind
    run_id: str
    result_ref: str
    media_ref: str
    pipeline_id: str
    pipeline_version: str
    model_id: str
    model_version: str
    correction: dict[str, Any]
    authorized_for_training: bool
    deidentified: bool
    status: FeedbackStatus = FeedbackStatus.PENDING
    submitted_by: str
    reviewed_by: str | None = None
    review_notes: str = ""
    created_at: float
    updated_at: float


class CreateHardSampleManifestRequest(FeedbackModel):
    dataset_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    label_schema: str = Field(default="scenara.feedback.correction.v1", min_length=1, max_length=256)
    split: Literal["train", "validation", "test"] = "train"
    feedback_ids: tuple[str, ...] = Field(min_length=1, max_length=10_000)


class HardSampleItem(FeedbackModel):
    feedback_id: str
    kind: FeedbackKind
    media_ref: str
    result_ref: str
    model_id: str
    model_version: str
    pipeline_id: str
    pipeline_version: str
    correction: dict[str, Any]
    authorized_for_training: bool = True
    deidentified: bool = True


class HardSampleManifest(FeedbackModel):
    schema_version: Literal["1.0"] = "1.0"
    manifest_id: str
    tenant_id: str
    project_id: str
    dataset_id: str
    version: str
    label_schema: str = "scenara.feedback.correction.v1"
    split: Literal["train", "validation", "test"] = "train"
    items: tuple[HardSampleItem, ...]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_by: str
    created_at: float


MODEL_EVIDENCE_REF = re.compile(
    r"^tenants/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}/projects/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}/model-evidence/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json#sha256=[0-9a-f]{64}$"
)


class CreateModelReleaseRequest(FeedbackModel):
    model_id: str = Field(min_length=1, max_length=128)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("evidence_refs")
    @classmethod
    def valid_evidence_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item or len(item) > 2048 for item in normalized):
            raise ValueError("evidence references must be non-empty and no longer than 2048 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("evidence references must be unique")
        if any(not MODEL_EVIDENCE_REF.fullmatch(item) for item in normalized):
            raise ValueError("evidence references must be scoped object keys with a SHA-256 digest")
        return normalized

EVIDENCE_SIGNER_PLACEHOLDER = re.compile(r"(?i)(?:<[^>]+>|\b(?:example|replace|todo|tbd)\b|待填写|占位)")


class ModelQualificationEvidence(FeedbackModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_type: str = Field(pattern=r"^(?:model_rights|regression|[a-z][a-z0-9_.-]{1,63}_evaluation)$")
    status: Literal["passed"]
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed_at: datetime
    approved_at: datetime
    signed_by: str = Field(min_length=1, max_length=256)
    details: dict[str, Any]

    @model_validator(mode="after")
    def valid_approval(self) -> ModelQualificationEvidence:
        if self.executed_at.tzinfo is None or self.approved_at.tzinfo is None:
            raise ValueError("qualification evidence timestamps must include a timezone")
        if self.approved_at < self.executed_at:
            raise ValueError("qualification evidence approval cannot predate execution")
        if EVIDENCE_SIGNER_PLACEHOLDER.search(self.signed_by):
            raise ValueError("qualification evidence signer cannot be a placeholder")
        if self.evidence_type == "model_rights" and self.details.get("rights_cleared") is not True:
            raise ValueError("model rights evidence must confirm cleared rights")
        if self.evidence_type.endswith("_evaluation") and not (
            self.details.get("thresholds_approved_before_run") is True
            and self.details.get("within_tolerance") is True
            and isinstance(self.details.get("independent_runs"), int)
            and self.details["independent_runs"] >= 2
        ):
            raise ValueError("evaluation evidence must record two approved reproducible runs")
        if self.evidence_type == "regression" and self.details.get("regressions_passed") is not True:
            raise ValueError("regression evidence must confirm all regressions passed")
        return self


class TransitionModelReleaseRequest(FeedbackModel):
    status: ModelReleaseStatus
    reason: str = Field(min_length=1, max_length=2000)


class RollbackModelReleaseRequest(FeedbackModel):
    target_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    reason: str = Field(min_length=1, max_length=2000)


class ModelRelease(FeedbackModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: str
    project_id: str
    model_id: str
    version: str
    capability: str
    runtime_model_id: str
    package_sha256: str
    evidence_refs: tuple[str, ...] = ()
    status: ModelReleaseStatus = ModelReleaseStatus.CANDIDATE
    created_by: str
    created_at: float
    updated_at: float
    activated_at: float | None = None
    retired_at: float | None = None


class ModelDeploymentEvent(FeedbackModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: str
    tenant_id: str
    project_id: str
    model_id: str
    version: str
    capability: str
    runtime_model_id: str
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: str
    from_status: ModelReleaseStatus | None
    to_status: ModelReleaseStatus
    reason: str
    operator_id: str
    audit_id: str
    created_at: float


class FeedbackError(RuntimeError):
    pass


class FeedbackNotFound(FeedbackError):
    pass


class FeedbackConflict(FeedbackError):
    pass


SENSITIVE_CORRECTION_KEYS = {"base64", "bytes", "crop", "embedding", "embeddings", "image_bytes", "raw_media"}


def contains_sensitive_correction(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in SENSITIVE_CORRECTION_KEYS or contains_sensitive_correction(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_sensitive_correction(item) for item in value)
    return False


class FeedbackRepository(Protocol):
    async def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord: ...

    async def get_feedback(
        self, tenant_id: str, project_id: str, feedback_id: str
    ) -> FeedbackRecord | None: ...

    async def list_feedback(self, tenant_id: str, project_id: str) -> list[FeedbackRecord]: ...

    async def save_feedback(self, record: FeedbackRecord, expected_status: FeedbackStatus) -> FeedbackRecord: ...

    async def create_manifest(self, manifest: HardSampleManifest) -> HardSampleManifest: ...

    async def list_manifests(self, tenant_id: str, project_id: str) -> list[HardSampleManifest]: ...

    async def create_release(self, release: ModelRelease) -> ModelRelease: ...

    async def get_release(
        self, tenant_id: str, project_id: str, model_id: str, version: str
    ) -> ModelRelease | None: ...

    async def list_releases(self, tenant_id: str, project_id: str) -> list[ModelRelease]: ...

    async def transition_release(
        self,
        tenant_id: str,
        project_id: str,
        model_id: str,
        version: str,
        target: ModelReleaseStatus,
        *,
        rollback: bool = False,
    ) -> tuple[ModelRelease, ModelRelease | None]: ...

    async def append_deployment_event(self, event: ModelDeploymentEvent) -> None: ...

    async def list_deployment_events(
        self, tenant_id: str, project_id: str, limit: int
    ) -> list[ModelDeploymentEvent]: ...


class MemoryFeedbackRepository:
    def __init__(self) -> None:
        self._feedback: dict[tuple[str, str, str], FeedbackRecord] = {}
        self._manifests: dict[tuple[str, str, str], HardSampleManifest] = {}
        self._releases: dict[tuple[str, str, str, str], ModelRelease] = {}
        self._events: list[ModelDeploymentEvent] = []

    async def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord:
        key = (record.tenant_id, record.project_id, record.feedback_id)
        if key in self._feedback:
            raise FeedbackConflict("feedback already exists")
        self._feedback[key] = record.model_copy(deep=True)
        return record

    async def get_feedback(self, tenant_id: str, project_id: str, feedback_id: str) -> FeedbackRecord | None:
        value = self._feedback.get((tenant_id, project_id, feedback_id))
        return value.model_copy(deep=True) if value else None

    async def list_feedback(self, tenant_id: str, project_id: str) -> list[FeedbackRecord]:
        return sorted(
            [
                value.model_copy(deep=True)
                for (tenant, project, _), value in self._feedback.items()
                if tenant == tenant_id and project == project_id
            ],
            key=lambda item: item.created_at,
            reverse=True,
        )

    async def save_feedback(self, record: FeedbackRecord, expected_status: FeedbackStatus) -> FeedbackRecord:
        key = (record.tenant_id, record.project_id, record.feedback_id)
        current = self._feedback.get(key)
        if current is None:
            raise FeedbackNotFound("feedback not found")
        if current.status != expected_status:
            raise FeedbackConflict("feedback status changed concurrently")
        self._feedback[key] = record.model_copy(deep=True)
        return record

    async def create_manifest(self, manifest: HardSampleManifest) -> HardSampleManifest:
        key = (manifest.tenant_id, manifest.project_id, manifest.manifest_id)
        if any(
            value.dataset_id == manifest.dataset_id and value.version == manifest.version
            for (tenant, project, _), value in self._manifests.items()
            if tenant == manifest.tenant_id and project == manifest.project_id
        ):
            raise FeedbackConflict("hard-sample manifest version already exists")
        self._manifests[key] = manifest.model_copy(deep=True)
        return manifest

    async def list_manifests(self, tenant_id: str, project_id: str) -> list[HardSampleManifest]:
        return sorted(
            [
                value.model_copy(deep=True)
                for (tenant, project, _), value in self._manifests.items()
                if tenant == tenant_id and project == project_id
            ],
            key=lambda item: item.created_at,
            reverse=True,
        )

    async def create_release(self, release: ModelRelease) -> ModelRelease:
        key = (release.tenant_id, release.project_id, release.model_id, release.version)
        if key in self._releases:
            raise FeedbackConflict("model release already exists")
        self._releases[key] = release.model_copy(deep=True)
        return release

    async def get_release(
        self, tenant_id: str, project_id: str, model_id: str, version: str
    ) -> ModelRelease | None:
        value = self._releases.get((tenant_id, project_id, model_id, version))
        return value.model_copy(deep=True) if value else None

    async def list_releases(self, tenant_id: str, project_id: str) -> list[ModelRelease]:
        return sorted(
            [
                value.model_copy(deep=True)
                for (tenant, project, _, _), value in self._releases.items()
                if tenant == tenant_id and project == project_id
            ],
            key=lambda item: (item.model_id, item.version),
        )

    async def transition_release(
        self,
        tenant_id: str,
        project_id: str,
        model_id: str,
        version: str,
        target: ModelReleaseStatus,
        *,
        rollback: bool = False,
    ) -> tuple[ModelRelease, ModelRelease | None]:
        key = (tenant_id, project_id, model_id, version)
        current = self._releases.get(key)
        if current is None:
            raise FeedbackNotFound("model release not found")
        validate_release_transition(current.status, target, rollback=rollback)
        now = time.time()
        previous: ModelRelease | None = None
        if target == ModelReleaseStatus.ACTIVE:
            for other_key, other in self._releases.items():
                if (
                    other_key[:2] == key[:2]
                    and other.capability == current.capability
                    and other.status == ModelReleaseStatus.ACTIVE
                    and other_key != key
                ):
                    previous = other.model_copy(
                        update={"status": ModelReleaseStatus.RETIRED, "retired_at": now, "updated_at": now}
                    )
                    self._releases[other_key] = previous
                    break
        updated = current.model_copy(
            update={
                "status": target,
                "updated_at": now,
                "activated_at": now if target == ModelReleaseStatus.ACTIVE else current.activated_at,
                "retired_at": now if target == ModelReleaseStatus.RETIRED else None,
            }
        )
        self._releases[key] = updated
        return updated, previous

    async def append_deployment_event(self, event: ModelDeploymentEvent) -> None:
        self._events.append(event.model_copy(deep=True))

    async def list_deployment_events(
        self, tenant_id: str, project_id: str, limit: int
    ) -> list[ModelDeploymentEvent]:
        return [
            event.model_copy(deep=True)
            for event in reversed(self._events)
            if event.tenant_id == tenant_id and event.project_id == project_id
        ][:limit]


def validate_release_transition(
    current: ModelReleaseStatus, target: ModelReleaseStatus, *, rollback: bool = False
) -> None:
    if rollback:
        if current != ModelReleaseStatus.RETIRED or target != ModelReleaseStatus.ACTIVE:
            raise FeedbackConflict("rollback target must be a retired model release")
        return
    allowed = {
        ModelReleaseStatus.CANDIDATE: {ModelReleaseStatus.VALIDATED},
        ModelReleaseStatus.VALIDATED: {ModelReleaseStatus.APPROVED, ModelReleaseStatus.CANDIDATE},
        ModelReleaseStatus.APPROVED: {ModelReleaseStatus.ACTIVE, ModelReleaseStatus.CANDIDATE},
        ModelReleaseStatus.ACTIVE: {ModelReleaseStatus.RETIRED},
        ModelReleaseStatus.RETIRED: set(),
    }
    if target not in allowed[current]:
        raise FeedbackConflict(f"invalid model release transition: {current.value} -> {target.value}")


class FeedbackService:
    def __init__(
        self,
        repository: FeedbackRepository,
        catalog: ModelCatalog,
        state: StateStore,
        objects: ObjectStore,
        policy: PolicyProvider,
        audit: AuditLogger,
        evaluation_evidence_type: Callable[[ModelPackageManifest], str | None],
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._state = state
        self._objects = objects
        self._policy = policy
        self._audit = audit
        self._evaluation_evidence_type = evaluation_evidence_type

    async def admit_package(
        self,
        context: PrincipalContext,
        package: ModelPackageManifest,
    ) -> ModelPackageManifest:
        await require_allowed(self._policy, context, "model-package.admit", "model_package")
        if package.runtime_model_id.startswith("legacy/"):
            raise FeedbackConflict("legacy runtime bindings are reserved for migrated packages")
        await self._audit.record(
            context,
            action="model-package.admit",
            resource_type="model-package",
            resource_id=f"{package.model_id}@{package.version}",
            evidence={
                "capability": package.capability,
                "runtime_model_id": package.runtime_model_id,
                "sha256": package.sha256,
            },
        )
        await self._catalog.register_model_package(package)
        return package

    async def create(self, context: PrincipalContext, body: CreateFeedbackRequest) -> FeedbackRecord:
        await require_allowed(self._policy, context, "feedback.create", "feedback")
        trace = await self._verified_trace(context, body)
        now = time.time()
        record = FeedbackRecord(
            feedback_id=f"fbk_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            submitted_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **trace,
            **body.model_dump(),
        )
        audit = await self._audit.record(
            context,
            action="feedback.create",
            resource_type="feedback",
            resource_id=record.feedback_id,
            evidence={"run_id": record.run_id, "kind": record.kind.value},
        )
        del audit
        return await self._repository.create_feedback(record)

    async def feedback_records(self, context: PrincipalContext) -> list[FeedbackRecord]:
        await require_allowed(self._policy, context, "feedback.read", "feedback")
        return await self._repository.list_feedback(context.tenant_id, context.project_id)

    async def review(
        self, context: PrincipalContext, feedback_id: str, body: ReviewFeedbackRequest
    ) -> FeedbackRecord:
        await require_allowed(self._policy, context, "feedback.review", "feedback")
        record = await self._repository.get_feedback(context.tenant_id, context.project_id, feedback_id)
        if record is None:
            raise FeedbackNotFound("feedback not found")
        if record.status != FeedbackStatus.PENDING:
            raise FeedbackConflict("feedback has already been reviewed")
        if body.status == FeedbackStatus.APPROVED and not (
            record.authorized_for_training and record.deidentified
        ):
            raise FeedbackConflict("approved training feedback must be authorized and deidentified")
        if body.status == FeedbackStatus.APPROVED and contains_sensitive_correction(record.correction):
            raise FeedbackConflict("approved training feedback cannot contain raw media or biometric payloads")
        updated = record.model_copy(
            update={
                "status": body.status,
                "reviewed_by": context.principal_id,
                "review_notes": body.notes,
                "updated_at": time.time(),
            }
        )
        await self._audit.record(
            context,
            action="feedback.review",
            resource_type="feedback",
            resource_id=feedback_id,
            evidence={"status": body.status.value},
        )
        return await self._repository.save_feedback(updated, FeedbackStatus.PENDING)

    async def create_manifest(
        self, context: PrincipalContext, body: CreateHardSampleManifestRequest
    ) -> HardSampleManifest:
        await require_allowed(self._policy, context, "hard-sample.export", "hard-sample-manifest")
        if len(set(body.feedback_ids)) != len(body.feedback_ids):
            raise FeedbackConflict("feedback_ids must be unique")
        items: list[HardSampleItem] = []
        for feedback_id in body.feedback_ids:
            record = await self._repository.get_feedback(context.tenant_id, context.project_id, feedback_id)
            if record is None:
                raise FeedbackNotFound(f"feedback not found: {feedback_id}")
            if record.status != FeedbackStatus.APPROVED or not (
                record.authorized_for_training and record.deidentified
            ):
                raise FeedbackConflict("hard-sample manifest accepts only approved, authorized, deidentified feedback")
            items.append(
                HardSampleItem(
                    feedback_id=record.feedback_id,
                    kind=record.kind,
                    media_ref=record.media_ref,
                    result_ref=record.result_ref,
                    model_id=record.model_id,
                    model_version=record.model_version,
                    pipeline_id=record.pipeline_id,
                    pipeline_version=record.pipeline_version,
                    correction=record.correction,
                )
            )
        payload = {
            "schema_version": "1.0",
            "dataset_id": body.dataset_id,
            "version": body.version,
            "label_schema": body.label_schema,
            "split": body.split,
            "items": [item.model_dump(mode="json") for item in items],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        manifest = HardSampleManifest(
            manifest_id=f"hsm_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            dataset_id=body.dataset_id,
            version=body.version,
            label_schema=body.label_schema,
            split=body.split,
            items=tuple(items),
            sha256=digest,
            created_by=context.principal_id,
            created_at=time.time(),
        )
        await self._audit.record(
            context,
            action="hard-sample.export",
            resource_type="hard-sample-manifest",
            resource_id=manifest.manifest_id,
            evidence={"sha256": digest, "item_count": len(items)},
        )
        return await self._repository.create_manifest(manifest)

    async def list_manifests(self, context: PrincipalContext) -> list[HardSampleManifest]:
        await require_allowed(self._policy, context, "hard-sample.read", "hard-sample-manifest")
        return await self._repository.list_manifests(context.tenant_id, context.project_id)

    async def create_release(
        self, context: PrincipalContext, body: CreateModelReleaseRequest
    ) -> ModelRelease:
        await require_allowed(self._policy, context, "model-release.create", "model-release")
        package = await self._package(body.model_id, body.version, body.package_sha256)
        if package.runtime_model_id.startswith("legacy/"):
            raise FeedbackConflict("migrated model packages must be replaced before release")
        now = time.time()
        release = ModelRelease(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            capability=package.capability,
            runtime_model_id=package.runtime_model_id,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await self._audit.record(
            context,
            action="model-release.create",
            resource_type="model-release",
            resource_id=f"{body.model_id}@{body.version}",
            evidence={"package_sha256": body.package_sha256},
        )
        return await self._repository.create_release(release)

    async def list_releases(self, context: PrincipalContext) -> list[ModelRelease]:
        await require_allowed(self._policy, context, "model-release.read", "model-release")
        return await self._repository.list_releases(context.tenant_id, context.project_id)

    async def transition_release(
        self,
        context: PrincipalContext,
        model_id: str,
        version: str,
        body: TransitionModelReleaseRequest,
    ) -> ModelRelease:
        await require_allowed(self._policy, context, "model-release.transition", "model-release")
        current = await self._repository.get_release(context.tenant_id, context.project_id, model_id, version)
        if current is None:
            raise FeedbackNotFound("model release not found")
        validate_release_transition(current.status, body.status)
        package: ModelPackageManifest | None = None
        if body.status in {
            ModelReleaseStatus.VALIDATED,
            ModelReleaseStatus.APPROVED,
            ModelReleaseStatus.ACTIVE,
        }:
            package = await self._package(model_id, version, current.package_sha256)
            if package.runtime_model_id.startswith("legacy/"):
                raise FeedbackConflict("migrated model packages must be replaced before release")
            await self._validate_qualification_evidence(context, current, package)
        if body.status == ModelReleaseStatus.ACTIVE:
            assert package is not None
            if not package.production_ready:
                raise FeedbackConflict("only a production-ready package can be activated")
        audit = await self._audit.record(
            context,
            action="model-release.transition",
            resource_type="model-release",
            resource_id=f"{model_id}@{version}",
            evidence={"from": current.status.value, "to": body.status.value, "reason": body.reason},
        )
        updated, retired = await self._repository.transition_release(
            context.tenant_id,
            context.project_id,
            model_id,
            version,
            body.status,
        )
        await self._record_deployment_event(
            ModelDeploymentEvent(
                event_id=f"mde_{uuid4().hex}",
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                model_id=model_id,
                version=version,
                capability=updated.capability,
                runtime_model_id=updated.runtime_model_id,
                package_sha256=updated.package_sha256,
                action="transition",
                from_status=current.status,
                to_status=updated.status,
                reason=body.reason,
                operator_id=context.principal_id,
                audit_id=audit.event_id,
                created_at=time.time(),
            )
        )
        if retired is not None:
            await self._record_deployment_event(
                ModelDeploymentEvent(
                    event_id=f"mde_{uuid4().hex}",
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    model_id=retired.model_id,
                    version=retired.version,
                    capability=retired.capability,
                    runtime_model_id=retired.runtime_model_id,
                    package_sha256=retired.package_sha256,
                    action="superseded",
                    from_status=ModelReleaseStatus.ACTIVE,
                    to_status=ModelReleaseStatus.RETIRED,
                    reason=f"superseded by {model_id}@{version}",
                    operator_id=context.principal_id,
                    audit_id=audit.event_id,
                    created_at=time.time(),
                )
            )
        return updated

    async def rollback(
        self,
        context: PrincipalContext,
        model_id: str,
        body: RollbackModelReleaseRequest,
    ) -> ModelRelease:
        await require_allowed(self._policy, context, "model-release.rollback", "model-release")
        target = await self._repository.get_release(
            context.tenant_id, context.project_id, model_id, body.target_version
        )
        if target is None:
            raise FeedbackNotFound("rollback target not found")
        validate_release_transition(target.status, ModelReleaseStatus.ACTIVE, rollback=True)
        package = await self._package(model_id, target.version, target.package_sha256)
        if package.runtime_model_id.startswith("legacy/"):
            raise FeedbackConflict("migrated model packages cannot be rollback targets")
        if not package.production_ready:
            raise FeedbackConflict("rollback target package is not production-ready")
        await self._validate_qualification_evidence(context, target, package)
        audit = await self._audit.record(
            context,
            action="model-release.rollback",
            resource_type="model-release",
            resource_id=f"{model_id}@{target.version}",
            evidence={"reason": body.reason},
        )
        updated, retired = await self._repository.transition_release(
            context.tenant_id,
            context.project_id,
            model_id,
            target.version,
            ModelReleaseStatus.ACTIVE,
            rollback=True,
        )
        await self._record_deployment_event(
            ModelDeploymentEvent(
                event_id=f"mde_{uuid4().hex}",
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                model_id=model_id,
                version=target.version,
                capability=updated.capability,
                runtime_model_id=updated.runtime_model_id,
                package_sha256=updated.package_sha256,
                action="rollback",
                from_status=target.status,
                to_status=ModelReleaseStatus.ACTIVE,
                reason=body.reason,
                operator_id=context.principal_id,
                audit_id=audit.event_id,
                created_at=time.time(),
            )
        )
        if retired is not None:
            await self._record_deployment_event(
                ModelDeploymentEvent(
                    event_id=f"mde_{uuid4().hex}",
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    model_id=model_id,
                    version=retired.version,
                    capability=retired.capability,
                    runtime_model_id=retired.runtime_model_id,
                    package_sha256=retired.package_sha256,
                    action="rollback-retire",
                    from_status=ModelReleaseStatus.ACTIVE,
                    to_status=ModelReleaseStatus.RETIRED,
                    reason=body.reason,
                    operator_id=context.principal_id,
                    audit_id=audit.event_id,
                    created_at=time.time(),
                )
            )
        return updated

    async def deployment_events(
        self, context: PrincipalContext, limit: int = 100
    ) -> list[ModelDeploymentEvent]:
        await require_allowed(self._policy, context, "model-release.read", "model-deployment-event")
        return await self._repository.list_deployment_events(context.tenant_id, context.project_id, limit)

    async def active_runtime_bindings(
        self,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, RuntimeModelBinding]:
        packages = {
            (package.model_id, package.version, package.sha256): package
            for package in await self._catalog.list_model_packages()
        }
        bindings: dict[str, RuntimeModelBinding] = {}
        for release in await self._repository.list_releases(tenant_id, project_id):
            if release.status != ModelReleaseStatus.ACTIVE:
                continue
            package = packages.get((release.model_id, release.version, release.package_sha256))
            if package is None:
                raise FeedbackConflict("active model release package is unavailable")
            if package.runtime_model_id.startswith("legacy/"):
                continue
            if release.capability in bindings:
                raise FeedbackConflict("multiple active model releases target the same capability")
            bindings[release.capability] = RuntimeModelBinding(
                capability=release.capability,
                model_id=release.model_id,
                version=release.version,
                runtime_model_id=release.runtime_model_id,
                adapter=package.adapter,
                sha256=package.sha256,
                package_sha256=release.package_sha256,
            )
        return bindings

    async def _record_deployment_event(self, event: ModelDeploymentEvent) -> None:
        await self._repository.append_deployment_event(event)
        await self._state.enqueue_webhook_event(
            event.tenant_id,
            event.project_id,
            event_id=event.event_id,
            event_type="model.deployment.changed",
            payload=event.model_dump(mode="json"),
            created_at=event.created_at,
        )

    async def _package(self, model_id: str, version: str, sha256: str) -> ModelPackageManifest:
        for package in await self._catalog.list_model_packages():
            if package.model_id == model_id and package.version == version and package.sha256 == sha256:
                return package
        raise FeedbackConflict("model package is not registered or its checksum does not match")

    async def _validate_qualification_evidence(
        self,
        context: PrincipalContext,
        release: ModelRelease,
        package: ModelPackageManifest,
    ) -> None:
        if not release.evidence_refs:
            raise FeedbackConflict("model release qualification requires evidence references")
        prefix = f"tenants/{context.tenant_id}/projects/{context.project_id}/model-evidence/"
        evidence_types: set[str] = set()
        for reference in release.evidence_refs:
            object_key, expected_sha256 = reference.rsplit("#sha256=", 1)
            if not object_key.startswith(prefix):
                raise FeedbackConflict("model qualification evidence is outside the current tenant and project")
            try:
                validate_object_key(object_key)
                document = await self._objects.get(object_key)
            except Exception as exc:
                raise FeedbackConflict("model qualification evidence cannot be read") from exc
            if hashlib.sha256(document).hexdigest() != expected_sha256:
                raise FeedbackConflict("model qualification evidence checksum does not match")
            try:
                evidence = ModelQualificationEvidence.model_validate_json(document)
            except ValidationError as exc:
                raise FeedbackConflict("model qualification evidence is invalid") from exc
            if (
                evidence.model_id != release.model_id
                or evidence.model_version != release.version
                or evidence.package_sha256 != release.package_sha256
            ):
                raise FeedbackConflict("model qualification evidence does not match the release")
            if evidence.evidence_type in evidence_types:
                raise FeedbackConflict("model qualification evidence types must be unique")
            evidence_types.add(evidence.evidence_type)
        evaluation_type = self._evaluation_evidence_type(package)
        if evaluation_type is None:
            raise FeedbackConflict("model capability has no qualification evidence policy")
        required = {"model_rights", evaluation_type, "regression"}
        missing = sorted(required - evidence_types)
        if missing:
            raise FeedbackConflict("model qualification evidence is incomplete: " + ", ".join(missing))

    async def _verified_trace(
        self,
        context: PrincipalContext,
        body: CreateFeedbackRequest,
    ) -> VerifiedFeedbackTrace:
        run = await self._state.get_run(context.tenant_id, context.project_id, body.run_id)
        if run is None:
            raise FeedbackNotFound("feedback run not found")
        if run.status != RunStatus.COMPLETED:
            raise FeedbackConflict("feedback requires a completed run")
        reference = await self._state.get_result_reference(context.tenant_id, context.project_id, body.run_id)
        if reference is None:
            raise FeedbackNotFound("feedback result not found")
        document = await self._objects.get(reference.object_key)
        if hashlib.sha256(document).hexdigest() != reference.sha256:
            raise FeedbackConflict("feedback result checksum does not match its reference")
        result = ResultEnvelope.model_validate_json(document)
        if result.run_id != run.run_id or result.pipeline != run.pipeline:
            raise FeedbackConflict("feedback result provenance does not match its run")
        media_ref = result.asset_id or result.source_id
        if media_ref is None or media_ref != (run.asset_id or run.source_id):
            raise FeedbackConflict("feedback media provenance does not match its run")
        if not any(
            model.model_id == body.model_id and model.version == body.model_version
            for model in result.models
        ):
            raise FeedbackConflict("feedback model provenance is not present in the result")
        return {
            "result_ref": reference.object_key,
            "media_ref": media_ref,
            "pipeline_id": run.pipeline.pipeline_id,
            "pipeline_version": run.pipeline.version,
        }


__all__ = [
    "CreateFeedbackRequest",
    "CreateHardSampleManifestRequest",
    "CreateModelReleaseRequest",
    "FeedbackConflict",
    "FeedbackKind",
    "FeedbackNotFound",
    "FeedbackRecord",
    "FeedbackRepository",
    "FeedbackService",
    "FeedbackStatus",
    "HardSampleManifest",
    "MemoryFeedbackRepository",
    "ModelDeploymentEvent",
    "ModelRelease",
    "ModelReleaseStatus",
    "ReviewFeedbackRequest",
    "RollbackModelReleaseRequest",
    "TransitionModelReleaseRequest",
    "validate_release_transition",
]
