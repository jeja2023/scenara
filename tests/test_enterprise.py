from __future__ import annotations

import base64
import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scenara.bootstrap import build_runtime
from scenara.enterprise.license import (
    EnterpriseLicenseError,
    LicenseClaims,
    canonical_claims,
)
from scenara.server import create_app


def signed_license(tmp_path: Path, *, media_limit: int = 100) -> tuple[Path, Path]:
    now = int(time.time())
    claims = LicenseClaims(
        license_id="lic-test-1",
        customer="Scenara Test",
        tenant_ids=("default",),
        entitlements=frozenset(
            {
                "media_asset:create",
                "enterprise_sla:read",
                "enterprise_incident:*",
                "enterprise_support:*",
                "enterprise_compliance:*",
            }
        ),
        limits={"media_bytes": media_limit, "runs": 10},
        support_tier="premium",
        sla_targets={"availability": 0.999, "success_rate": 0.99},
        issued_at=now - 10,
        not_before=now - 5,
        expires_at=now + 3600,
    )
    private_key = Ed25519PrivateKey.generate()
    signature = private_key.sign(canonical_claims(claims))
    document = {
        "claims": claims.model_dump(mode="json"),
        "signature": base64.b64encode(signature).decode(),
    }
    license_path = tmp_path / "enterprise-license.json"
    license_path.write_text(json.dumps(document), encoding="utf-8")
    public_key_path = tmp_path / "enterprise-license.pub"
    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return license_path, public_key_path


@pytest.fixture
async def enterprise_client(development_settings, tmp_path: Path):
    license_path, public_key_path = signed_license(tmp_path)
    settings = replace(
        development_settings,
        enterprise_policy_required=True,
        enterprise_license_path=license_path,
        enterprise_public_key_path=public_key_path,
    )
    runtime = build_runtime(settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


@pytest.mark.asyncio
async def test_signed_enterprise_policy_quota_and_resources(enterprise_client) -> None:
    api, runtime = enterprise_client
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    status = await api.get("/api/v1/enterprise/status")
    assert status.status_code == 200
    assert status.json()["data"]["license_id"] == "lic-test-1"
    assert status.json()["data"]["support_tier"] == "premium"

    first = await api.post(
        "/api/v1/media/assets",
        files={"file": ("a.png", one_pixel_png, "image/png")},
        data={"kind": "image"},
    )
    assert first.status_code == 201, first.text
    exceeded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("b.png", one_pixel_png, "image/png")},
        data={"kind": "image"},
    )
    assert exceeded.status_code == 403
    assert exceeded.json()["error"]["code"] == "POLICY_DENIED"
    assets = await runtime.state.list_assets("default", "default")
    assert len(assets) == 1

    sla = await api.post(
        "/api/v1/enterprise/sla/evaluate",
        json={"availability": 0.998, "success_rate": 0.995},
    )
    assert sla.status_code == 200
    assert sla.json()["data"]["breaches"] == ["availability"]

    incident = await api.post(
        "/api/v1/enterprise/incidents",
        json={"title": "GPU worker unavailable", "severity": "sev2", "summary": "triage"},
        headers={"X-Principal-Id": "oncall"},
    )
    assert incident.status_code == 201, incident.text
    incident_id = incident.json()["data"]["incident_id"]
    resolved = await api.post(
        f"/api/v1/enterprise/incidents/{incident_id}/resolve",
        json={"summary": "worker recovered"},
        headers={"X-Principal-Id": "oncall"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "resolved"

    support = await api.post(
        "/api/v1/enterprise/support/cases",
        json={"subject": "Capacity review", "priority": "high", "description": "Review GPU capacity."},
        headers={"X-Principal-Id": "customer-admin"},
    )
    assert support.status_code == 201

    evidence = await api.post(
        "/api/v1/enterprise/compliance/evidence",
        json={
            "evidence_type": "access-review",
            "object_ref": "s3://evidence/access-review.pdf",
            "sha256": "a" * 64,
            "signed_by": "security@example.com",
        },
    )
    assert evidence.status_code == 201
    assert (await api.get("/api/v1/enterprise/compliance/evidence")).json()["data"][0][
        "evidence_id"
    ] == evidence.json()["data"]["evidence_id"]


def test_tampered_enterprise_license_is_rejected(development_settings, tmp_path: Path) -> None:
    license_path, public_key_path = signed_license(tmp_path)
    document = json.loads(license_path.read_text(encoding="utf-8"))
    document["claims"]["customer"] = "Tampered"
    license_path.write_text(json.dumps(document), encoding="utf-8")
    settings = replace(
        development_settings,
        enterprise_policy_required=True,
        enterprise_license_path=license_path,
        enterprise_public_key_path=public_key_path,
    )
    with pytest.raises(EnterpriseLicenseError, match="signature"):
        build_runtime(settings)
