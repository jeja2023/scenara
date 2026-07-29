from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from scenara.platform.models import PipelineStatus


class PipelineError(RuntimeError):
    pass


class DomainUnavailable(PipelineError):
    pass


class OperatorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    version: str
    domain: str | None = None
    input_types: dict[str, str]
    output_types: dict[str, str]
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    resource_class: str = "cpu"
    batchable: bool = False
    failure_policy: str = "fail"


@dataclass(slots=True)
class ExecutionContext:
    run_id: str
    tenant_id: str
    project_id: str
    pipeline_id: str
    pipeline_version: str
    asset_id: str | None
    source_id: str | None
    filename: str | None
    content_type: str


class Operator(Protocol):
    definition: OperatorDefinition

    async def execute(
        self,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]: ...


class PipelineNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    operator_id: str
    inputs: dict[str, str]
    parameters: dict[str, Any] = Field(default_factory=dict)


class PipelineDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline_id: str
    version: str
    domain: str
    status: PipelineStatus
    nodes: list[PipelineNode]
    output: str
    allowed_parameters: set[str] = Field(default_factory=set)
    pausable: bool = False


class PipelineRegistry:
    def __init__(self) -> None:
        self._operators: dict[str, Operator] = {}
        self._pipelines: dict[tuple[str, str], PipelineDefinition] = {}
        self._orders: dict[tuple[str, str], list[str]] = {}

    def register_operator(self, operator: Operator) -> None:
        definition = operator.definition
        if definition.operator_id in self._operators:
            raise PipelineError(f"operator already registered: {definition.operator_id}")
        self._operators[definition.operator_id] = operator

    def register_pipeline(self, pipeline: PipelineDefinition) -> None:
        key = (pipeline.pipeline_id, pipeline.version)
        if key in self._pipelines:
            raise PipelineError(f"pipeline already registered: {pipeline.pipeline_id}@{pipeline.version}")
        self._orders[key] = self._validate(pipeline)
        self._pipelines[key] = pipeline

    def pipeline(self, pipeline_id: str, version: str, *, active_only: bool = True) -> PipelineDefinition:
        pipeline = self._pipelines.get((pipeline_id, version))
        if pipeline is None:
            raise PipelineError(f"pipeline not found: {pipeline_id}@{version}")
        if active_only and pipeline.status != PipelineStatus.ACTIVE:
            raise PipelineError(f"pipeline is not active: {pipeline_id}@{version}")
        return pipeline

    def pipelines(self) -> list[PipelineDefinition]:
        return [item.model_copy(deep=True) for item in self._pipelines.values()]

    def validate_run_parameters(self, pipeline: PipelineDefinition, parameters: dict[str, Any]) -> None:
        unexpected = sorted(set(parameters) - pipeline.allowed_parameters)
        if unexpected:
            raise PipelineError("unsupported pipeline parameters: " + ", ".join(unexpected))

    async def execute(
        self,
        pipeline: PipelineDefinition,
        context: ExecutionContext,
        initial_inputs: dict[str, Any],
        run_parameters: dict[str, Any],
        checkpoint: Any,
    ) -> Any:
        self.validate_run_parameters(pipeline, run_parameters)
        outputs: dict[str, Any] = dict(initial_inputs)
        nodes = {node.node_id: node for node in pipeline.nodes}
        for node_id in self._orders[(pipeline.pipeline_id, pipeline.version)]:
            await checkpoint()
            node = nodes[node_id]
            operator = self._operators[node.operator_id]
            inputs = {name: outputs[source] for name, source in node.inputs.items()}
            parameters = {**node.parameters, **run_parameters}
            result = await operator.execute(context, inputs, parameters)
            missing = sorted(set(operator.definition.output_types) - set(result))
            if missing:
                raise PipelineError(f"operator {node.operator_id} omitted outputs: {', '.join(missing)}")
            for name, value in result.items():
                outputs[f"{node.node_id}.{name}"] = value
        if pipeline.output not in outputs:
            raise PipelineError(f"pipeline output was not produced: {pipeline.output}")
        return outputs[pipeline.output]

    def _validate(self, pipeline: PipelineDefinition) -> list[str]:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,127}", pipeline.pipeline_id):
            raise PipelineError("invalid pipeline_id")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?", pipeline.version):
            raise PipelineError("pipeline version must be semantic")
        if not pipeline.nodes or len(pipeline.nodes) > 64:
            raise PipelineError("pipeline must contain 1-64 nodes")
        nodes = {node.node_id: node for node in pipeline.nodes}
        if len(nodes) != len(pipeline.nodes):
            raise PipelineError("pipeline node_id values must be unique")

        dependencies: dict[str, set[str]] = defaultdict(set)
        children: dict[str, set[str]] = defaultdict(set)
        available_types = {"$media.bytes": "bytes"}
        for node in pipeline.nodes:
            operator = self._operators.get(node.operator_id)
            if operator is None:
                raise PipelineError(f"unknown operator: {node.operator_id}")
            if operator.definition.domain not in {None, pipeline.domain}:
                raise PipelineError(f"operator domain mismatch: {node.operator_id}")
            for output_name, output_type in operator.definition.output_types.items():
                available_types[f"{node.node_id}.{output_name}"] = output_type
            for source in node.inputs.values():
                if source.startswith("$media."):
                    continue
                source_node = source.split(".", 1)[0]
                if source_node not in nodes:
                    raise PipelineError(f"unknown input source: {source}")
                dependencies[node.node_id].add(source_node)
                children[source_node].add(node.node_id)
        if any(len(items) > 16 for items in children.values()):
            raise PipelineError("pipeline fan-out exceeds 16")

        queue = deque(sorted(node_id for node_id in nodes if not dependencies[node_id]))
        order: list[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for child in sorted(children[current]):
                dependencies[child].discard(current)
                if not dependencies[child]:
                    queue.append(child)
        if len(order) != len(nodes):
            raise PipelineError("pipeline contains a cycle")

        for node in pipeline.nodes:
            definition = self._operators[node.operator_id].definition
            if set(node.inputs) != set(definition.input_types):
                raise PipelineError(f"operator inputs do not match contract: {node.operator_id}")
            for input_name, source in node.inputs.items():
                source_type = available_types.get(source)
                if source_type != definition.input_types[input_name]:
                    raise PipelineError(
                        f"type mismatch for {node.node_id}.{input_name}: expected "
                        f"{definition.input_types[input_name]}, received {source_type or 'unknown'}"
                    )
        if pipeline.output not in available_types:
            raise PipelineError("pipeline output reference is invalid")
        return order
