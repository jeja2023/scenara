from __future__ import annotations

import time
from uuid import uuid4

from scenara.platform.audit import AuditLogger
from scenara.platform.models import (
    CreateDatasetRequest,
    CreateDatasetVersionRequest,
    DatasetPage,
    DatasetRecord,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionPage,
    DatasetVersionStatus,
    PrincipalContext,
    TransitionDatasetVersionRequest,
    UpdateDatasetRequest,
)
from scenara.platform.policy import PolicyProvider, require_allowed
from scenara.platform.store import StateConflict, StateStore


class DatasetNotFound(RuntimeError):
    pass


class DatasetConflict(RuntimeError):
    pass


class DatasetService:
    def __init__(self, state: StateStore, policy: PolicyProvider, audit: AuditLogger) -> None:
        self.state = state
        self.policy = policy
        self.audit = audit

    async def create(self, context: PrincipalContext, request: CreateDatasetRequest) -> DatasetRecord:
        await require_allowed(self.policy, context, "create", "dataset")
        now = time.time()
        dataset = DatasetRecord(
            dataset_id=f"dst_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            name=request.name,
            description=request.description,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )
        try:
            stored = await self.state.create_dataset(dataset)
        except StateConflict as exc:
            raise DatasetConflict(str(exc)) from exc
        await self.audit.record(
            context,
            action="dataset.create",
            resource_type="dataset",
            resource_id=dataset.dataset_id,
        )
        return stored

    async def get(self, context: PrincipalContext, dataset_id: str) -> DatasetRecord:
        await require_allowed(self.policy, context, "read", "dataset", {"dataset_id": dataset_id})
        dataset = await self.state.get_dataset(context.tenant_id, context.project_id, dataset_id)
        if dataset is None:
            raise DatasetNotFound("dataset not found")
        return dataset

    async def list(self, context: PrincipalContext, *, offset: int, limit: int) -> DatasetPage:
        await require_allowed(self.policy, context, "list", "dataset")
        items = await self.state.list_datasets(
            context.tenant_id,
            context.project_id,
            offset=offset,
            limit=limit,
        )
        return DatasetPage(
            items=items,
            offset=offset,
            limit=limit,
            total=await self.state.count_datasets(context.tenant_id, context.project_id),
        )

    async def update(
        self,
        context: PrincipalContext,
        dataset_id: str,
        request: UpdateDatasetRequest,
    ) -> DatasetRecord:
        await require_allowed(self.policy, context, "update", "dataset", {"dataset_id": dataset_id})
        current = await self.get(context, dataset_id)
        changes = request.model_dump(exclude_unset=True)
        if changes.get("status") is not None:
            changes["status"] = DatasetStatus(changes["status"])
        updated = current.model_copy(update={**changes, "updated_at": time.time()})
        try:
            saved = await self.state.save_dataset(updated)
        except StateConflict as exc:
            raise DatasetConflict(str(exc)) from exc
        await self.audit.record(
            context,
            action="dataset.update",
            resource_type="dataset",
            resource_id=dataset_id,
            evidence={"status": saved.status.value},
        )
        return saved

    async def create_version(
        self,
        context: PrincipalContext,
        dataset_id: str,
        request: CreateDatasetVersionRequest,
    ) -> DatasetVersion:
        await require_allowed(self.policy, context, "create", "dataset_version", {"dataset_id": dataset_id})
        dataset = await self.get(context, dataset_id)
        asset_ids = list(dict.fromkeys(request.asset_ids))
        if len(asset_ids) != len(request.asset_ids):
            raise DatasetConflict("dataset version asset IDs must be unique")
        missing = []
        for asset_id in asset_ids:
            asset = await self.state.get_asset(context.tenant_id, context.project_id, asset_id)
            if asset is None or asset.deleted_at is not None or asset.original_deleted_at is not None:
                missing.append(asset_id)
        if missing:
            raise DatasetConflict(f"dataset version references missing assets: {', '.join(missing[:10])}")
        now = time.time()
        version = DatasetVersion(
            version_id=f"dsv_{uuid4().hex}",
            dataset_id=dataset.dataset_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            version=request.version,
            manifest_sha256=request.manifest_sha256.lower(),
            asset_ids=asset_ids,
            item_count=len(asset_ids),
            quality_score=request.quality_score,
            lineage=request.lineage,
            annotation_summary=request.annotation_summary,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
        )
        try:
            stored = await self.state.create_dataset_version(version)
        except StateConflict as exc:
            raise DatasetConflict(str(exc)) from exc
        await self.audit.record(
            context,
            action="dataset.version.create",
            resource_type="dataset_version",
            resource_id=version.version_id,
            evidence={"dataset_id": dataset_id, "asset_count": len(asset_ids)},
        )
        return stored

    async def list_versions(
        self,
        context: PrincipalContext,
        dataset_id: str,
        *,
        offset: int,
        limit: int,
    ) -> DatasetVersionPage:
        await require_allowed(self.policy, context, "list", "dataset_version", {"dataset_id": dataset_id})
        await self.get(context, dataset_id)
        items = await self.state.list_dataset_versions(
            context.tenant_id,
            context.project_id,
            dataset_id,
            offset=offset,
            limit=limit,
        )
        return DatasetVersionPage(
            items=items,
            offset=offset,
            limit=limit,
            total=await self.state.count_dataset_versions(context.tenant_id, context.project_id, dataset_id),
        )

    async def transition_version(
        self,
        context: PrincipalContext,
        version_id: str,
        request: TransitionDatasetVersionRequest,
    ) -> DatasetVersion:
        await require_allowed(self.policy, context, "transition", "dataset_version", {"version_id": version_id})
        version = await self.state.get_dataset_version(context.tenant_id, context.project_id, version_id)
        if version is None:
            raise DatasetNotFound("dataset version not found")
        allowed = {
            DatasetVersionStatus.DRAFT: {DatasetVersionStatus.VALIDATED, DatasetVersionStatus.RETIRED},
            DatasetVersionStatus.VALIDATED: {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.RETIRED},
            DatasetVersionStatus.PUBLISHED: {DatasetVersionStatus.RETIRED},
            DatasetVersionStatus.RETIRED: set(),
        }
        if request.status not in allowed[version.status]:
            raise DatasetConflict(
                f"dataset version cannot transition from {version.status.value} to {request.status.value}"
            )
        if request.status == DatasetVersionStatus.PUBLISHED:
            if not version.asset_ids:
                raise DatasetConflict("published dataset versions require at least one asset")
            if version.quality_score is None:
                raise DatasetConflict("published dataset versions require a quality score")
        updated = version.model_copy(update={"status": request.status, "updated_at": time.time()})
        try:
            saved = await self.state.save_dataset_version(updated)
        except StateConflict as exc:
            raise DatasetConflict(str(exc)) from exc
        if request.status == DatasetVersionStatus.PUBLISHED:
            dataset = await self.get(context, version.dataset_id)
            if dataset.status != DatasetStatus.ACTIVE:
                await self.state.save_dataset(
                    dataset.model_copy(update={"status": DatasetStatus.ACTIVE, "updated_at": time.time()})
                )
        await self.audit.record(
            context,
            action="dataset.version.transition",
            resource_type="dataset_version",
            resource_id=version_id,
            evidence={"from": version.status.value, "to": request.status.value},
        )
        return saved


__all__ = ["DatasetConflict", "DatasetNotFound", "DatasetService"]
