from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.platform.model_runtime import ModelPackageManifest
from scenara.platform.models import (
    ModelProvenance,
    PipelineRef,
    PortraitDomainPayload,
    ResultEnvelope,
    ResultReference,
    RunRecord,
    RunStatus,
)
from scenara.server import create_app


@pytest.fixture
async def feedback_client(development_settings):
    runtime = build_runtime(development_settings)
    await runtime.state.register_model_package(
        ModelPackageManifest(
            model_id="scenara.portrait.release",
            version="1.0.0",
            capability="portrait-analysis",
            adapter="release-test",
            sha256="a" * 64,
            source_uri="internal://models/portrait/1.0.0",
            license_id="Proprietary",
            model_card="models/portrait-1.0.0.yml",
            vram_mb=1024,
            regression_samples=("portrait-regression-v1",),
            production_ready=True,
        )
    )
    now = time.time()
    run = RunRecord(
        run_id="run_feedback1",
        tenant_id="default",
        project_id="default",
        principal_id="anonymous",
        domain="portrait",
        pipeline=PipelineRef(pipeline_id="portrait.analysis", version="0.4.0"),
        asset_id="asset_feedback1",
        status=RunStatus.COMPLETED,
        progress=1.0,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    await runtime.state.create_run_idempotent(run, idempotency_key="feedback-trace", request_hash="trace")
    result = ResultEnvelope(
        run_id=run.run_id,
        domain="portrait",
        pipeline=run.pipeline,
        asset_id=run.asset_id,
        domain_payload=PortraitDomainPayload(),
        models=[
            ModelProvenance(
                capability="portrait-analysis",
                model_id="scenara.portrait.release",
                version="1.0.0",
                sha256="a" * 64,
                production_ready=True,
            )
        ],
        created_at=now,
    )
    result_document = result.model_dump_json().encode("utf-8")
    result_key = "tenants/default/projects/default/results/run_feedback1/result.json"
    await runtime.objects.put(result_key, result_document, "application/json")
    await runtime.state.save_result_reference(
        "default",
        "default",
        ResultReference(
            run_id=run.run_id,
            object_key=result_key,
            sha256=hashlib.sha256(result_document).hexdigest(),
            unit_count=0,
            domain="portrait",
            created_at=now,
        ),
    )
    await runtime.state.register_model_package(
        ModelPackageManifest(
            model_id="scenara.portrait.release",
            version="1.1.0",
            capability="portrait-analysis",
            adapter="release-test",
            sha256="b" * 64,
            source_uri="internal://models/portrait/1.1.0",
            license_id="Proprietary",
            model_card="models/portrait-1.1.0.yml",
            vram_mb=1024,
            regression_samples=("portrait-regression-v2",),
            production_ready=True,
        )
    )
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


def feedback_body(*, authorized: bool = True) -> dict[str, object]:
    return {
        "kind": "false_negative",
        "run_id": "run_feedback1",
        "model_id": "scenara.portrait.release",
        "model_version": "1.0.0",
        "correction": {"label": "person", "bbox": [1, 2, 30, 40]},
        "authorized_for_training": authorized,
        "deidentified": authorized,
    }


@pytest.mark.asyncio
async def test_feedback_review_and_hard_sample_manifest_are_fail_closed(feedback_client) -> None:
    api, _ = feedback_client
    wrong_model = feedback_body()
    wrong_model["model_version"] = "9.9.9"
    rejected_trace = await api.post("/api/v1/feedback", json=wrong_model)
    assert rejected_trace.status_code == 409

    sensitive_body = feedback_body()
    sensitive_body["correction"] = {"embedding": [0.1, 0.2]}
    sensitive = await api.post("/api/v1/feedback", json=sensitive_body)
    assert sensitive.status_code == 201
    sensitive_review = await api.post(
        f"/api/v1/feedback/{sensitive.json()['data']['feedback_id']}/review",
        json={"status": "approved", "notes": "must be rejected"},
    )
    assert sensitive_review.status_code == 409

    unsafe = await api.post("/api/v1/feedback", json=feedback_body(authorized=False))
    assert unsafe.status_code == 201
    unsafe_id = unsafe.json()["data"]["feedback_id"]
    rejected = await api.post(
        f"/api/v1/feedback/{unsafe_id}/review",
        json={"status": "approved", "notes": "missing rights"},
    )
    assert rejected.status_code == 409

    created = await api.post("/api/v1/feedback", json=feedback_body())
    assert created.status_code == 201, created.text
    created_data = created.json()["data"]
    feedback_id = created_data["feedback_id"]
    assert created_data["result_ref"] == "tenants/default/projects/default/results/run_feedback1/result.json"
    assert created_data["media_ref"] == "asset_feedback1"
    assert created_data["pipeline_id"] == "portrait.analysis"
    reviewed = await api.post(
        f"/api/v1/feedback/{feedback_id}/review",
        json={"status": "approved", "notes": "rights and deidentification checked"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["reviewed_by"] == "anonymous"

    manifest = await api.post(
        "/api/v1/hard-sample-manifests",
        json={"dataset_id": "portrait.hard-samples", "version": "1.0.0", "feedback_ids": [feedback_id]},
    )
    assert manifest.status_code == 201, manifest.text
    payload = manifest.json()["data"]
    assert len(payload["sha256"]) == 64
    assert payload["items"][0]["authorized_for_training"] is True
    assert payload["items"][0]["deidentified"] is True
    assert payload["label_schema"] == "scenara.feedback.correction.v1"
    assert payload["split"] == "train"
    assert "embedding" not in payload["items"][0]

    other_tenant = await api.get("/api/v1/feedback", headers={"X-Tenant-Id": "other"})
    assert other_tenant.status_code == 200
    assert other_tenant.json()["data"] == []


async def qualification_refs(
    runtime,
    version: str,
    package_sha256: str,
    *,
    signed_by: str = "算法评估负责人",
) -> list[str]:
    executed_at = datetime.now(timezone.utc)
    details = {
        "model_rights": {"rights_cleared": True},
        "portrait_evaluation": {
            "thresholds_approved_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
        },
        "regression": {"regressions_passed": True},
    }
    references: list[str] = []
    for evidence_type, evidence_details in details.items():
        document = json.dumps(
            {
                "schema_version": "1.0",
                "evidence_type": evidence_type,
                "status": "passed",
                "model_id": "scenara.portrait.release",
                "model_version": version,
                "package_sha256": package_sha256,
                "executed_at": executed_at.isoformat(),
                "approved_at": (executed_at + timedelta(minutes=5)).isoformat(),
                "signed_by": signed_by,
                "details": evidence_details,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        object_key = f"tenants/default/projects/default/model-evidence/{evidence_type}-{version}.json"
        await runtime.objects.put(object_key, document, "application/json")
        references.append(f"{object_key}#sha256={hashlib.sha256(document).hexdigest()}")
    return references


async def create_release(api: httpx.AsyncClient, runtime, version: str, digest: str) -> None:
    evidence_refs = await qualification_refs(runtime, version, digest)
    created = await api.post(
        "/api/v1/model-releases",
        json={
            "model_id": "scenara.portrait.release",
            "version": version,
            "package_sha256": digest,
            "evidence_refs": evidence_refs,
        },
    )
    assert created.status_code == 201, created.text
    for target in ("validated", "approved", "active"):
        transitioned = await api.post(
            f"/api/v1/model-releases/scenara.portrait.release/versions/{version}/transition",
            json={"status": target, "reason": f"qualification to {target}"},
        )
        assert transitioned.status_code == 200, transitioned.text


@pytest.mark.asyncio
async def test_model_release_lifecycle_activation_and_rollback(feedback_client) -> None:
    api, runtime = feedback_client
    await create_release(api, runtime, "1.0.0", "a" * 64)
    await create_release(api, runtime, "1.1.0", "b" * 64)

    releases = (await api.get("/api/v1/model-releases")).json()["data"]
    statuses = {item["version"]: item["status"] for item in releases}
    assert statuses == {"1.0.0": "retired", "1.1.0": "active"}

    rolled_back = await api.post(
        "/api/v1/model-releases/scenara.portrait.release/rollback",
        json={"target_version": "1.0.0", "reason": "regression detected"},
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["data"]["status"] == "active"

    releases = (await api.get("/api/v1/model-releases")).json()["data"]
    statuses = {item["version"]: item["status"] for item in releases}
    assert statuses == {"1.0.0": "active", "1.1.0": "retired"}
    events = (await api.get("/api/v1/model-deployment-events")).json()["data"]
    assert events[0]["action"] in {"rollback", "rollback-retire"}
    assert any(event["action"] == "rollback" for event in events)


@pytest.mark.asyncio
async def test_model_release_cannot_be_validated_without_evidence(feedback_client) -> None:
    api, _ = feedback_client
    created = await api.post(
        "/api/v1/model-releases",
        json={
            "model_id": "scenara.portrait.release",
            "version": "1.0.0",
            "package_sha256": "a" * 64,
            "evidence_refs": [],
        },
    )
    assert created.status_code == 201
    rejected = await api.post(
        "/api/v1/model-releases/scenara.portrait.release/versions/1.0.0/transition",
        json={"status": "validated", "reason": "missing evidence"},
    )
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_model_release_rejects_untrusted_or_placeholder_evidence(feedback_client) -> None:
    api, runtime = feedback_client
    malformed = await api.post(
        "/api/v1/model-releases",
        json={
            "model_id": "scenara.portrait.release",
            "version": "1.0.0",
            "package_sha256": "a" * 64,
            "evidence_refs": ["s3://evidence/fake.json"],
        },
    )
    assert malformed.status_code == 422

    evidence_refs = await qualification_refs(runtime, "1.0.0", "a" * 64, signed_by="TBD")
    created = await api.post(
        "/api/v1/model-releases",
        json={
            "model_id": "scenara.portrait.release",
            "version": "1.0.0",
            "package_sha256": "a" * 64,
            "evidence_refs": evidence_refs,
        },
    )
    assert created.status_code == 201
    rejected = await api.post(
        "/api/v1/model-releases/scenara.portrait.release/versions/1.0.0/transition",
        json={"status": "validated", "reason": "placeholder signer"},
    )
    assert rejected.status_code == 409
