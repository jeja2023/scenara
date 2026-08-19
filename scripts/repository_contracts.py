from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenara.platform.feedback import (  # noqa: E402
    FeedbackKind,
    HardSampleItem,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelReleaseStatus,
)
from scenara.platform.model_runtime import ModelPackageManifest  # noqa: E402
from scenara.platform.repository_contracts import (  # noqa: E402
    CONTRACT_RELEASE_VERSION,
    DatasetVersionReference,
)

CONTRACT_DIR = ROOT / "contracts" / "repository" / f"v{CONTRACT_RELEASE_VERSION}"
RELEASE_INDEX = ROOT / "contracts" / "repository" / "release-index.json"
PACKAGE_NAME = "@scenara/repository-contracts"


def sha256(document: bytes) -> str:
    return hashlib.sha256(document).hexdigest()


def json_document(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def hard_sample_digest(document: dict[str, Any]) -> str:
    payload = {
        "schema_version": document["schema_version"],
        "dataset_id": document["dataset_id"],
        "version": document["version"],
        "label_schema": document["label_schema"],
        "split": document["split"],
        "items": document["items"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode("utf-8"))


def contract_definitions() -> list[dict[str, Any]]:
    artifact_sha = "a" * 64
    card_sha = "b" * 64
    evidence_sha = "c" * 64
    manifest_sha = "d" * 64
    lineage_sha = "e" * 64
    hard_sample = HardSampleManifest(
        manifest_id="hsm_contractexample",
        tenant_id="tenant-example",
        project_id="project-example",
        dataset_id="portrait.hard-samples",
        version="1.0.0",
        items=(
            HardSampleItem(
                feedback_id="fbk_contractexample",
                kind=FeedbackKind.FALSE_NEGATIVE,
                media_ref="objects/media/example",
                result_ref="objects/results/example.json",
                model_id="scenara.portrait.person-detector",
                model_version="1.0.0",
                pipeline_id="portrait.person-detection",
                pipeline_version="0.1.0",
                correction={"label": "person", "bbox": [1, 2, 30, 40]},
            ),
        ),
        sha256="0" * 64,
        created_by="service-account:model-feedback-exporter",
        created_at="2026-08-18T00:00:00Z",
    )
    hard_sample = hard_sample.model_copy(update={"sha256": hard_sample_digest(hard_sample.model_dump(mode="json"))})
    return [
        {
            "contract_id": "model-package-admission",
            "payload_type": "ModelPackageManifest",
            "model": ModelPackageManifest,
            "producer_repository_id": "scenara-model",
            "consumer_repository_id": "scenara",
            "transport": "immutable_manifest",
            "example": ModelPackageManifest(
                model_id="scenara.portrait.person-detector",
                version="1.0.0",
                capability="person_detection",
                adapter="yolo",
                runtime_model_id="scenara.portrait/person_detector_v1",
                sha256=artifact_sha,
                source_uri=f"oci://registry.example/scenara/person-detector@sha256:{artifact_sha}",
                license_id="LicenseRef-Proprietary-Approved",
                model_card=f"https://artifacts.example/model-card.json#sha256={card_sha}",
                evaluation_evidence=(f"https://artifacts.example/evaluation.json#sha256={evidence_sha}",),
                vram_mb=4096,
                regression_samples=("portrait-regression-v1",),
                production_ready=True,
            ),
        },
        {
            "contract_id": "hard-sample-handoff",
            "payload_type": "HardSampleManifest",
            "model": HardSampleManifest,
            "producer_repository_id": "scenara",
            "consumer_repository_id": "scenara-data",
            "transport": "immutable_manifest",
            "example": hard_sample,
        },
        {
            "contract_id": "dataset-version-input",
            "payload_type": "DatasetVersionReference",
            "model": DatasetVersionReference,
            "producer_repository_id": "scenara-data",
            "consumer_repository_id": "scenara-model",
            "transport": "versioned_api",
            "example": DatasetVersionReference(
                dataset_id="portrait.training",
                version="2.1.0",
                manifest_uri=f"https://data.example/manifests/2.1.0.json#sha256={manifest_sha}",
                manifest_sha256=manifest_sha,
                lineage_refs=(f"https://data.example/lineage/source.json#sha256={lineage_sha}",),
                authorization_id="grant_training_2026_07",
                authorized_consumer_repository_ids=("scenara-model",),
                created_at="2026-08-18T00:00:00Z",
            ),
        },
        {
            "contract_id": "deployment-feedback",
            "payload_type": "ModelDeploymentEvent",
            "model": ModelDeploymentEvent,
            "producer_repository_id": "scenara",
            "consumer_repository_id": "scenara-model",
            "transport": "event",
            "example": ModelDeploymentEvent(
                event_id="mde_contractexample",
                tenant_id="tenant-example",
                project_id="project-example",
                model_id="scenara.portrait.person-detector",
                version="1.0.0",
                capability="person_detection",
                runtime_model_id="scenara.portrait/person_detector_v1",
                package_sha256=artifact_sha,
                action="transition",
                from_status=ModelReleaseStatus.APPROVED,
                to_status=ModelReleaseStatus.ACTIVE,
                reason="qualification passed",
                operator_id="service-account:model-release-manager",
                audit_id="aud_contractexample",
                created_at="2026-08-18T00:00:00Z",
            ),
        },
    ]


def rendered_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    manifest_contracts: list[dict[str, Any]] = []
    for definition in contract_definitions():
        contract_id = str(definition["contract_id"])
        model = definition["model"]
        assert isinstance(model, type) and issubclass(model, BaseModel)
        schema = model.model_json_schema(mode="serialization")
        schema.update(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://contracts.scenara.dev/repository/{CONTRACT_RELEASE_VERSION}/{contract_id}.schema.json",
            }
        )
        schema_name = f"{contract_id}.schema.json"
        example_name = f"{contract_id}.example.json"
        schema_bytes = json_document(schema)
        example = definition["example"]
        assert isinstance(example, BaseModel)
        example_bytes = json_document(example.model_dump(mode="json"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(json.loads(example_bytes))
        files[schema_name] = schema_bytes
        files[example_name] = example_bytes
        manifest_contracts.append(
            {
                "contract_id": contract_id,
                "payload_type": definition["payload_type"],
                "release_version": CONTRACT_RELEASE_VERSION,
                "payload_schema_version": "1.0",
                "producer_repository_id": definition["producer_repository_id"],
                "consumer_repository_id": definition["consumer_repository_id"],
                "transport": definition["transport"],
                "compatibility": "backward",
                "schema_path": f"contracts/repository/v{CONTRACT_RELEASE_VERSION}/{schema_name}",
                "schema_sha256": sha256(schema_bytes),
                "example_path": f"contracts/repository/v{CONTRACT_RELEASE_VERSION}/{example_name}",
                "example_sha256": sha256(example_bytes),
            }
        )
    files["manifest.json"] = json_document(
        {
            "schema_version": "1.0",
            "release_version": CONTRACT_RELEASE_VERSION,
            "package_name": PACKAGE_NAME,
            "contracts": manifest_contracts,
        }
    )
    return files


def required_properties(schema: dict[str, Any]) -> set[str]:
    value = schema.get("required", [])
    return {str(item) for item in value} if isinstance(value, list) else set()


def _resolved(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return schema
    current: Any = root
    for part in reference[2:].split("/"):
        if not isinstance(current, dict):
            return schema
        current = current.get(part.replace("~1", "/").replace("~0", "~"))
    return current if isinstance(current, dict) else schema


def compatibility_errors(
    previous: dict[str, Any],
    candidate: dict[str, Any],
    path: str = "$",
    *,
    previous_root: dict[str, Any] | None = None,
    candidate_root: dict[str, Any] | None = None,
) -> list[str]:
    previous_root = previous if previous_root is None else previous_root
    candidate_root = candidate if candidate_root is None else candidate_root
    previous = _resolved(previous, previous_root)
    candidate = _resolved(candidate, candidate_root)
    errors: list[str] = []
    previous_required = required_properties(previous)
    candidate_required = required_properties(candidate)
    added_required = sorted(candidate_required - previous_required)
    if added_required:
        errors.append(f"{path}: new required properties: {', '.join(added_required)}")
    previous_properties = previous.get("properties", {})
    candidate_properties = candidate.get("properties", {})
    if isinstance(previous_properties, dict) and isinstance(candidate_properties, dict):
        removed = sorted(set(previous_properties) - set(candidate_properties))
        if removed:
            errors.append(f"{path}: removed properties: {', '.join(removed)}")
        for name in sorted(set(previous_properties) & set(candidate_properties)):
            old = previous_properties[name]
            new = candidate_properties[name]
            if isinstance(old, dict) and isinstance(new, dict):
                errors.extend(
                    compatibility_errors(
                        old,
                        new,
                        f"{path}.{name}",
                        previous_root=previous_root,
                        candidate_root=candidate_root,
                    )
                )
    previous_enum = previous.get("enum")
    candidate_enum = candidate.get("enum")
    if not isinstance(previous_enum, list) and isinstance(candidate_enum, list):
        errors.append(f"{path}: added enum constraint")
    if isinstance(previous_enum, list) and isinstance(candidate_enum, list):
        removed_values = [item for item in previous_enum if item not in candidate_enum]
        if removed_values:
            errors.append(f"{path}: removed enum values: {removed_values}")
    previous_type = previous.get("type")
    candidate_type = candidate.get("type")
    if previous_type is None and candidate_type is not None:
        errors.append(f"{path}: added type constraint {candidate_type}")
    if previous_type is not None and candidate_type is not None:
        old_types = set(previous_type if isinstance(previous_type, list) else [previous_type])
        new_types = set(candidate_type if isinstance(candidate_type, list) else [candidate_type])
        if not old_types <= new_types:
            errors.append(f"{path}: narrowed types from {sorted(old_types)} to {sorted(new_types)}")
    for keyword in ("pattern", "format", "const"):
        if keyword in candidate and previous.get(keyword) != candidate.get(keyword):
            errors.append(f"{path}: changed {keyword} constraint")
    for keyword in ("minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties"):
        old_value = previous.get(keyword)
        new_value = candidate.get(keyword)
        if isinstance(new_value, (int, float)) and (not isinstance(old_value, (int, float)) or new_value > old_value):
            errors.append(f"{path}: tightened {keyword} from {old_value} to {new_value}")
    for keyword in ("maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties"):
        old_value = previous.get(keyword)
        new_value = candidate.get(keyword)
        if isinstance(new_value, (int, float)) and (not isinstance(old_value, (int, float)) or new_value < old_value):
            errors.append(f"{path}: tightened {keyword} from {old_value} to {new_value}")
    if previous.get("additionalProperties", True) is not False and candidate.get("additionalProperties", True) is False:
        errors.append(f"{path}: additional properties are no longer accepted")
    if previous.get("uniqueItems") is not True and candidate.get("uniqueItems") is True:
        errors.append(f"{path}: array items must now be unique")
    previous_items = previous.get("items")
    candidate_items = candidate.get("items")
    if isinstance(previous_items, dict) and isinstance(candidate_items, dict):
        errors.extend(
            compatibility_errors(
                previous_items,
                candidate_items,
                f"{path}[]",
                previous_root=previous_root,
                candidate_root=candidate_root,
            )
        )
    for keyword in ("anyOf", "oneOf"):
        old_variants = previous.get(keyword)
        new_variants = candidate.get(keyword)
        if not isinstance(old_variants, list) and isinstance(new_variants, list):
            errors.append(f"{path}: added {keyword} constraint")
        if isinstance(old_variants, list) and isinstance(new_variants, list):
            for index, old_variant in enumerate(old_variants):
                if not isinstance(old_variant, dict):
                    continue
                compatible = any(
                    isinstance(new_variant, dict)
                    and not compatibility_errors(
                        old_variant,
                        new_variant,
                        f"{path}.{keyword}[{index}]",
                        previous_root=previous_root,
                        candidate_root=candidate_root,
                    )
                    for new_variant in new_variants
                )
                if not compatible:
                    errors.append(f"{path}: removed or narrowed {keyword} variant {index}")
    return errors


def validate_contract_document(contract_id: str, document: dict[str, Any]) -> BaseModel:
    definition = next(
        (item for item in contract_definitions() if item["contract_id"] == contract_id),
        None,
    )
    if definition is None:
        raise SystemExit(f"unknown repository contract: {contract_id}")
    model = definition["model"]
    assert isinstance(model, type) and issubclass(model, BaseModel)
    validated = model.model_validate(document)
    if contract_id == "hard-sample-handoff" and document.get("sha256") != hard_sample_digest(document):
        raise SystemExit("hard-sample-handoff payload checksum does not match its canonical content")
    return validated


def verify_compatibility(previous_dir: Path, candidate_files: dict[str, bytes]) -> None:
    errors: list[str] = []
    for name, document in candidate_files.items():
        if not name.endswith(".schema.json"):
            continue
        previous_path = previous_dir / name
        if not previous_path.is_file():
            continue
        previous = json.loads(previous_path.read_bytes())
        candidate = json.loads(document)
        errors.extend(f"{name}: {item}" for item in compatibility_errors(previous, candidate))
    if errors:
        raise SystemExit("repository contract compatibility failed:\n" + "\n".join(errors))


def write_files(output_dir: Path, files: dict[str, bytes]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, document in files.items():
        (output_dir / name).write_bytes(document)


def check_files(output_dir: Path, files: dict[str, bytes]) -> None:
    drift = [
        name
        for name, document in files.items()
        if not (output_dir / name).is_file() or (output_dir / name).read_bytes() != document
    ]
    unexpected = sorted(path.name for path in output_dir.glob("*.json") if path.name not in files)
    if drift or unexpected:
        details = [*(f"drifted: {name}" for name in drift), *(f"unexpected: {name}" for name in unexpected)]
        raise SystemExit("repository contracts drifted; run scripts/repository_contracts.py\n" + "\n".join(details))


def check_release_index(output_dir: Path) -> None:
    document = json.loads(RELEASE_INDEX.read_bytes())
    releases = document.get("releases", [])
    release = next(
        (item for item in releases if item.get("release_version") == CONTRACT_RELEASE_VERSION),
        None,
    )
    if release is None or release.get("status") != "published":
        raise SystemExit(f"repository contract release {CONTRACT_RELEASE_VERSION} is not published")
    manifest = output_dir / "manifest.json"
    if release.get("manifest_sha256") != sha256(manifest.read_bytes()):
        raise SystemExit("published repository contract release is immutable; publish a new semantic version")


def build_bundle(output: Path, source_dir: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.glob("*.json")):
            info = zipfile.ZipInfo(f"repository-contracts-{CONTRACT_RELEASE_VERSION}/{path.name}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate, validate, and package cross-repository contracts")
    parser.add_argument("--output-dir", type=Path, default=CONTRACT_DIR)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--against", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--verify-contract")
    parser.add_argument("--verify-document", type=Path)
    args = parser.parse_args()
    files = rendered_files()
    if args.verify_contract or args.verify_document:
        if not args.verify_contract or args.verify_document is None:
            raise SystemExit("--verify-contract and --verify-document must be used together")
        schema_name = f"{args.verify_contract}.schema.json"
        if schema_name not in files:
            raise SystemExit(f"unknown repository contract: {args.verify_contract}")
        document = json.loads(args.verify_document.read_bytes())
        Draft202012Validator(json.loads(files[schema_name])).validate(document)
        validate_contract_document(args.verify_contract, document)
    if args.against is not None:
        verify_compatibility(args.against, files)
    if args.check:
        check_files(args.output_dir, files)
        check_release_index(args.output_dir)
    else:
        write_files(args.output_dir, files)
    if args.bundle is not None:
        build_bundle(args.bundle, args.output_dir)


if __name__ == "__main__":
    main()
