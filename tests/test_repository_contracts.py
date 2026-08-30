from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from scenara.platform.repository_contracts import load_repository_contract_catalog
from scripts.repository_contracts import (
    CONTRACT_DIR,
    compatibility_errors,
    rendered_files,
    validate_contract_document,
)


def test_published_repository_contracts_match_models_examples_and_digests() -> None:
    files = rendered_files()
    catalog = load_repository_contract_catalog()
    assert catalog.release_version == "1.2.0"
    assert len(catalog.contracts) == 5
    for contract in catalog.contracts:
        schema_name = Path(contract.schema_path).name
        example_name = Path(contract.example_path).name
        schema_document = (CONTRACT_DIR / schema_name).read_bytes()
        example_document = (CONTRACT_DIR / example_name).read_bytes()
        assert schema_document == files[schema_name]
        assert example_document == files[example_name]
        assert hashlib.sha256(schema_document).hexdigest() == contract.schema_sha256
        assert hashlib.sha256(example_document).hexdigest() == contract.example_sha256
        Draft202012Validator(json.loads(schema_document)).validate(json.loads(example_document))


def test_compatibility_check_rejects_required_fields_removals_and_enum_narrowing() -> None:
    previous = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "status": {"type": "string", "enum": ["active", "retired"]},
        },
    }
    candidate = {
        "type": "object",
        "required": ["id", "reason"],
        "properties": {
            "id": {"type": "string"},
            "reason": {"type": "string"},
            "status": {"type": "string", "enum": ["active"]},
        },
    }
    errors = compatibility_errors(previous, candidate)
    assert any("new required properties: reason" in item for item in errors)
    assert any("removed enum values" in item for item in errors)

    removed = compatibility_errors(previous, {"type": "object", "properties": {"id": {"type": "string"}}})
    assert any("removed properties: status" in item for item in removed)


def test_compatibility_check_resolves_references_and_rejects_tighter_constraints() -> None:
    previous = {
        "type": "object",
        "$defs": {"Status": {"type": "string", "enum": ["active", "retired"]}},
        "properties": {
            "status": {"$ref": "#/$defs/Status"},
            "label": {"type": "string"},
        },
    }
    candidate = {
        "type": "object",
        "$defs": {"Status": {"type": "string", "enum": ["active"]}},
        "properties": {
            "status": {"$ref": "#/$defs/Status"},
            "label": {"type": "string", "minLength": 2},
        },
    }
    errors = compatibility_errors(previous, candidate)
    assert any("removed enum values" in item for item in errors)
    assert any("tightened minLength" in item for item in errors)


def test_semantic_validator_checks_cross_field_and_canonical_digests() -> None:
    files = rendered_files()
    model_package = json.loads(files["model-package-admission.example.json"])
    model_package["sha256"] = "9" * 64
    with pytest.raises(ValidationError, match="artifact reference digest"):
        validate_contract_document("model-package-admission", model_package)

    hard_sample = json.loads(files["hard-sample-handoff.example.json"])
    hard_sample["items"][0]["correction"]["label"] = "changed"
    with pytest.raises(SystemExit, match="checksum does not match"):
        validate_contract_document("hard-sample-handoff", hard_sample)


def test_typescript_openapi_digest_allow_marker_is_preserved_in_generated_artifacts() -> None:
    generated_files = (
        Path("sdk/typescript/src/generated.ts"),
        Path("sdk/typescript/dist/generated.js"),
        Path("sdk/typescript/dist/generated.d.ts"),
    )
    for path in generated_files:
        digest_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if "OPENAPI_SHA256" in line
        ]
        assert len(digest_lines) == 1, path
        assert "gitleaks:allow - public contract digest" in digest_lines[0], path
