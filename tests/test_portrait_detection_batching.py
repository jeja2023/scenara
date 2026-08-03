from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from scenara.domains.portrait.operators import PERSON_DETECTION_BATCH_SIZE, PortraitPersonDetectionOperator
from scenara.platform.media_batch import DecodedMedia, DecodedMediaUnit
from scenara.platform.models import MediaKind, MediaTechnicalMetadata
from scenara.platform.pipeline import ExecutionContext


@pytest.mark.asyncio
async def test_person_detection_inference_is_bounded_to_operator_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_sizes: list[int] = []
    progress_updates: list[tuple[float, dict[str, Any]]] = []
    partial_unit_counts: list[int] = []

    async def fake_runtime(capability: str, adapters: set[str]) -> Any:
        del capability, adapters
        return SimpleNamespace(
            bundle={},
            cache_key="models/test-person",
            model_id="models/test-person",
            version="1.0.0",
            capability={},
            config={},
        )

    async def fake_infer(
        bundle: dict[str, Any],
        key: str,
        images: list[Image.Image],
        filenames: list[str | None],
        **parameters: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        del bundle, key, filenames, parameters
        batch_sizes.append(len(images))
        return ([{"persons": []} for _ in images], {"timing": {"inference_seconds": 0.25}})

    monkeypatch.setattr("app.portrait_model_runtime_capability.get_capability_runtime", fake_runtime)
    monkeypatch.setattr("app.inference_detection.infer_person_frames", fake_infer)
    unit_count = PERSON_DETECTION_BATCH_SIZE * 2 + 1
    decoded = DecodedMedia(
        kind=MediaKind.VIDEO,
        units=[
            DecodedMediaUnit(
                unit_id=f"frame_{index}",
                unit_type="frame",
                index=index,
                pts_ms=index * 1000,
                image=Image.new("RGB", (16, 12), "black"),
            )
            for index in range(unit_count)
        ],
        metadata=MediaTechnicalMetadata(format="mp4", sampled_units=unit_count),
    )
    context = ExecutionContext(
        run_id="run_test",
        tenant_id="tenant",
        project_id="project",
        pipeline_id="portrait.person-detection",
        pipeline_version="0.1.0",
        asset_id="asset",
        source_id=None,
        filename="video.mp4",
        content_type="video/mp4",
        progress_reporter=lambda progress, payload: _record_progress(progress_updates, progress, payload),
        partial_result_publisher=lambda result: _record_partial(partial_unit_counts, len(result.units)),
    )

    output = await PortraitPersonDetectionOperator().execute(context, {"batch": decoded}, {})

    assert batch_sizes == [PERSON_DETECTION_BATCH_SIZE, PERSON_DETECTION_BATCH_SIZE, 1]
    assert output["result"].timings["inference_seconds"] == pytest.approx(0.75)
    assert len(output["result"].units) == unit_count
    assert partial_unit_counts == [PERSON_DETECTION_BATCH_SIZE, PERSON_DETECTION_BATCH_SIZE * 2, unit_count]
    assert [payload["processed_units"] for _, payload in progress_updates] == partial_unit_counts
    assert [progress for progress, _ in progress_updates] == sorted(progress for progress, _ in progress_updates)


async def _record_progress(
    updates: list[tuple[float, dict[str, Any]]],
    progress: float,
    payload: dict[str, Any],
) -> None:
    updates.append((progress, payload))


async def _record_partial(counts: list[int], unit_count: int) -> None:
    counts.append(unit_count)
