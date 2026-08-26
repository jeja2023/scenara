from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.domains.portrait.analysis import (
    PORTRAIT_CAPABILITIES,
    LegacyPortraitAnalysisBackend,
    PortraitBackendOutput,
    PortraitFullAnalysisOperator,
)
from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
from scenara.platform.models import MediaKind, MediaTechnicalMetadata, ModelProvenance
from scenara.platform.pipeline import ExecutionContext
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
            key in {"embedding", "_tracking_embedding", "_face_embedding"} or contains_embedding(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_embedding(item) for item in value)
    return False


def portrait_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 30), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_full_portrait_video_omits_units_without_objects() -> None:
    class SparsePortraitBackend:
        def production_capabilities(self) -> frozenset[str]:
            return frozenset({"person_detection"})

        async def analyze(self, images, filenames, capabilities):
            del filenames
            assert len(images) == 2
            assert capabilities == frozenset({"person_detection"})
            return PortraitBackendOutput(
                units=[
                    {},
                    {"persons": [{"box": [2, 3, 20, 24], "score": 0.92}]},
                ]
            )

    decoded = DecodedMedia(
        kind=MediaKind.VIDEO,
        units=[
            DecodedMediaUnit(
                unit_id=f"frame_{index}",
                unit_type="frame",
                index=index,
                pts_ms=index * 1000,
                image=Image.new("RGB", (40, 30), "white"),
            )
            for index in range(2)
        ],
        metadata=MediaTechnicalMetadata(format="mp4", sampled_units=2),
    )
    context = ExecutionContext(
        run_id="run_sparse_video",
        tenant_id="tenant",
        project_id="project",
        pipeline_id="portrait.analysis",
        pipeline_version="0.4.0",
        asset_id="asset",
        source_id=None,
        filename="video.mp4",
        content_type="video/mp4",
    )

    output = await PortraitFullAnalysisOperator(SparsePortraitBackend()).execute(
        context,
        {"batch": decoded},
        {"capabilities": ["person_detection"]},
    )

    result = output["result"]
    assert result.media_metadata.sampled_units == 2
    assert [unit.index for unit in result.units] == [1]
    assert [unit.pts_ms for unit in result.units] == [1000]


@pytest.mark.asyncio
async def test_legacy_portrait_backend_composes_migrated_runtime_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = LegacyPortraitAnalysisBackend()
    capabilities = frozenset(
        {
            "person_detection",
            "body_reid",
            "face_detection",
            "face_embedding",
            "pose",
            "human_parsing",
            "apparel_attributes",
            "silhouette_segmentation",
            "gait",
            "tracking",
            "quality_fusion",
        }
    )

    async def persons(*args, **kwargs):
        del args, kwargs
        return [{"box": [1, 2, 21, 28], "score": 0.9, "embedding": [0.2, 0.8]}]

    async def body(*args, **kwargs):
        del args, kwargs
        return {"embedding": [0.1, 0.9], "quality": 0.8}

    async def faces(*args, **kwargs):
        del args, kwargs
        return [{"box": [4, 3, 14, 13], "score": 0.88, "embedding": [0.3, 0.7]}]

    async def pose(*args, **kwargs):
        del args, kwargs
        return {"keypoints": [{"name": "nose", "point": [8, 6], "score": 0.9}]}

    async def appearance(*args, **kwargs):
        del args, kwargs
        return {"upper_color": "black", "embedding": [0.4, 0.6]}

    async def gait(*args, **kwargs):
        del args, kwargs
        return [0.5, 0.5], {"quality": 0.75, "embedding": [0.5, 0.5]}

    monkeypatch.setattr(backend, "_persons", persons)
    monkeypatch.setattr(backend, "production_capabilities", lambda: capabilities)
    monkeypatch.setattr("app.media.quality.assess_image_quality", lambda image: {"score": image.width / 40})
    monkeypatch.setattr(
        "app.portrait_model_capabilities.capability_status",
        lambda name: {"model_id": f"approved.{name}", "version": "1.0.0"},
    )
    monkeypatch.setattr("app.portrait_model_runtime.infer_body_record_for_image", body)
    monkeypatch.setattr("app.portrait_model_runtime.infer_face_records_for_image", faces)
    monkeypatch.setattr("app.portrait_model_runtime.infer_pose_record_for_image", pose)
    monkeypatch.setattr("app.portrait_model_runtime.infer_appearance_record_for_image", appearance)
    monkeypatch.setattr("app.portrait_model_runtime.infer_gait_embedding_for_images", gait)
    monkeypatch.setattr(
        "app.tracking_association.associate_person_tracks",
        lambda frames, include_template_embeddings: {
            "tracks": [{"track_id": "track-1", "frame_count": len(frames)}]
        },
    )

    images = [Image.new("RGB", (40, 30), "white") for _ in range(8)]
    result = await backend.analyze(images, [f"frame-{index}.png" for index in range(8)], capabilities)

    assert len(result.units) == 8
    assert result.units[0]["persons"][0]["quality"]["score"] == 0.935
    assert result.units[0]["persons"][0]["embedding"] == [0.2, 0.8]
    assert result.units[0]["persons"][0]["body_quality"] == 0.8
    assert result.units[0]["silhouettes"][0]["model_status"] == "development_bbox_silhouette_substitute"
    assert result.tracks == [
        {"track_id": "track-1", "frame_count": 8},
        {"track_id": "gait_sequence_0", "gait": {"quality": 0.75, "embedding_available": True}},
    ]
    assert result.development_substitutes == []
    assert all(model.production_ready for model in result.models)


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
        vector_index = await runtime.indexes.get_index("result.portrait.face.unknown.unknown")
        assert vector_index is not None
        vector_records = await runtime.indexes.list_records(
            "default",
            "default",
            index_id="result.portrait.face.unknown.unknown",
            source_id=run.json()["data"]["run_id"],
        )
        assert vector_records
        assert vector_records[0].vector is not None


@pytest.mark.asyncio
async def test_portrait_roi_filtering() -> None:
    class TestBackend:
        def production_capabilities(self) -> frozenset[str]:
            return frozenset({"person_detection", "face_detection"})

        async def analyze(self, images, filenames, capabilities):
            return PortraitBackendOutput(
                units=[
                    {
                        "persons": [{"box": [2, 3, 30, 22], "score": 0.98}],
                        "faces": [{"box": [8, 4, 19, 15], "score": 0.97}],
                    }
                ]
            )

    decoded = DecodedMedia(
        kind=MediaKind.IMAGE,
        units=[
            DecodedMediaUnit(
                unit_id="frame_0",
                unit_type="frame",
                index=0,
                pts_ms=0,
                image=Image.new("RGB", (100, 100), "white"),
            )
        ],
        metadata=MediaTechnicalMetadata(format="png", sampled_units=1),
    )
    context = ExecutionContext(
        run_id="run_roi_portrait",
        tenant_id="tenant",
        project_id="project",
        pipeline_id="portrait.analysis",
        pipeline_version="0.4.0",
        asset_id="asset",
        source_id=None,
        filename="portrait.png",
        content_type="image/png",
    )

    operator = PortraitFullAnalysisOperator(TestBackend())

    # 1. 圈选覆盖目标的 ROI：目标保留
    out_inside = await operator.execute(
        context,
        {"batch": decoded},
        {
            "capabilities": ["person_detection", "face_detection"],
            "roi": [0.0, 0.0, 0.4, 0.4],
        },
    )
    assert len(out_inside["result"].units[0].objects) == 2

    # 2. 圈选右下角的 ROI：目标被过滤，对象数为 0
    out_outside = await operator.execute(
        context,
        {"batch": decoded},
        {
            "capabilities": ["person_detection", "face_detection"],
            "roi": [0.5, 0.5, 1.0, 1.0],
        },
    )
    assert len(out_outside["result"].units[0].objects) == 0
