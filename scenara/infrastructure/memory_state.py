from __future__ import annotations

import asyncio
from collections.abc import Iterable
from uuid import uuid4

from scenara.platform.audit import AuditEvent
from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import (
    MediaAsset,
    MediaSource,
    ObjectRetentionRecord,
    PipelineStatus,
    ResultReference,
    RunEvent,
    RunRecord,
    WebhookDeliveryRecord,
    WebhookSubscription,
)
from scenara.platform.pipeline import PipelineDefinition
from scenara.platform.store import StateConflict


class MemoryStateStore:
    """Development store. Production startup rejects this backend."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._assets: dict[tuple[str, str, str], MediaAsset] = {}
        self._sources: dict[tuple[str, str, str], MediaSource] = {}
        self._runs: dict[tuple[str, str, str], RunRecord] = {}
        self._events: dict[tuple[str, str, str], list[RunEvent]] = {}
        self._results: dict[tuple[str, str, str], ResultReference] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._audits: list[AuditEvent] = []
        self._object_retention: dict[tuple[str, str, str], ObjectRetentionRecord] = {}
        self._pipelines: dict[tuple[str, str], PipelineDefinition] = {}
        self._model_packages: dict[tuple[str, str], ModelPackageManifest] = {}
        self._webhook_subscriptions: dict[tuple[str, str, str], WebhookSubscription] = {}
        self._webhook_deliveries: dict[tuple[str, str, str], WebhookDeliveryRecord] = {}

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> None:
        return None

    async def register_pipeline_definition(self, pipeline: PipelineDefinition) -> None:
        async with self._lock:
            key = (pipeline.pipeline_id, pipeline.version)
            existing = self._pipelines.get(key)
            if existing is not None and existing.definition_sha256 != pipeline.definition_sha256:
                raise StateConflict("pipeline version definition is immutable")
            if existing is None:
                if pipeline.status.value == "active" and any(
                    item.pipeline_id == pipeline.pipeline_id and item.status.value == "active"
                    for item in self._pipelines.values()
                ):
                    raise StateConflict("pipeline already has an active version")
                self._pipelines[key] = pipeline.model_copy(deep=True)

    async def get_pipeline_definition(self, pipeline_id: str, version: str) -> PipelineDefinition | None:
        async with self._lock:
            pipeline = self._pipelines.get((pipeline_id, version))
            return pipeline.model_copy(deep=True) if pipeline else None

    async def list_pipeline_definitions(self) -> list[PipelineDefinition]:
        async with self._lock:
            return [item.model_copy(deep=True) for _, item in sorted(self._pipelines.items())]

    async def transition_pipeline_definition(
        self, pipeline_id: str, version: str, target: PipelineStatus
    ) -> PipelineDefinition:
        allowed = {
            PipelineStatus.DRAFT: {PipelineStatus.VALIDATED},
            PipelineStatus.VALIDATED: {PipelineStatus.APPROVED, PipelineStatus.DRAFT},
            PipelineStatus.APPROVED: {PipelineStatus.ACTIVE, PipelineStatus.DRAFT},
            PipelineStatus.ACTIVE: {PipelineStatus.RETIRED},
            PipelineStatus.RETIRED: set(),
        }
        async with self._lock:
            key = (pipeline_id, version)
            pipeline = self._pipelines.get(key)
            if pipeline is None:
                raise StateConflict("pipeline version does not exist")
            if target not in allowed[pipeline.status]:
                raise StateConflict(f"invalid pipeline transition: {pipeline.status.value} -> {target.value}")
            if target == PipelineStatus.ACTIVE:
                for other_key, other in list(self._pipelines.items()):
                    if other.pipeline_id == pipeline_id and other.status == PipelineStatus.ACTIVE:
                        self._pipelines[other_key] = other.model_copy(update={"status": PipelineStatus.RETIRED})
            updated = pipeline.model_copy(update={"status": target})
            self._pipelines[key] = updated
            return updated.model_copy(deep=True)

    async def register_model_package(self, package: ModelPackageManifest) -> None:
        async with self._lock:
            key = (package.model_id, package.version)
            existing = self._model_packages.get(key)
            if existing is not None and existing != package:
                raise StateConflict("model package version is immutable")
            self._model_packages[key] = package.model_copy(deep=True)

    async def list_model_packages(self) -> list[ModelPackageManifest]:
        async with self._lock:
            return [item.model_copy(deep=True) for _, item in sorted(self._model_packages.items())]

    async def create_webhook_subscription(self, endpoint: WebhookSubscription) -> WebhookSubscription:
        async with self._lock:
            key = self._key(endpoint.tenant_id, endpoint.project_id, endpoint.endpoint_id)
            if key in self._webhook_subscriptions:
                raise StateConflict("webhook subscription already exists")
            self._webhook_subscriptions[key] = endpoint.model_copy(deep=True)
            return endpoint.model_copy(deep=True)

    async def get_webhook_subscription(
        self, tenant_id: str, project_id: str, endpoint_id: str
    ) -> WebhookSubscription | None:
        async with self._lock:
            endpoint = self._webhook_subscriptions.get(self._key(tenant_id, project_id, endpoint_id))
            return endpoint.model_copy(deep=True) if endpoint else None

    async def list_webhook_subscriptions(self, tenant_id: str, project_id: str) -> list[WebhookSubscription]:
        async with self._lock:
            return [
                item.model_copy(deep=True)
                for key, item in sorted(self._webhook_subscriptions.items())
                if key[:2] == (tenant_id, project_id)
            ]

    async def delete_webhook_subscription(
        self, tenant_id: str, project_id: str, endpoint_id: str
    ) -> WebhookSubscription | None:
        async with self._lock:
            endpoint = self._webhook_subscriptions.pop(self._key(tenant_id, project_id, endpoint_id), None)
            stale = [
                key
                for key, item in self._webhook_deliveries.items()
                if (item.tenant_id, item.project_id, item.endpoint_id) == (tenant_id, project_id, endpoint_id)
            ]
            for key in stale:
                del self._webhook_deliveries[key]
            return endpoint.model_copy(deep=True) if endpoint else None

    async def claim_webhook_deliveries(
        self, before: float, lease_until: float, limit: int
    ) -> list[WebhookDeliveryRecord]:
        async with self._lock:
            due = sorted(
                (
                    item
                    for item in self._webhook_deliveries.values()
                    if item.status in {"pending", "delivering"} and item.next_attempt_at <= before
                ),
                key=lambda item: (item.next_attempt_at, item.created_at, item.delivery_id),
            )[:limit]
            claimed: list[WebhookDeliveryRecord] = []
            for item in due:
                updated = item.model_copy(
                    update={"status": "delivering", "next_attempt_at": lease_until, "updated_at": before}
                )
                self._webhook_deliveries[self._key(item.tenant_id, item.project_id, item.delivery_id)] = updated
                claimed.append(updated.model_copy(deep=True))
            return claimed

    async def save_webhook_delivery(self, delivery: WebhookDeliveryRecord) -> None:
        async with self._lock:
            key = self._key(delivery.tenant_id, delivery.project_id, delivery.delivery_id)
            if key not in self._webhook_deliveries:
                raise StateConflict("webhook delivery does not exist")
            self._webhook_deliveries[key] = delivery.model_copy(deep=True)

    async def list_webhook_deliveries(
        self, tenant_id: str, project_id: str, limit: int
    ) -> list[WebhookDeliveryRecord]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for key, item in self._webhook_deliveries.items()
                if key[:2] == (tenant_id, project_id)
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.delivery_id), reverse=True)[:limit]

    @staticmethod
    def _key(tenant_id: str, project_id: str, value_id: str) -> tuple[str, str, str]:
        return tenant_id, project_id, value_id

    async def create_asset(self, asset: MediaAsset) -> MediaAsset:
        async with self._lock:
            key = self._key(asset.tenant_id, asset.project_id, asset.asset_id)
            if key in self._assets:
                raise StateConflict("media asset already exists")
            self._assets[key] = asset.model_copy(deep=True)
        return asset.model_copy(deep=True)

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None:
        async with self._lock:
            asset = self._assets.get(self._key(tenant_id, project_id, asset_id))
            return asset.model_copy(deep=True) if asset else None

    async def list_assets(self, tenant_id: str, project_id: str) -> list[MediaAsset]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for (row_tenant, row_project, _), item in self._assets.items()
                if row_tenant == tenant_id and row_project == project_id
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.asset_id), reverse=True)

    async def create_source(self, source: MediaSource) -> MediaSource:
        async with self._lock:
            key = self._key(source.tenant_id, source.project_id, source.source_id)
            if key in self._sources:
                raise StateConflict("media source already exists")
            self._sources[key] = source.model_copy(deep=True)
        return source.model_copy(deep=True)

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None:
        async with self._lock:
            source = self._sources.get(self._key(tenant_id, project_id, source_id))
            return source.model_copy(deep=True) if source else None

    async def list_sources(self, tenant_id: str, project_id: str) -> list[MediaSource]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for (row_tenant, row_project, _), item in self._sources.items()
                if row_tenant == tenant_id and row_project == project_id
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.source_id), reverse=True)

    async def delete_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None:
        async with self._lock:
            return self._sources.pop(self._key(tenant_id, project_id, source_id), None)

    async def create_run_idempotent(
        self,
        run: RunRecord,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[RunRecord, bool]:
        async with self._lock:
            idem_key = self._key(run.tenant_id, run.project_id, idempotency_key)
            existing = self._idempotency.get(idem_key)
            if existing is not None:
                existing_hash, existing_run_id = existing
                if existing_hash != request_hash:
                    raise StateConflict("idempotency key was already used for a different request")
                existing_run = self._runs[self._key(run.tenant_id, run.project_id, existing_run_id)]
                return existing_run.model_copy(deep=True), False
            key = self._key(run.tenant_id, run.project_id, run.run_id)
            if key in self._runs:
                raise StateConflict("run already exists")
            self._runs[key] = run.model_copy(deep=True)
            self._events[key] = []
            self._idempotency[idem_key] = (request_hash, run.run_id)
            return run.model_copy(deep=True), True

    async def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None:
        async with self._lock:
            run = self._runs.get(self._key(tenant_id, project_id, run_id))
            return run.model_copy(deep=True) if run else None

    async def list_runs(self, tenant_id: str, project_id: str) -> list[RunRecord]:
        async with self._lock:
            rows = [
                item.model_copy(deep=True)
                for (row_tenant, row_project, _), item in self._runs.items()
                if row_tenant == tenant_id and row_project == project_id
            ]
        return sorted(rows, key=lambda item: (item.created_at, item.run_id), reverse=True)

    async def delete_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None:
        async with self._lock:
            key = self._key(tenant_id, project_id, run_id)
            run = self._runs.pop(key, None)
            self._events.pop(key, None)
            self._results.pop(key, None)
            stale = [
                idem_key
                for idem_key, (_, stored_run_id) in self._idempotency.items()
                if idem_key[:2] == (tenant_id, project_id) and stored_run_id == run_id
            ]
            for idem_key in stale:
                del self._idempotency[idem_key]
            return run

    async def save_run(self, run: RunRecord, *, expected_revision: int) -> RunRecord:
        async with self._lock:
            key = self._key(run.tenant_id, run.project_id, run.run_id)
            current = self._runs.get(key)
            if current is None:
                raise StateConflict("run does not exist")
            if current.revision != expected_revision:
                raise StateConflict("run revision conflict")
            saved = run.model_copy(update={"revision": expected_revision + 1}, deep=True)
            self._runs[key] = saved
            return saved.model_copy(deep=True)

    async def append_event(self, tenant_id: str, project_id: str, event: RunEvent) -> RunEvent:
        async with self._lock:
            key = self._key(tenant_id, project_id, event.run_id)
            rows = self._events.get(key)
            if rows is None:
                raise StateConflict("run does not exist")
            stored = event.model_copy(update={"event_id": len(rows) + 1}, deep=True)
            rows.append(stored)
            self._enqueue_webhook_event(
                tenant_id,
                project_id,
                event_id=f"{stored.run_id}:{stored.event_id}",
                event_type=stored.event_type,
                payload=stored.model_dump(mode="json"),
                created_at=stored.created_at,
            )
            return stored.model_copy(deep=True)

    async def enqueue_webhook_event(
        self,
        tenant_id: str,
        project_id: str,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, object],
        created_at: float,
    ) -> None:
        async with self._lock:
            self._enqueue_webhook_event(
                tenant_id,
                project_id,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                created_at=created_at,
            )

    def _enqueue_webhook_event(
        self,
        tenant_id: str,
        project_id: str,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, object],
        created_at: float,
    ) -> None:
        for endpoint in self._webhook_subscriptions.values():
            if (
                endpoint.tenant_id == tenant_id
                and endpoint.project_id == project_id
                and endpoint.enabled
                and event_type in endpoint.event_types
            ):
                delivery = WebhookDeliveryRecord(
                    delivery_id=f"whd_{uuid4().hex}",
                    tenant_id=tenant_id,
                    project_id=project_id,
                    endpoint_id=endpoint.endpoint_id,
                    event_id=event_id,
                    event_type=event_type,
                    payload=payload,
                    next_attempt_at=created_at,
                    created_at=created_at,
                    updated_at=created_at,
                )
                self._webhook_deliveries[self._key(tenant_id, project_id, delivery.delivery_id)] = delivery

    async def events_after(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_id: int,
    ) -> list[RunEvent]:
        async with self._lock:
            rows: Iterable[RunEvent] = self._events.get(self._key(tenant_id, project_id, run_id), [])
            return [item.model_copy(deep=True) for item in rows if item.event_id > event_id]

    async def save_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        result: ResultReference,
    ) -> None:
        async with self._lock:
            self._results[self._key(tenant_id, project_id, result.run_id)] = result.model_copy(deep=True)

    async def get_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> ResultReference | None:
        async with self._lock:
            result = self._results.get(self._key(tenant_id, project_id, run_id))
            return result.model_copy(deep=True) if result else None

    async def append_audit(self, event: AuditEvent) -> None:
        async with self._lock:
            self._audits.append(event)

    async def audit_events(self, tenant_id: str, project_id: str) -> list[AuditEvent]:
        async with self._lock:
            return [item for item in self._audits if item.tenant_id == tenant_id and item.project_id == project_id]

    async def track_object(self, record: ObjectRetentionRecord) -> None:
        async with self._lock:
            key = self._key(record.tenant_id, record.project_id, record.object_key)
            existing = self._object_retention.get(key)
            if existing is not None and existing != record:
                raise StateConflict("object retention record already exists")
            self._object_retention[key] = record.model_copy(deep=True)

    async def expired_object_keys(self, before: float, limit: int) -> list[str]:
        async with self._lock:
            keys = [
                item.object_key
                for item in self._object_retention.values()
                if item.expires_at is not None and item.expires_at <= before and item.deleted_at is None
            ]
        return sorted(keys)[:limit]

    async def mark_objects_deleted(self, object_keys: list[str], deleted_at: float) -> None:
        targets = set(object_keys)
        async with self._lock:
            result_owners: set[tuple[str, str, str]] = set()
            raw_asset_owners: set[tuple[str, str, str]] = set()
            preview_asset_owners: set[tuple[str, str, str]] = set()
            for key, retention in list(self._object_retention.items()):
                if retention.object_key in targets:
                    self._object_retention[key] = retention.model_copy(update={"deleted_at": deleted_at})
                    if retention.owner_type == "run_result":
                        result_owners.add((retention.tenant_id, retention.project_id, retention.owner_id))
                    elif retention.owner_type == "media_asset" and retention.category == "raw_media":
                        raw_asset_owners.add((retention.tenant_id, retention.project_id, retention.owner_id))
                    elif retention.owner_type == "media_asset" and retention.category == "preview":
                        preview_asset_owners.add((retention.tenant_id, retention.project_id, retention.owner_id))
            for key, asset in list(self._assets.items()):
                updates: dict[str, object] = {}
                if key in raw_asset_owners:
                    updates["original_deleted_at"] = deleted_at
                if key in preview_asset_owners:
                    updates.update(
                        {
                            "preview_object_key": None,
                            "preview_content_type": None,
                            "preview_sha256": None,
                        }
                    )
                    if key in raw_asset_owners or asset.original_deleted_at is not None:
                        updates["deleted_at"] = deleted_at
                if updates:
                    self._assets[key] = asset.model_copy(update=updates)
            for tenant_id, project_id, run_id in result_owners:
                remaining = any(
                    item.owner_type == "run_result"
                    and (item.tenant_id, item.project_id, item.owner_id) == (tenant_id, project_id, run_id)
                    and item.deleted_at is None
                    for item in self._object_retention.values()
                )
                if not remaining:
                    self._results.pop(self._key(tenant_id, project_id, run_id), None)

    async def delete_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None:
        async with self._lock:
            return self._assets.pop(self._key(tenant_id, project_id, asset_id), None)


__all__ = ["MemoryStateStore"]
