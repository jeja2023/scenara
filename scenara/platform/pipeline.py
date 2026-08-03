from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from scenara.platform.artifacts import ArtifactSink
from scenara.platform.model_runtime import RuntimeModelBinding
from scenara.platform.models import PipelineStatus


class PipelineError(RuntimeError):
    pass


class DomainUnavailable(PipelineError):
    pass


class ExecutionInterrupted(PipelineError):
    """Control-plane interruption that must not be wrapped as an operator failure."""


@dataclass(slots=True)
class ExecutionControl:
    """Thread-safe pause and cancellation signal for long-running operators."""

    _condition: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _paused: bool = field(default=False, init=False, repr=False)
    _cancelled: bool = field(default=False, init=False, repr=False)
    _pause_started_at: float | None = field(default=None, init=False, repr=False)
    _paused_seconds: float = field(default=0.0, init=False, repr=False)

    def pause(self) -> None:
        with self._condition:
            if not self._paused:
                self._pause_started_at = time.monotonic()
            self._paused = True

    def resume(self) -> None:
        with self._condition:
            self._finish_pause()
            self._paused = False
            self._condition.notify_all()

    def cancel(self) -> None:
        with self._condition:
            self._finish_pause()
            self._cancelled = True
            self._paused = False
            self._condition.notify_all()

    def wait_until_runnable(self, delay_seconds: float = 0.0) -> bool:
        """Block while paused and return False once cancellation is requested."""

        with self._condition:
            if delay_seconds > 0 and not self._paused and not self._cancelled:
                self._condition.wait(timeout=delay_seconds)
            while self._paused and not self._cancelled:
                self._condition.wait(timeout=0.1)
            return not self._cancelled

    @property
    def cancelled(self) -> bool:
        with self._condition:
            return self._cancelled

    @property
    def paused_seconds(self) -> float:
        with self._condition:
            active = time.monotonic() - self._pause_started_at if self._pause_started_at is not None else 0.0
            return self._paused_seconds + active

    def _finish_pause(self) -> None:
        if self._pause_started_at is not None:
            self._paused_seconds += time.monotonic() - self._pause_started_at
            self._pause_started_at = None


class OperatorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    version: str
    domain: str | None = None
    input_types: dict[str, str]
    output_types: dict[str, str]
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    resource_class: Literal["cpu", "gpu", "io"] = "cpu"
    resource_budget: dict[str, float] = Field(default_factory=dict)
    batchable: bool = False
    max_batch_size: int = Field(default=1, ge=1, le=4096)
    failure_policy: Literal["fail", "retry"] = "fail"
    max_attempts: int = Field(default=1, ge=1, le=5)


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
    production: bool = False
    model_bindings: dict[str, RuntimeModelBinding] = field(default_factory=dict)
    artifacts: ArtifactSink | None = None
    control: ExecutionControl = field(default_factory=ExecutionControl)
    progress_reporter: Callable[[float, dict[str, Any]], Awaitable[None]] | None = None
    partial_result_publisher: Callable[[Any], Awaitable[None]] | None = None

    async def report_progress(self, progress: float, **payload: Any) -> None:
        if self.progress_reporter is not None:
            await self.progress_reporter(max(0.0, min(0.99, progress)), payload)

    async def publish_partial_result(self, result: Any) -> None:
        if self.partial_result_publisher is not None:
            await self.partial_result_publisher(result)


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


class PipelineParameterDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    control: Literal["boolean", "integer", "number", "select", "text"]
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: list[str] = Field(default_factory=list)
    placeholder: str | None = None
    advanced: bool = False
    media_kinds: set[str] = Field(default_factory=set)


class PipelineDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline_id: str
    version: str
    domain: str
    status: PipelineStatus
    nodes: list[PipelineNode]
    output: str
    allowed_parameters: set[str] = Field(default_factory=set)
    parameter_schema: dict[str, PipelineParameterDefinition] = Field(default_factory=dict)
    pausable: bool = False

    @property
    def definition_sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude={"status"})
        payload["allowed_parameters"] = sorted(self.allowed_parameters)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class PipelineRegistry:
    def __init__(self) -> None:
        self._operators: dict[str, Operator] = {}
        self._pipelines: dict[tuple[str, str], PipelineDefinition] = {}
        self._orders: dict[tuple[str, str], list[str]] = {}
        self._digests: dict[tuple[str, str], str] = {}

    def register_operator(self, operator: Operator) -> None:
        definition = operator.definition
        if definition.operator_id in self._operators:
            raise PipelineError(f"operator already registered: {definition.operator_id}")
        self._operators[definition.operator_id] = operator

    def register_pipeline(self, pipeline: PipelineDefinition) -> None:
        key = (pipeline.pipeline_id, pipeline.version)
        if key in self._pipelines:
            raise PipelineError(f"pipeline already registered: {pipeline.pipeline_id}@{pipeline.version}")
        if pipeline.status == PipelineStatus.ACTIVE and any(
            item.pipeline_id == pipeline.pipeline_id and item.status == PipelineStatus.ACTIVE
            for item in self._pipelines.values()
        ):
            raise PipelineError(f"pipeline already has an active version: {pipeline.pipeline_id}")
        self._orders[key] = self._validate(pipeline)
        self._pipelines[key] = pipeline.model_copy(deep=True)
        self._digests[key] = pipeline.definition_sha256

    def pipeline(self, pipeline_id: str, version: str, *, active_only: bool = True) -> PipelineDefinition:
        pipeline = self._pipelines.get((pipeline_id, version))
        if pipeline is None:
            raise PipelineError(f"pipeline not found: {pipeline_id}@{version}")
        if active_only and pipeline.status != PipelineStatus.ACTIVE:
            raise PipelineError(f"pipeline is not active: {pipeline_id}@{version}")
        return pipeline.model_copy(deep=True)

    def pipelines(self) -> list[PipelineDefinition]:
        return [item.model_copy(deep=True) for item in self._pipelines.values()]

    def transition(self, pipeline_id: str, version: str, target: PipelineStatus) -> PipelineDefinition:
        key = (pipeline_id, version)
        pipeline = self._pipelines.get(key)
        if pipeline is None:
            raise PipelineError(f"pipeline not found: {pipeline_id}@{version}")
        allowed = {
            PipelineStatus.DRAFT: {PipelineStatus.VALIDATED},
            PipelineStatus.VALIDATED: {PipelineStatus.APPROVED, PipelineStatus.DRAFT},
            PipelineStatus.APPROVED: {PipelineStatus.ACTIVE, PipelineStatus.DRAFT},
            PipelineStatus.ACTIVE: {PipelineStatus.RETIRED},
            PipelineStatus.RETIRED: set(),
        }
        if target not in allowed[pipeline.status]:
            raise PipelineError(f"invalid pipeline transition: {pipeline.status.value} -> {target.value}")
        if pipeline.definition_sha256 != self._digests[key]:
            raise PipelineError("pipeline definition was mutated after registration")
        if target == PipelineStatus.ACTIVE:
            for other_key, other in list(self._pipelines.items()):
                if other.pipeline_id == pipeline_id and other.status == PipelineStatus.ACTIVE:
                    self._pipelines[other_key] = other.model_copy(update={"status": PipelineStatus.RETIRED})
        updated = pipeline.model_copy(update={"status": target})
        self._pipelines[key] = updated
        return updated.model_copy(deep=True)

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
        key = (pipeline.pipeline_id, pipeline.version)
        registered = self._pipelines.get(key)
        if registered is None or registered.definition_sha256 != self._digests[key]:
            raise PipelineError("pipeline definition is not immutable")
        outputs: dict[str, Any] = dict(initial_inputs)
        nodes = {node.node_id: node for node in pipeline.nodes}
        for node_id in self._orders[key]:
            await checkpoint()
            node = nodes[node_id]
            operator = self._operators[node.operator_id]
            inputs = {name: outputs[source] for name, source in node.inputs.items()}
            parameters = {**node.parameters, **run_parameters}
            definition = operator.definition
            attempts = definition.max_attempts if definition.failure_policy == "retry" else 1
            result: dict[str, Any] | None = None
            for attempt in range(attempts):
                try:
                    result = await self._execute_operator(
                        operator,
                        context,
                        inputs,
                        parameters,
                        checkpoint,
                        timeout_seconds=definition.timeout_seconds,
                    )
                    break
                except TimeoutError as exc:
                    if attempt + 1 == attempts:
                        raise PipelineError(f"operator timed out: {node.operator_id}") from exc
                except DomainUnavailable:
                    raise
                except ExecutionInterrupted:
                    raise
                except Exception as exc:
                    if attempt + 1 == attempts:
                        raise PipelineError(f"operator failed: {node.operator_id}") from exc
                await asyncio.sleep(min(1.0, 0.05 * (2**attempt)))
            if result is None:
                raise PipelineError(f"operator did not produce a result: {node.operator_id}")
            missing = sorted(set(definition.output_types) - set(result))
            if missing:
                raise PipelineError(f"operator {node.operator_id} omitted outputs: {', '.join(missing)}")
            for name, value in result.items():
                outputs[f"{node.node_id}.{name}"] = value
        if pipeline.output not in outputs:
            raise PipelineError(f"pipeline output was not produced: {pipeline.output}")
        return outputs[pipeline.output]

    @staticmethod
    async def _execute_operator(
        operator: Operator,
        context: ExecutionContext,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
        checkpoint: Any,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        task = asyncio.create_task(operator.execute(context, inputs, parameters))
        running_seconds = 0.0
        running_since = time.monotonic()
        paused_since = context.control.paused_seconds

        async def stop_operator() -> None:
            context.control.cancel()
            done, _ = await asyncio.wait({task}, timeout=1.0)
            if task not in done:
                task.cancel()
            with suppress(BaseException):
                await task

        try:
            while True:
                remaining_seconds = timeout_seconds - running_seconds
                if remaining_seconds <= 0:
                    await stop_operator()
                    raise TimeoutError
                done, _ = await asyncio.wait({task}, timeout=min(0.1, remaining_seconds))
                now = time.monotonic()
                paused_now = context.control.paused_seconds
                running_seconds += max(0.0, now - running_since - (paused_now - paused_since))
                running_since = now
                paused_since = paused_now
                if task in done:
                    return task.result()
                if running_seconds >= timeout_seconds:
                    await stop_operator()
                    raise TimeoutError
                try:
                    await checkpoint()
                except BaseException:
                    await stop_operator()
                    raise
                checkpoint_finished = time.monotonic()
                paused_after_checkpoint = context.control.paused_seconds
                running_seconds += max(
                    0.0,
                    checkpoint_finished - running_since - (paused_after_checkpoint - paused_since),
                )
                running_since = checkpoint_finished
                paused_since = paused_after_checkpoint
        except asyncio.CancelledError:
            await stop_operator()
            raise

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
        available_types = {"$media.bytes": "bytes", "$media.input": "media/input"}
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
