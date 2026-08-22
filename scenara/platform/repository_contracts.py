from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_RELEASE_VERSION = "1.0.1"
CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "contracts" / "repository" / f"v{CONTRACT_RELEASE_VERSION}"
SHA256 = r"^[0-9a-f]{64}$"
IMMUTABLE_URI = r"^.+(?:@sha256:|#sha256=)[0-9a-f]{64}$"
RFC3339_UTC = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_utc_rfc3339(value: str) -> str:
    normalized = value.strip()
    if re.fullmatch(RFC3339_UTC, normalized) is None:
        raise ValueError("时间必须是以 Z 结尾的 UTC RFC3339 字符串")
    datetime.fromisoformat(normalized[:-1] + "+00:00")
    return normalized


class DatasetVersionReference(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$")
    manifest_uri: str = Field(pattern=IMMUTABLE_URI, max_length=2048)
    manifest_sha256: str = Field(pattern=SHA256)
    lineage_refs: tuple[str, ...] = Field(min_length=1, max_length=100)
    authorization_id: str = Field(min_length=1, max_length=256)
    authorized_consumer_repository_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    created_at: str = Field(pattern=RFC3339_UTC)

    @field_validator("created_at")
    @classmethod
    def utc_created_at(cls, value: str) -> str:
        return _validate_utc_rfc3339(value)

    @field_validator("lineage_refs")
    @classmethod
    def immutable_lineage(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(
            len(item) > 2048 or not re.fullmatch(IMMUTABLE_URI, item)
            for item in value
        ):
            raise ValueError("dataset lineage references must be unique immutable references")
        return value

    @model_validator(mode="after")
    def matching_manifest_digest(self) -> DatasetVersionReference:
        if not self.manifest_uri.endswith((f"@sha256:{self.manifest_sha256}", f"#sha256={self.manifest_sha256}")):
            raise ValueError("dataset manifest URI digest must match manifest_sha256")
        return self


class RepositoryContractArtifact(ContractModel):
    contract_id: str
    payload_type: str
    release_version: str
    payload_schema_version: str
    producer_repository_id: str
    consumer_repository_id: str
    transport: Literal["versioned_api", "event", "immutable_manifest"]
    compatibility: Literal["backward"] = "backward"
    schema_path: str
    schema_sha256: str = Field(pattern=SHA256)
    example_path: str
    example_sha256: str = Field(pattern=SHA256)


class RepositoryContractCatalog(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    release_version: str
    package_name: str
    contracts: list[RepositoryContractArtifact]


def load_repository_contract_catalog() -> RepositoryContractCatalog:
    manifest = CONTRACT_ROOT / "manifest.json"
    return RepositoryContractCatalog.model_validate_json(manifest.read_bytes())


ContractId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]


__all__ = [
    "CONTRACT_RELEASE_VERSION",
    "CONTRACT_ROOT",
    "ContractId",
    "DatasetVersionReference",
    "RepositoryContractArtifact",
    "RepositoryContractCatalog",
    "load_repository_contract_catalog",
]
