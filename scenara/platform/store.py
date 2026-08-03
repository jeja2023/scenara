from __future__ import annotations

from typing import Protocol

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
    RunStatus,
    WebhookDeliveryRecord,
    WebhookSubscription,
)
from scenara.platform.pipeline import PipelineDefinition


class StateConflict(RuntimeError):
    pass


class StateStore(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def health_check(self) -> None: ...

    async def register_pipeline_definition(self, pipeline: PipelineDefinition) -> None: ...

    async def get_pipeline_definition(self, pipeline_id: str, version: str) -> PipelineDefinition | None: ...

    async def list_pipeline_definitions(self) -> list[PipelineDefinition]: ...

    async def transition_pipeline_definition(
        self, pipeline_id: str, version: str, target: PipelineStatus
    ) -> PipelineDefinition: ...

    async def register_model_package(self, package: ModelPackageManifest) -> None: ...

    async def list_model_packages(self) -> list[ModelPackageManifest]: ...

    async def create_webhook_subscription(self, endpoint: WebhookSubscription) -> WebhookSubscription: ...

    async def get_webhook_subscription(
        self, tenant_id: str, project_id: str, endpoint_id: str
    ) -> WebhookSubscription | None: ...

    async def list_webhook_subscriptions(self, tenant_id: str, project_id: str) -> list[WebhookSubscription]: ...

    async def delete_webhook_subscription(
        self, tenant_id: str, project_id: str, endpoint_id: str
    ) -> WebhookSubscription | None: ...

    async def claim_webhook_deliveries(
        self, before: float, lease_until: float, limit: int
    ) -> list[WebhookDeliveryRecord]: ...

    async def save_webhook_delivery(self, delivery: WebhookDeliveryRecord) -> None: ...

    async def list_webhook_deliveries(
        self, tenant_id: str, project_id: str, limit: int
    ) -> list[WebhookDeliveryRecord]: ...

    async def enqueue_webhook_event(
        self,
        tenant_id: str,
        project_id: str,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, object],
        created_at: float,
    ) -> None: ...

    async def create_asset(self, asset: MediaAsset) -> MediaAsset: ...

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None: ...

    async def list_assets(
        self,
        tenant_id: str,
        project_id: str,
        *,
        include_deleted: bool = True,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[MediaAsset]: ...

    async def count_assets(self, tenant_id: str, project_id: str, *, include_deleted: bool = True) -> int: ...

    async def delete_asset(self, tenant_id: str, project_id: str, asset_id: str) -> MediaAsset | None: ...

    async def create_source(self, source: MediaSource) -> MediaSource: ...

    async def get_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None: ...

    async def list_sources(
        self,
        tenant_id: str,
        project_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[MediaSource]: ...

    async def count_sources(self, tenant_id: str, project_id: str) -> int: ...

    async def delete_source(self, tenant_id: str, project_id: str, source_id: str) -> MediaSource | None: ...

    async def create_run_idempotent(
        self,
        run: RunRecord,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[RunRecord, bool]: ...

    async def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None: ...

    async def list_runs(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: RunStatus | None = None,
        domain: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[RunRecord]: ...

    async def count_runs(
        self,
        tenant_id: str,
        project_id: str,
        *,
        status: RunStatus | None = None,
        domain: str | None = None,
    ) -> int: ...

    async def recoverable_runs(self) -> list[RunRecord]: ...

    async def has_non_terminal_run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        asset_id: str | None = None,
        source_id: str | None = None,
    ) -> bool: ...

    async def delete_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord | None: ...

    async def save_run(self, run: RunRecord, *, expected_revision: int) -> RunRecord: ...

    async def append_event(self, tenant_id: str, project_id: str, event: RunEvent) -> RunEvent: ...

    async def events_after(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_id: int,
    ) -> list[RunEvent]: ...

    async def save_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        result: ResultReference,
    ) -> None: ...

    async def get_result_reference(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> ResultReference | None: ...

    async def list_result_references(
        self,
        tenant_id: str,
        project_id: str,
        *,
        domain: str | None = None,
        media_kind: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ResultReference]: ...

    async def count_result_references(
        self,
        tenant_id: str,
        project_id: str,
        *,
        domain: str | None = None,
        media_kind: str | None = None,
        query: str | None = None,
    ) -> int: ...

    async def append_audit(self, event: AuditEvent) -> None: ...

    async def track_object(self, record: ObjectRetentionRecord) -> None: ...

    async def expired_object_keys(self, before: float, limit: int) -> list[str]: ...

    async def mark_objects_deleted(self, object_keys: list[str], deleted_at: float) -> None: ...

    async def audit_events(self, tenant_id: str, project_id: str) -> list[AuditEvent]: ...


__all__ = ["StateConflict", "StateStore"]
