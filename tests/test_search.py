from io import BytesIO

import httpx
import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.domains.portrait.encoder import decode_portrait_image
from scenara.platform.index import IndexDefinition, IndexRecord, IndexRecordKind, IndexSourceRef
from scenara.server import create_app


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (128, 128), (180, 120, 80)).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
async def search_client(development_settings):
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api, runtime


@pytest.mark.asyncio
async def test_text_search_returns_media_context_and_audit(search_client) -> None:
    api, runtime = search_client
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("invoice.png", _image_bytes(), "image/png")},
        data={"kind": "image"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["data"]["asset_id"]
    await runtime.indexes.create_index(
        IndexDefinition(index_id="result.ocr", domain="ocr", record_kind=IndexRecordKind.MULTIMODAL)
    )
    await runtime.indexes.upsert(
        IndexRecord(
            record_id="text-hit",
            tenant_id="default",
            project_id="default",
            index_id="result.ocr",
            domain="ocr",
            kind=IndexRecordKind.MULTIMODAL,
            source=IndexSourceRef(source_type="run_result", source_id="run-text", asset_id=asset_id, run_id="run-text"),
            text="合同编号 INV-2026-001",
            metadata={"source_id": None},
        )
    )

    response = await api.post("/api/v1/search/text", json={"query": "INV-2026", "media_kinds": ["image"]})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["hits"][0]["media_kind"] == "image"
    assert payload["hits"][0]["source"]["asset_id"] == asset_id
    assert '"vector"' not in response.text
    events = await runtime.state.audit_events("default", "default")
    assert any(event.action == "search.text" for event in events)


@pytest.mark.asyncio
async def test_search_ranking_profile_weights_are_applied(search_client) -> None:
    api, runtime = search_client
    await runtime.indexes.create_index(
        IndexDefinition(index_id="result.ocr", domain="ocr", record_kind=IndexRecordKind.MULTIMODAL)
    )
    await runtime.indexes.upsert(
        IndexRecord(
            record_id="weighted-hit",
            tenant_id="default",
            project_id="default",
            index_id="result.ocr",
            domain="ocr",
            kind=IndexRecordKind.MULTIMODAL,
            source=IndexSourceRef(source_type="run_result", source_id="run-weighted"),
            text="weighted search",
        )
    )
    profile = await api.post(
        "/api/v1/search/ranking-profiles",
        json={"name": "weighted", "exact_weight": 0.25, "vector_weight": 0.75},
    )
    assert profile.status_code == 201, profile.text
    result = await api.post(
        "/api/v1/search/text",
        json={"query": "weighted", "profile_id": profile.json()["data"]["record_id"]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["data"]["hits"][0]["score"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_portrait_search_queries_result_vector_index(search_client) -> None:
    api, runtime = search_client
    image = _image_bytes()
    uploaded = await api.post(
        "/api/v1/media/assets",
        files={"file": ("face.png", image, "image/png")},
        data={"kind": "image"},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["data"]["asset_id"]
    encoded = await runtime.portrait.encoder.encode(decode_portrait_image(image))
    index_id = f"result.{encoded.feature_space_id}"
    await runtime.indexes.create_index(
        IndexDefinition(
            index_id=index_id,
            domain="portrait",
            record_kind=IndexRecordKind.VECTOR,
            vector_dimension=len(encoded.embedding),
            vector_model_id=encoded.model_id,
            vector_model_version=encoded.model_version,
            distance_metric="cosine",
            threshold=0.8,
        )
    )
    await runtime.indexes.upsert(
        IndexRecord(
            record_id="portrait-hit",
            tenant_id="default",
            project_id="default",
            index_id=index_id,
            domain="portrait",
            kind=IndexRecordKind.VECTOR,
            source=IndexSourceRef(source_type="run_result", source_id="run-face", asset_id=asset_id, run_id="run-face"),
            vector=encoded.embedding,
            metadata={"object_type": "face"},
        )
    )

    response = await api.post(
        "/api/v1/search/image",
        files={"file": ("query.png", image, "image/png")},
        data={"media_kinds": "image"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["mode"] == "portrait"
    assert payload["total"] == 1
    assert payload["hits"][0]["source"]["run_id"] == "run-face"
    assert '"vector"' not in response.text

    asset_response = await api.post(
        "/api/v1/search/asset",
        json={"asset_id": asset_id, "media_kinds": ["image"]},
    )
    assert asset_response.status_code == 200, asset_response.text
    asset_payload = asset_response.json()["data"]
    assert asset_payload["mode"] == "portrait"
    assert asset_payload["total"] == 1
    assert asset_payload["query_summary"]["face_count"] == 1


@pytest.mark.asyncio
async def test_portrait_result_search_rejects_model_contract_mismatch(search_client) -> None:
    api, runtime = search_client
    image = _image_bytes()
    encoded = await runtime.portrait.encoder.encode(decode_portrait_image(image))
    index_id = "result.portrait.face.other-model.v1"
    await runtime.indexes.create_index(
        IndexDefinition(
            index_id=index_id,
            domain="portrait",
            record_kind=IndexRecordKind.VECTOR,
            vector_dimension=len(encoded.embedding),
            vector_model_id="other-model",
            vector_model_version="1.0.0",
            distance_metric="cosine",
            threshold=0.8,
        )
    )

    response = await api.post(
        "/api/v1/search/image",
        files={"file": ("query.png", image, "image/png")},
        data={"feature_space_id": "portrait.face.other-model.v1"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "INDEX_CONTRACT_ERROR"


@pytest.mark.asyncio
async def test_portrait_result_search_matches_video_frame(search_client) -> None:
    api, runtime = search_client
    image = _image_bytes()
    encoded = await runtime.portrait.encoder.encode(decode_portrait_image(image))
    safe_model = encoded.model_id.replace("/", ".")
    index_id = f"result.portrait.face.{safe_model}.{encoded.model_version}"
    await runtime.indexes.create_index(
        IndexDefinition(
            index_id=index_id,
            domain="portrait",
            record_kind=IndexRecordKind.VECTOR,
            vector_dimension=len(encoded.embedding),
            vector_model_id=encoded.model_id,
            vector_model_version=encoded.model_version,
            distance_metric="cosine",
            threshold=0.8,
        )
    )
    await runtime.indexes.upsert(
        IndexRecord(
            record_id="idxv_run_video_001_face_01",
            tenant_id="default",
            project_id="default",
            index_id=index_id,
            domain="portrait",
            kind=IndexRecordKind.VECTOR,
            source=IndexSourceRef(
                source_type="run_result",
                source_id="run_video_001",
                asset_id="asset_video_001",
                run_id="run_video_001",
                unit_id="unit_12",
                object_id="face_01",
                artifact_id="art_crop_face_01",
                pts_ms=12400,
            ),
            vector=encoded.embedding,
            metadata={"object_type": "face", "source_id": "src_cam_01"},
        )
    )

    response = await api.post(
        "/api/v1/search/image",
        files={"file": ("query.png", image, "image/png")},
        data={"media_kinds": "video"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["hits"][0]["source"]["run_id"] == "run_video_001"
    assert payload["hits"][0]["source"]["pts_ms"] == 12400
    assert payload["hits"][0]["source"]["artifact_id"] == "art_crop_face_01"

