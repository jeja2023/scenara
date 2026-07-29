from __future__ import annotations

from typing import Any

import pytest

from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import (
    ExecutionContext,
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
