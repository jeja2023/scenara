from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scenara.platform.audit import AuditEvent


class DataEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    event_version: str = Field(pattern=r"^\d+\.\d+$")
    occurred_at: datetime
    producer: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    data: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("occurred_at must use UTC")
        return value

    def payload_hash(self) -> str:
        content = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def audit_event(self) -> AuditEvent:
        resource_id = next(
            (
                str(self.data[key])
                for key in (
                    "dataset_version_id",
                    "version_id",
                    "dataset_id",
                    "task_id",
                    "annotation_id",
                    "run_id",
                    "migration_id",
                    "import_id",
                )
                if self.data.get(key) is not None
            ),
            self.event_id,
        )
        return AuditEvent(
            event_id=f"aud_data_{hashlib.sha256(self.event_id.encode('utf-8')).hexdigest()[:24]}",
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            principal_id=self.producer,
            action=f"data.event.{self.event_type}",
            resource_type="data_event",
            resource_id=resource_id,
            outcome="success",
            request_id=self.request_id,
            evidence={
                "event_id": self.event_id,
                "event_version": self.event_version,
                "producer": self.producer,
                "trace_id": self.trace_id,
                "occurred_at": self.occurred_at.isoformat().replace("+00:00", "Z"),
                "data": self.data,
            },
            created_at=self.occurred_at.timestamp(),
        )


__all__ = ["DataEventEnvelope"]
