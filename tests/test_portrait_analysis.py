from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.domains.portrait.analysis import (
    PORTRAIT_CAPABILITIES,
    PortraitBackendOutput,
)
from scenara.platform.models import ModelProvenance
from scenara.server import create_app


class CompletePortraitBackend:
    def production_capabilities(self) -> frozenset[str]:
        return PORTRAIT_CAPABILITIES

    async def analyze(self, images, filenames, capabilities):
        assert filenames == ["portrait.png"]
        assert capabilities == PORTRAIT_CAPABILITIES
        assert len(images) == 1
        return PortraitBackendOutput(
            units=[
                {
                    "persons": [
                        {
                            "box": [2, 3, 30, 22],
                            "score": 0.98,
                            "track_id": "track-1",
                            "embedding": [1.0, 0.0],
                            "quality": {"score": 0.94},
                            "pose": {"keypoints": [{"name": "nose", "point": [10, 8], "score": 0.9}]},
                            "appearance": {"upper_color": "black", "embedding": [0.1, 0.2]},
                        }
                    ],
                    "faces": [
                        {
                            "box": [8, 4, 19, 15],
                            "score": 0.97,
                            "landmarks": [[10, 8], [16, 8]],
                            "embedding": [0.5, 0.5],
                        }
                    ],
                    "silhouettes": [
                        {
                            "polygon": [[2, 3], [30, 3], [30, 22], [2, 22]],
                            "score": 0.96,
                        }
                    ],
                }
            ],
            tracks=[{"track_id": "track-1", "stability": 0.93, "gait": {"quality": 0.88}}],
            models=[
                ModelProvenance(
                    capability=capability,
                    model_id=f"approved.{capability}",
                    version="1.0.0",
                    production_ready=True,
                )
                for capability in sorted(capabilities)
            ],
            timings={"portrait_analysis_seconds": 0.01},
        )


def contains_embedding(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"embedding", "_tracking_embedding"} or contains_embedding(item) for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_embedding(item) for item in value)
    return False


def portrait_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 30), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_full_portrait_pipeline_exposes_all_capabilities_without_embeddings(development_settings) -> None:
    runtime = build_runtime(development_settings, portrait_backend=CompletePortraitBackend())
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        uploaded = await api.post(
            "/api/v1/media/assets",
            files={"file": ("portrait.png", portrait_image(), "image/png")},
            data={"kind": "image"},
        )
        assert uploaded.status_code == 201
        run = await api.post(
            "/api/v1/runs",
            json={
                "domain": "portrait",
                "pipeline": {"pipeline_id": "portrait.analysis", "version": "0.4.0"},
                "asset_id": uploaded.json()["data"]["asset_id"],
                "wait_ms": 2000,
            },
            headers={"Idempotency-Key": "portrait-full"},
        )
        assert run.status_code == 202, run.text
        assert run.json()["data"]["status"] == "completed"
        response = await api.get(f"/api/v1/runs/{run.json()['data']['run_id']}/result")
        assert response.status_code == 200
        result = response.json()["data"]["result"]
        payload = result["domain_payload"]
        assert set(payload["capabilities"]) == set(PORTRAIT_CAPABILITIES)
        assert payload["tracks"][0]["track_id"] == "track-1"
        assert {item["object_type"] for item in result["units"][0]["objects"]} == {
            "person",
            "face",
            "silhouette",
        }
        assert {relation["relation_type"] for relation in result["relations"]} == {
            "belongs_to",
            "segments",
        }
        assert not contains_embedding(result)
        assert result["provenance"]["development_substitutes"] == []
