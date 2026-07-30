from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from scenara.bootstrap import build_runtime
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.infrastructure.queue import RedisRunQueue
from scenara.platform.models import (
    CreateRunRequest,
    MediaKind,
    OcrDomainPayload,
    PipelineRef,
    PipelineStatus,
    PrincipalContext,
    ResultEnvelope,
    RunStatus,
)
from scenara.platform.pipeline import ExecutionContext, OperatorDefinition, PipelineDefinition, PipelineNode
from scenara.settings import load_settings

pytestmark = pytest.mark.integration

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def require_integration_services() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("set SCENARA_RUN_INTEGRATION=1 to run service integration tests")


class GateOperator:
    definition = OperatorDefinition(
        operator_id="integration.lifecycle.gate",
        version="1.0.0",
        domain="integration",
        input_types={"media": "bytes"},
        output_types={"token": "integration/token"},
        timeout_seconds=30,
    )

    def __init__(self) -> None:
        self.entered: dict[str, asyncio.Event] = {}
        self.releases: dict[str, asyncio.Event] = {}

    async def execute(
        self, context: ExecutionContext, inputs: dict[str, Any], parameters: dict[str, Any]
    ) -> dict[str, Any]:
        del inputs, parameters
        self.entered.setdefault(context.run_id, asyncio.Event()).set()
        await self.releases.setdefault(context.run_id, asyncio.Event()).wait()
        return {"token": context.run_id}


class ResultOperator:
    definition = OperatorDefinition(
        operator_id="integration.lifecycle.result",
        version="1.0.0",
        domain="integration",
        input_types={"token": "integration/token"},
        output_types={"result": "result/ocr"},
        timeout_seconds=30,
    )

    async def execute(
        self, context: ExecutionContext, inputs: dict[str, Any], parameters: dict[str, Any]
    ) -> dict[str, Any]:
        del inputs, parameters
        return {
            "result": ResultEnvelope(
                run_id=context.run_id,
                domain="integration",
                pipeline=PipelineRef(
                    pipeline_id=context.pipeline_id,
                    version=context.pipeline_version,
                ),
                asset_id=context.asset_id,
                domain_payload=OcrDomainPayload(text="integration lifecycle"),
                created_at=time.time(),
            )
        }


async def _wait_status(runtime: Any, context: PrincipalContext, run_id: str, status: RunStatus) -> None:
    async with asyncio.timeout(10):
        while True:
            run = await runtime.runs.get_run(context, run_id)
            if run.status == status:
                return
            await asyncio.sleep(0.02)


async def _wait_entered(
    gate: GateOperator,
    run_id: str,
    consumer: asyncio.Task[None],
    runtime: Any,
    context: PrincipalContext,
) -> None:
    async with asyncio.timeout(10):
        while run_id not in gate.entered:
            if consumer.done():
                await consumer
            run = await runtime.runs.get_run(context, run_id)
            if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
                pytest.fail(f"worker terminated before gate: {run.error_code}: {run.termination_reason}")
            await asyncio.sleep(0.02)
        await gate.entered[run_id].wait()


async def test_real_services_pause_resume_cancel_and_result_persistence(tmp_path: Path) -> None:
    suffix = uuid4().hex
    tenant_id = f"lifecycle_{suffix}"
    context = PrincipalContext(tenant_id=tenant_id, project_id="qualification", principal_id="integration")
    settings = replace(
        load_settings(),
        profile="integration",
        state_backend="postgres",
        object_backend="s3",
        queue_backend="redis",
        data_dir=tmp_path,
        postgres_dsn="postgresql://scenara:scenara-integration@127.0.0.1:55432/scenara",
        redis_url="redis://127.0.0.1:56379/14",
        s3_endpoint_url="http://127.0.0.1:59000",
        s3_bucket="scenara",
        s3_access_key="scenara",
        s3_secret_key=os.getenv("SCENARA_INTEGRATION_S3_SECRET_KEY", "scenara-integration-secret"),
        auth_required=False,
        production_models_required=False,
        secret_encryption_key="",
    )
    runtime = build_runtime(settings)
    queue = RedisRunQueue(
        settings.redis_url,
        stream=f"scenara:integration:lifecycle:{suffix}",
        group=f"workers-{suffix}",
        visibility_timeout_ms=500,
    )
    runtime.queue = queue
    runtime.runs.queue = queue
    queue.set_handler(runtime.runs.execute_run)
    gate = GateOperator()
    runtime.pipelines.register_operator(gate)
    runtime.pipelines.register_operator(ResultOperator())
    pipeline = PipelineDefinition(
        pipeline_id=f"integration.lifecycle-{suffix}",
        version="1.0.0",
        domain="integration",
        status=PipelineStatus.ACTIVE,
        nodes=[
            PipelineNode(
                node_id="gate",
                operator_id=gate.definition.operator_id,
                inputs={"media": "$media.bytes"},
            ),
            PipelineNode(
                node_id="result",
                operator_id="integration.lifecycle.result",
                inputs={"token": "gate.token"},
            ),
        ],
        output="result.result",
        allowed_parameters={"max_units", "sample_interval_ms"},
        pausable=True,
    )
    runtime.pipelines.register_pipeline(pipeline)
    await runtime.open()
    consumer = asyncio.create_task(
        queue.consume_forever(consumer=f"worker-{suffix}", lane="batch", block_ms=25)
    )
    assets = []
    run_ids: list[str] = []
    try:
        first_asset = await runtime.runs.create_asset(
            context,
            data=b"first lifecycle payload",
            filename="first.bin",
            content_type="application/octet-stream",
            kind=MediaKind.VIDEO,
        )
        assets.append(first_asset)
        first = (
            await runtime.runs.create_run(
                context,
                CreateRunRequest(
                    domain="integration",
                    pipeline=PipelineRef(pipeline_id=pipeline.pipeline_id, version=pipeline.version),
                    asset_id=first_asset.asset_id,
                ),
                idempotency_key=f"pause-{suffix}",
            )
        ).run
        run_ids.append(first.run_id)
        await _wait_entered(gate, first.run_id, consumer, runtime, context)
        await _wait_status(runtime, context, first.run_id, RunStatus.RUNNING)
        assert (await runtime.runs.transition(context, first.run_id, "pause")).status == RunStatus.PAUSING
        gate.releases[first.run_id].set()
        await _wait_status(runtime, context, first.run_id, RunStatus.PAUSED)
        assert (await runtime.runs.transition(context, first.run_id, "resume")).status == RunStatus.RUNNING
        await _wait_status(runtime, context, first.run_id, RunStatus.COMPLETED)
        first_result = await runtime.runs.result(context, first.run_id)
        assert isinstance(first_result.domain_payload, OcrDomainPayload)
        assert first_result.domain_payload.text == "integration lifecycle"

        second_asset = await runtime.runs.create_asset(
            context,
            data=b"second lifecycle payload",
            filename="second.bin",
            content_type="application/octet-stream",
            kind=MediaKind.VIDEO,
        )
        assets.append(second_asset)
        second = (
            await runtime.runs.create_run(
                context,
                CreateRunRequest(
                    domain="integration",
                    pipeline=PipelineRef(pipeline_id=pipeline.pipeline_id, version=pipeline.version),
                    asset_id=second_asset.asset_id,
                ),
                idempotency_key=f"cancel-{suffix}",
            )
        ).run
        run_ids.append(second.run_id)
        await _wait_entered(gate, second.run_id, consumer, runtime, context)
        await _wait_status(runtime, context, second.run_id, RunStatus.RUNNING)
        assert (await runtime.runs.transition(context, second.run_id, "cancel")).status == RunStatus.CANCELLING
        gate.releases[second.run_id].set()
        await _wait_status(runtime, context, second.run_id, RunStatus.CANCELLED)
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        if queue._client is not None:
            await queue._client.delete(
                f"scenara:integration:lifecycle:{suffix}:batch",
                f"scenara:integration:lifecycle:{suffix}:stream",
            )
        for asset in assets:
            await runtime.objects.delete(asset.object_key)
        for run_id in run_ids:
            reference = await runtime.state.get_result_reference(tenant_id, "qualification", run_id)
            if reference is not None:
                for object_key in [reference.object_key, *reference.shard_keys]:
                    await runtime.objects.delete(object_key)
        assert isinstance(runtime.state, PostgresStateStore)
        async with runtime.state.pool.connection() as connection, connection.transaction():
            await connection.execute("DELETE FROM scenara_object_retention WHERE tenant_id = %s", (tenant_id,))
            await connection.execute("DELETE FROM scenara_audit_events WHERE tenant_id = %s", (tenant_id,))
            await connection.execute("DELETE FROM scenara_runs WHERE tenant_id = %s", (tenant_id,))
            await connection.execute("DELETE FROM scenara_media_assets WHERE tenant_id = %s", (tenant_id,))
            await connection.execute(
                "DELETE FROM scenara_pipeline_versions WHERE pipeline_id = %s", (pipeline.pipeline_id,)
            )
        await runtime.close()
