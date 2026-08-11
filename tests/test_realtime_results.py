from __future__ import annotations

import asyncio
import time
from io import BytesIO
from typing import Any

import pytest
from PIL import Image

from scenara.bootstrap import build_runtime
from scenara.platform.models import (
    CreateRunRequest,
    MediaKind,
    MediaSource,
    MediaTechnicalMetadata,
    MediaUnitResult,
    OcrDomainPayload,
    PipelineRef,
    PrincipalContext,
    ResultEnvelope,
    RunStatus,
)


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, format="PNG")
    return output.getvalue()


def _result(run_id: str, pipeline: PipelineRef, unit_count: int) -> ResultEnvelope:
    return ResultEnvelope(
        run_id=run_id,
        domain="ocr",
        pipeline=pipeline,
        units=[
            MediaUnitResult(
                unit_id=f"frame_{index}",
                unit_type="frame",
                index=index,
                pts_ms=index * 1000,
                width=32,
                height=24,
            )
            for index in range(unit_count)
        ],
        domain_payload=OcrDomainPayload(text="partial" if unit_count == 1 else "complete"),
        media_metadata=MediaTechnicalMetadata(sampled_units=unit_count),
        created_at=time.time(),
    )


@pytest.mark.asyncio
async def test_running_run_exposes_progress_and_partial_result(
    development_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_runtime(development_settings)
    runtime.runs.result_shard_units = 1
    context = PrincipalContext(tenant_id="default", project_id="default", principal_id="tester")
    asset = await runtime.runs.create_asset(
        context,
        data=_image_bytes(),
        filename="frame.png",
        content_type="image/png",
        kind=MediaKind.IMAGE,
    )
    pipeline = await runtime.runs.resolve_pipeline_ref("ocr.document")

    async def hold_queue(run: Any) -> None:
        del run

    monkeypatch.setattr(runtime.queue, "enqueue", hold_queue)
    outcome = await runtime.runs.create_run(
        context,
        CreateRunRequest(
            domain="ocr",
            pipeline=pipeline,
            asset_id=asset.asset_id,
        ),
        idempotency_key="realtime-result-test",
    )
    run = outcome.run
    assert run.status == RunStatus.QUEUED

    partial_published = asyncio.Event()
    finish_execution = asyncio.Event()

    async def fake_execute(
        definition: Any,
        execution_context: Any,
        initial_inputs: dict[str, Any],
        parameters: dict[str, Any],
        checkpoint: Any,
    ) -> ResultEnvelope:
        del definition, initial_inputs, parameters
        await checkpoint()
        await execution_context.publish_partial_result(_result(run.run_id, pipeline, 1))
        await execution_context.report_progress(
            0.5,
            stage="inference",
            processed_units=1,
            expected_units=2,
        )
        partial_published.set()
        await finish_execution.wait()
        return _result(run.run_id, pipeline, 2)

    monkeypatch.setattr(runtime.pipelines, "execute", fake_execute)
    execution = asyncio.create_task(runtime.runs.execute_run("default", "default", run.run_id))
    await asyncio.wait_for(partial_published.wait(), timeout=2)

    running = await runtime.state.get_run("default", "default", run.run_id)
    assert running is not None
    assert running.status == RunStatus.RUNNING
    assert running.progress == pytest.approx(0.5)
    partial = await runtime.runs.result(context, run.run_id)
    assert [unit.unit_id for unit in partial.units] == ["frame_0"]
    partial_reference = await runtime.state.get_result_reference("default", "default", run.run_id)
    assert partial_reference is not None
    assert "/partial/" in partial_reference.object_key
    events = await runtime.state.events_after("default", "default", run.run_id, 0)
    assert [event.event_type for event in events][-2:] == ["result.partial", "run.progress"]
    assert events[-1].payload == {
        "progress": 0.5,
        "stage": "inference",
        "processed_units": 1,
        "expected_units": 2,
    }

    finish_execution.set()
    await asyncio.wait_for(execution, timeout=2)
    completed = await runtime.state.get_run("default", "default", run.run_id)
    assert completed is not None
    assert completed.status == RunStatus.COMPLETED
    assert completed.progress == 1.0
    final = await runtime.runs.result(context, run.run_id)
    assert [unit.unit_id for unit in final.units] == ["frame_0", "frame_1"]
    page = await runtime.runs.result_page(context, run.run_id, unit_offset=1, unit_limit=1)
    assert [unit.unit_id for unit in page.result.units] == ["frame_1"]
    assert page.unit_total == 2
    final_reference = await runtime.state.get_result_reference("default", "default", run.run_id)
    assert final_reference is not None
    assert "/partial/" not in final_reference.object_key
    with pytest.raises(FileNotFoundError):
        await runtime.objects.get(partial_reference.object_key)


@pytest.mark.asyncio
async def test_stream_segment_completion_queues_the_next_session_run(
    development_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_runtime(development_settings)
    context = PrincipalContext(tenant_id="default", project_id="default", principal_id="tester")
    source = MediaSource(
        source_id="src_incremental",
        tenant_id="default",
        project_id="default",
        name="continuous camera",
        masked_url="rtsp://1.1.1.1/live",
        secret_ref="secret://media-sources/src_incremental",
        created_at=time.time(),
    )
    await runtime.state.create_source(source)
    await runtime.secrets.put(source.secret_ref, "rtsp://1.1.1.1/live")

    async def allow_source(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    monkeypatch.setattr("scenara.platform.services.validate_external_url", allow_source)
    enqueued: list[Any] = []

    async def hold_queue(run: Any) -> None:
        enqueued.append(run)

    monkeypatch.setattr(runtime.queue, "enqueue", hold_queue)
    pipeline = await runtime.runs.resolve_pipeline_ref("ocr.document")
    outcome = await runtime.runs.create_run(
        context,
        CreateRunRequest(domain="ocr", pipeline=pipeline, source_id=source.source_id),
        idempotency_key="stream-session-first-segment",
    )
    first = outcome.run
    assert "max_units" not in first.parameters
    assert first.parameters["stream_segment_duration_ms"] == development_settings.stream_segment_duration_ms

    async def finish_segment(
        definition: Any,
        execution_context: Any,
        initial_inputs: dict[str, Any],
        parameters: dict[str, Any],
        checkpoint: Any,
    ) -> ResultEnvelope:
        del definition, initial_inputs
        await checkpoint()
        assert parameters["stream_segment_index"] == 0
        return ResultEnvelope(
            run_id=execution_context.run_id,
            domain="ocr",
            pipeline=pipeline,
            source_id=source.source_id,
            domain_payload=OcrDomainPayload(),
            warnings=["media_termination:segment_window_completed"],
            created_at=time.time(),
        )

    monkeypatch.setattr(runtime.pipelines, "execute", finish_segment)
    await runtime.runs.execute_run("default", "default", first.run_id)

    completed = await runtime.runs.get_run(context, first.run_id)
    assert completed.status == RunStatus.COMPLETED
    assert completed.next_run_id is not None
    second = await runtime.runs.get_run(context, completed.next_run_id)
    assert second.status == RunStatus.QUEUED
    assert second.previous_run_id == first.run_id
    assert second.stream_session_id == first.stream_session_id
    assert second.stream_segment_index == 1
    assert len(enqueued) == 2

    session = await runtime.runs.stream_session(context, first.stream_session_id or "")
    assert session.current_run_id == second.run_id
    assert session.segment_count == 2
    assert session.status == "active"
    events = await runtime.state.events_after("default", "default", first.run_id, 0)
    event_types = [event.event_type for event in events]
    assert "stream.segment.started" in event_types
    assert "stream.segment.completed" in event_types
