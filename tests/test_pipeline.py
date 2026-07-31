from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import (
    ExecutionContext,
    ExecutionInterrupted,
    OperatorDefinition,
    PipelineDefinition,
    PipelineError,
    PipelineNode,
    PipelineRegistry,
)


class PassOperator:
    definition = OperatorDefinition(
        operator_id="test.pass",
        version="1.0.0",
        input_types={"value": "bytes"},
        output_types={"value": "bytes"},
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        del context, parameters
        return {"value": inputs["value"]}


def test_pipeline_rejects_cycles() -> None:
    registry = PipelineRegistry()
    registry.register_operator(PassOperator())
    pipeline = PipelineDefinition(
        pipeline_id="test.cycle",
        version="1.0.0",
        domain="test",
        status=PipelineStatus.ACTIVE,
        nodes=[
            PipelineNode(node_id="left", operator_id="test.pass", inputs={"value": "right.value"}),
            PipelineNode(node_id="right", operator_id="test.pass", inputs={"value": "left.value"}),
        ],
        output="right.value",
    )
    with pytest.raises(PipelineError, match="cycle"):
        registry.register_pipeline(pipeline)


def test_pipeline_rejects_unlisted_parameters() -> None:
    registry = PipelineRegistry()
    registry.register_operator(PassOperator())
    pipeline = PipelineDefinition(
        pipeline_id="test.valid",
        version="1.0.0",
        domain="test",
        status=PipelineStatus.ACTIVE,
        nodes=[PipelineNode(node_id="pass", operator_id="test.pass", inputs={"value": "$media.bytes"})],
        output="pass.value",
    )
    registry.register_pipeline(pipeline)
    with pytest.raises(PipelineError, match="unsupported"):
        registry.validate_run_parameters(pipeline, {"arbitrary": True})


class ControlledOperator:
    definition = OperatorDefinition(
        operator_id="test.controlled",
        version="1.0.0",
        input_types={"value": "bytes"},
        output_types={"value": "bytes"},
        timeout_seconds=5,
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        del parameters

        def work() -> bytes:
            while context.control.wait_until_runnable(0.01):
                pass
            raise PipelineError("operator observed cancellation")

        return {"value": await asyncio.to_thread(work) or inputs["value"]}


class StopRequested(ExecutionInterrupted):
    pass


class PauseAwareOperator:
    definition = OperatorDefinition(
        operator_id="test.pause-aware",
        version="1.0.0",
        input_types={"value": "bytes"},
        output_types={"value": "bytes"},
        timeout_seconds=0.25,
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        del parameters
        for _ in range(5):
            assert await asyncio.to_thread(context.control.wait_until_runnable, 0.03)
        return {"value": inputs["value"]}


class TimeoutOperator:
    definition = OperatorDefinition(
        operator_id="test.timeout",
        version="1.0.0",
        input_types={"value": "bytes"},
        output_types={"value": "bytes"},
        timeout_seconds=0.05,
    )

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        del context, parameters
        await asyncio.sleep(1)
        return {"value": inputs["value"]}


@pytest.mark.asyncio
async def test_pipeline_checkpoints_while_an_operator_is_running() -> None:
    registry = PipelineRegistry()
    registry.register_operator(ControlledOperator())
    pipeline = PipelineDefinition(
        pipeline_id="test.controlled",
        version="1.0.0",
        domain="test",
        status=PipelineStatus.ACTIVE,
        nodes=[
            PipelineNode(node_id="controlled", operator_id="test.controlled", inputs={"value": "$media.bytes"})
        ],
        output="controlled.value",
    )
    registry.register_pipeline(pipeline)
    context = ExecutionContext(
        run_id="run-controlled",
        tenant_id="tenant",
        project_id="project",
        pipeline_id=pipeline.pipeline_id,
        pipeline_version=pipeline.version,
        asset_id="asset",
        source_id=None,
        filename="sample.bin",
        content_type="application/octet-stream",
    )
    checkpoints = 0

    async def checkpoint() -> None:
        nonlocal checkpoints
        checkpoints += 1
        if checkpoints >= 2:
            raise StopRequested("stop requested")

    with pytest.raises(StopRequested, match="stop requested"):
        await registry.execute(pipeline, context, {"$media.bytes": b"value"}, {}, checkpoint)
    assert context.control.cancelled is True
    assert checkpoints == 2


@pytest.mark.asyncio
async def test_operator_timeout_excludes_time_spent_paused() -> None:
    registry = PipelineRegistry()
    registry.register_operator(PauseAwareOperator())
    pipeline = PipelineDefinition(
        pipeline_id="test.pause-aware",
        version="1.0.0",
        domain="test",
        status=PipelineStatus.ACTIVE,
        nodes=[
            PipelineNode(node_id="pause-aware", operator_id="test.pause-aware", inputs={"value": "$media.bytes"})
        ],
        output="pause-aware.value",
        pausable=True,
    )
    registry.register_pipeline(pipeline)
    context = ExecutionContext(
        run_id="run-pause-aware",
        tenant_id="tenant",
        project_id="project",
        pipeline_id=pipeline.pipeline_id,
        pipeline_version=pipeline.version,
        asset_id="asset",
        source_id=None,
        filename="sample.bin",
        content_type="application/octet-stream",
    )
    checkpoints = 0
    resume_task: asyncio.Task[None] | None = None

    async def resume_after_pause() -> None:
        await asyncio.sleep(0.3)
        context.control.resume()

    async def checkpoint() -> None:
        nonlocal checkpoints, resume_task
        checkpoints += 1
        if checkpoints == 2:
            context.control.pause()
            resume_task = asyncio.create_task(resume_after_pause())

    result = await registry.execute(pipeline, context, {"$media.bytes": b"value"}, {}, checkpoint)
    if resume_task is not None:
        await resume_task
    assert result == b"value"
    assert checkpoints >= 2


@pytest.mark.asyncio
async def test_operator_timeout_still_cancels_over_budget_work() -> None:
    registry = PipelineRegistry()
    registry.register_operator(TimeoutOperator())
    pipeline = PipelineDefinition(
        pipeline_id="test.timeout",
        version="1.0.0",
        domain="test",
        status=PipelineStatus.ACTIVE,
        nodes=[PipelineNode(node_id="timeout", operator_id="test.timeout", inputs={"value": "$media.bytes"})],
        output="timeout.value",
    )
    registry.register_pipeline(pipeline)
    context = ExecutionContext(
        run_id="run-timeout",
        tenant_id="tenant",
        project_id="project",
        pipeline_id=pipeline.pipeline_id,
        pipeline_version=pipeline.version,
        asset_id="asset",
        source_id=None,
        filename="sample.bin",
        content_type="application/octet-stream",
    )

    async def checkpoint() -> None:
        return None

    with pytest.raises(PipelineError, match="operator timed out"):
        await registry.execute(pipeline, context, {"$media.bytes": b"value"}, {}, checkpoint)
    assert context.control.cancelled is True
