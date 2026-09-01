"""Run execution lifecycle mixin."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from scenara.platform.artifacts import RunArtifactSink
from scenara.platform.audit import AuditLogger
from scenara.platform.index import (
    IndexDefinition,
    IndexRecord,
    IndexRecordKind,
    IndexSourceRef,
)
from scenara.platform.media_batch import MediaInput
from scenara.platform.model_runtime import runtime_binding_scope
from scenara.platform.models import (
    TERMINAL_RUN_STATUSES,
    CreateRunRequest,
    MediaKind,
    ObjectRetentionRecord,
    PrincipalContext,
    ResultEnvelope,
    ResultReference,
    RunEvent,
    RunRecord,
    RunStatus,
)
from scenara.platform.network import validate_external_url
from scenara.platform.pipeline import (
    DomainUnavailable,
    ExecutionContext,
    ExecutionControl,
    PipelineDefinition,
    PipelineError,
    PipelineRegistry,
)
from scenara.platform.secrets import SecretStore
from scenara.platform.services_errors import (
    ExecutionStopped,
    InvalidTransition,
    ResourceNotFound,
)
from scenara.platform.store import StateConflict, StateStore

logger = logging.getLogger(__name__)


class RunExecutionMixin:
    """Execution behavior mixed into the public run service."""

    state: StateStore
    objects: Any
    secrets: SecretStore
    pipelines: PipelineRegistry
    audit: AuditLogger
    indexes: Any
    active_model_resolver: Any
    observation_evaluators: Sequence[Any]
    registrars: Sequence[Any]
    production: bool
    allow_private_media_sources: bool
    media_sample_interval_ms: int
    stream_segment_duration_ms: int
    preview_retention_days: int
    result_shard_units: int
    structured_result_retention_days: int

    def _artifact_sink(self, run: RunRecord) -> RunArtifactSink | None:
        raise NotImplementedError

    async def pipeline_definition(
        self, *args: Any, **kwargs: Any
    ) -> PipelineDefinition:
        raise NotImplementedError

    async def create_run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def execute_run(self, tenant_id: str, project_id: str, run_id: str) -> None:
        run = await self.state.get_run(tenant_id, project_id, run_id)
        if run is None:
            raise ResourceNotFound("queued run does not exist")
        if run.status in TERMINAL_RUN_STATUSES:
            return
        sink = self._artifact_sink(run)
        media_file_path: str | None = None
        try:
            run = await self._begin_execution(run)
            if run.status == RunStatus.CANCELLED:
                return
            if run.source_id and run.stream_session_id:
                await self._event(
                    run,
                    "stream.segment.started",
                    {
                        "session_id": run.stream_session_id,
                        "segment_index": run.stream_segment_index or 0,
                    },
                )
            data: bytes | None = None
            source_url: str | None = None
            filename: str | None = None
            content_type = "application/octet-stream"
            if run.asset_id:
                asset = await self.state.get_asset(
                    run.tenant_id, run.project_id, run.asset_id
                )
                if (
                    asset is None
                    or asset.deleted_at is not None
                    or asset.original_deleted_at is not None
                ):
                    raise ResourceNotFound("media asset disappeared before execution")
                media_kind = asset.kind
                filename = asset.filename
                content_type = asset.content_type
                if media_kind == MediaKind.VIDEO:
                    suffix = Path(filename or "media.mp4").suffix or ".mp4"
                    handle = tempfile.NamedTemporaryFile(
                        prefix="scenara-object-", suffix=suffix, delete=False
                    )
                    handle.close()
                    media_file_path = handle.name
                    await self.objects.get_to_file(
                        asset.object_key,
                        Path(media_file_path),
                        expected_sha256=asset.sha256,
                    )
                else:
                    data = await self.objects.get(
                        asset.object_key, expected_sha256=asset.sha256
                    )
            else:
                source = await self.state.get_source(
                    run.tenant_id, run.project_id, run.source_id or ""
                )
                if source is None:
                    raise ResourceNotFound("media source disappeared before execution")
                source_url = await self.secrets.get(source.secret_ref)
                await validate_external_url(
                    source_url,
                    allowed_schemes=frozenset({"rtsp", "rtmp", "http", "https"}),
                    allow_private=self.allow_private_media_sources,
                    allow_credentials=True,
                )
                media_kind = MediaKind.STREAM
            pipeline = await self.pipeline_definition(
                run.pipeline.pipeline_id,
                run.pipeline.version,
                active_only=False,
            )
            model_bindings = (
                await self.active_model_resolver.active_runtime_bindings(
                    run.tenant_id, run.project_id
                )
                if self.active_model_resolver is not None
                else {}
            )
            checkpoint_run: RunRecord = run
            execution_run = run
            published_unit_count = 0

            async def report_progress(
                progress: float | None, payload: dict[str, Any]
            ) -> None:
                nonlocal checkpoint_run
                for _ in range(4):
                    latest = await self.state.get_run(
                        execution_run.tenant_id,
                        execution_run.project_id,
                        execution_run.run_id,
                    )
                    if latest is None:
                        raise ResourceNotFound(
                            "run disappeared while reporting progress"
                        )
                    if latest.status in TERMINAL_RUN_STATUSES:
                        return
                    next_progress = (
                        latest.progress
                        if progress is None
                        else max(latest.progress, min(0.99, progress))
                    )
                    if progress is None:
                        await self._event(
                            latest, "run.progress", {"progress": None, **payload}
                        )
                        return
                    if next_progress <= latest.progress:
                        return
                    updated = latest.model_copy(
                        update={"progress": next_progress, "updated_at": time.time()}
                    )
                    try:
                        saved = await self.state.save_run(
                            updated, expected_revision=latest.revision
                        )
                    except StateConflict:
                        continue
                    checkpoint_run = saved
                    await self._event(
                        saved,
                        "run.progress",
                        {"progress": saved.progress, **payload},
                    )
                    return
                raise StateConflict("run progress could not be saved")

            async def publish_partial_result(partial: Any) -> None:
                nonlocal published_unit_count
                if not isinstance(partial, ResultEnvelope):
                    raise PipelineError(
                        "partial pipeline result is not a ResultEnvelope"
                    )
                if sink is not None and (sink.artifacts or sink.warnings):
                    partial = partial.model_copy(
                        update={
                            "artifacts": [*partial.artifacts, *sink.artifacts],
                            "warnings": [*partial.warnings, *sink.warnings],
                        },
                        deep=True,
                    )
                try:
                    await self._store_result(execution_run, partial, sink, partial=True)
                    for evaluator in self.observation_evaluators:
                        try:
                            await evaluator.evaluate_run_result(execution_run, partial)
                        except Exception:
                            # Surveillance and similar observers enrich a run but must not
                            # turn an otherwise valid parse result into a failed run.
                            logger.exception(
                                "run observation evaluator failed for run %s",
                                execution_run.run_id,
                            )
                    latest = await self.state.get_run(
                        execution_run.tenant_id,
                        execution_run.project_id,
                        execution_run.run_id,
                    )
                    if (
                        latest is not None
                        and latest.status not in TERMINAL_RUN_STATUSES
                    ):
                        unit_count = len(partial.units)
                        delta_count = max(0, unit_count - published_unit_count)
                        if delta_count:
                            await self._event(
                                latest,
                                "result.delta",
                                {
                                    "sequence": published_unit_count,
                                    "unit_offset": published_unit_count,
                                    "unit_count": delta_count,
                                    "unit_total": unit_count,
                                    "result_url": f"/api/v1/runs/{execution_run.run_id}/result"
                                    f"?unit_offset={published_unit_count}&unit_limit={delta_count}",
                                },
                            )
                            published_unit_count = unit_count
                        await self._event(
                            latest,
                            "result.partial",
                            {"unit_count": unit_count, "progress": latest.progress},
                        )
                except Exception:
                    logger.exception(
                        "could not publish partial result for run %s",
                        execution_run.run_id,
                    )

            context = ExecutionContext(
                run_id=run.run_id,
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                pipeline_id=run.pipeline.pipeline_id,
                pipeline_version=run.pipeline.version,
                asset_id=run.asset_id,
                source_id=run.source_id,
                filename=filename,
                content_type=content_type,
                production=self.production,
                model_bindings=model_bindings,
                artifacts=sink,
                progress_reporter=report_progress,
                partial_result_publisher=publish_partial_result,
            )

            async def checkpoint() -> None:
                await self._checkpoint(checkpoint_run, context.control)

            parameters = {
                "sample_interval_ms": self.media_sample_interval_ms,
                **run.parameters,
            }
            ignored_max_units = parameters.pop("max_units", None)
            if ignored_max_units is not None:
                logger.info(
                    "ignored legacy max_units=%r while executing stored %s run %s; "
                    "parse unit limits are not supported",
                    ignored_max_units,
                    media_kind.value,
                    run.run_id,
                )
            if media_kind == MediaKind.STREAM:
                parameters.setdefault(
                    "stream_segment_duration_ms", self.stream_segment_duration_ms
                )
            if run.stream_segment_index is not None:
                parameters["stream_segment_index"] = run.stream_segment_index
            with runtime_binding_scope(model_bindings):
                result = await self.pipelines.execute(
                    pipeline,
                    context,
                    {
                        "$media.bytes": data or b"",
                        "$media.input": MediaInput(
                            kind=media_kind,
                            content_type=content_type,
                            data=data,
                            source_url=source_url,
                            file_path=media_file_path,
                            filename=filename,
                        ),
                    },
                    parameters,
                    checkpoint,
                )
            if not isinstance(result, ResultEnvelope):
                raise PipelineError("pipeline did not return a ResultEnvelope")
            if sink is not None and (sink.artifacts or sink.warnings):
                result = result.model_copy(
                    update={
                        "artifacts": [*result.artifacts, *sink.artifacts],
                        "warnings": [*result.warnings, *sink.warnings],
                    },
                    deep=True,
                )
            for registrar in self.registrars:
                try:
                    await registrar.register_run_result(run, result)
                except Exception:
                    # 登记是结果的增益信息，失败不应让整个 run 失败。
                    logger.exception(
                        "run result registrar failed for run %s", run.run_id
                    )
            await self._store_result(run, result, sink)
            for evaluator in self.observation_evaluators:
                try:
                    await evaluator.evaluate_run_result(run, result)
                except Exception:
                    logger.exception(
                        "run observation evaluator failed for run %s", run.run_id
                    )
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is None:
                raise ResourceNotFound("run disappeared during execution")
            worker_context = PrincipalContext(
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                principal_id=run.principal_id,
            )
            await self.audit.record(
                worker_context,
                action="run.complete",
                resource_type="run",
                resource_id=run.run_id,
                evidence={"unit_count": len(result.units), "domain": result.domain},
            )
            media_termination = next(
                (
                    warning.removeprefix("media_termination:")
                    for warning in result.warnings
                    if warning.startswith("media_termination:")
                ),
                None,
            )
            run = await self._set_status(
                latest,
                RunStatus.COMPLETED,
                progress=1.0,
                completed_at=time.time(),
                termination_reason=media_termination,
            )
            await self._event(
                run,
                "result.available",
                {
                    "result_schema_version": result.schema_version,
                    "unit_count": len(result.units),
                    "result_url": f"/api/v1/runs/{run.run_id}/result",
                },
            )
            if (
                run.source_id
                and run.stream_session_id
                and media_termination == "segment_window_completed"
            ):
                await self._rollover_stream_segment(run)
        except ExecutionStopped:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest and latest.status != RunStatus.CANCELLED:
                cancelled = await self._set_status(
                    latest,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
                await self.audit.record(
                    PrincipalContext(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        principal_id=run.principal_id,
                    ),
                    action="run.cancel",
                    resource_type="run",
                    resource_id=run.run_id,
                    evidence={"status": cancelled.status.value},
                )
            try:
                reference = await self.state.get_result_reference(
                    run.tenant_id, run.project_id, run.run_id
                )
                if reference is not None:
                    if sink is not None:
                        for record in sink.retention_records(
                            created_at=run.created_at,
                            expires_at=run.created_at
                            + self.preview_retention_days * 86_400,
                        ):
                            await self.state.track_object(record)
                    await self._event(
                        run,
                        "result.available",
                        {
                            "result_schema_version": reference.schema_version,
                            "unit_count": reference.unit_count,
                            "result_url": f"/api/v1/runs/{run.run_id}/result",
                        },
                    )
                elif sink is not None:
                    await sink.discard()
            except Exception:
                logger.exception(
                    "could not finalize retained partial result for cancelled run %s",
                    run.run_id,
                )
        except Exception as exc:
            logger.exception("run execution failed for %s", run.run_id)
            await self._discard_partial_result(run)
            if sink is not None:
                await sink.discard()
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest and latest.status not in TERMINAL_RUN_STATUSES:
                code = (
                    "DOMAIN_UNAVAILABLE"
                    if isinstance(exc, DomainUnavailable)
                    else "PIPELINE_EXECUTION_FAILED"
                )
                failed = await self._set_status(
                    latest,
                    RunStatus.FAILED,
                    completed_at=time.time(),
                    error_code=code,
                    termination_reason=str(exc)[:500],
                )
                await self._event(
                    failed, "run.error", {"code": code, "message": str(exc)[:500]}
                )
                await self.audit.record(
                    PrincipalContext(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        principal_id=run.principal_id,
                    ),
                    action="run.fail",
                    resource_type="run",
                    resource_id=run.run_id,
                    outcome="failure",
                    evidence={"code": code, "message": str(exc)[:500]},
                )
        finally:
            if media_file_path is not None:
                with suppress(FileNotFoundError):
                    os.unlink(media_file_path)

    async def _store_result(
        self,
        run: RunRecord,
        result: ResultEnvelope,
        sink: RunArtifactSink | None = None,
        *,
        partial: bool = False,
    ) -> ResultReference:
        run_base_key = (
            f"tenants/{run.tenant_id}/projects/{run.project_id}/runs/{run.run_id}"
        )
        base_key = f"{run_base_key}/partial" if partial else run_base_key
        shard_keys: list[str] = []
        shard_sha256: list[str] = []
        shard_unit_counts: list[int] = []
        written_keys: list[str] = []
        previous = await self.state.get_result_reference(
            run.tenant_id, run.project_id, run.run_id
        )
        try:
            if partial:
                previous_count = 0
                if previous is not None and previous.index_status == "partial":
                    shard_keys = list(previous.shard_keys)
                    shard_sha256 = list(previous.shard_sha256)
                    shard_unit_counts = list(previous.shard_unit_counts)
                    if len(shard_unit_counts) != len(shard_keys):
                        shard_unit_counts = [self.result_shard_units] * len(shard_keys)
                        if shard_unit_counts:
                            shard_unit_counts[-1] = max(
                                0,
                                previous.unit_count
                                - self.result_shard_units
                                * (len(shard_unit_counts) - 1),
                            )
                    previous_count = previous.unit_count
                if len(result.units) < previous_count:
                    raise PipelineError("partial result unit count must be monotonic")
                new_units = result.units[previous_count:]
                for offset in range(0, len(new_units), self.result_shard_units):
                    units = new_units[offset : offset + self.result_shard_units]
                    shard_document = json.dumps(
                        [unit.model_dump(mode="json") for unit in units],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    shard_key = f"{base_key}/units-{len(shard_keys):06d}.json"
                    await self.objects.put(
                        shard_key,
                        shard_document,
                        "application/json",
                        sha256=hashlib.sha256(shard_document).hexdigest(),
                        retention_category="structured_result",
                    )
                    written_keys.append(shard_key)
                    shard_keys.append(shard_key)
                    shard_sha256.append(hashlib.sha256(shard_document).hexdigest())
                    shard_unit_counts.append(len(units))
                index_result = result.model_copy(update={"units": []})
            elif len(result.units) > self.result_shard_units:
                for offset in range(0, len(result.units), self.result_shard_units):
                    units = result.units[offset : offset + self.result_shard_units]
                    shard_document = json.dumps(
                        [unit.model_dump(mode="json") for unit in units],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    shard_key = (
                        f"{base_key}/units-{offset // self.result_shard_units:06d}.json"
                    )
                    await self.objects.put(
                        shard_key,
                        shard_document,
                        "application/json",
                        sha256=hashlib.sha256(shard_document).hexdigest(),
                        retention_category="structured_result",
                    )
                    written_keys.append(shard_key)
                    shard_keys.append(shard_key)
                    shard_sha256.append(hashlib.sha256(shard_document).hexdigest())
                    shard_unit_counts.append(len(units))
                index_result = result.model_copy(update={"units": []})
            else:
                index_result = result
            result_document = index_result.model_dump_json().encode("utf-8")
            result_key = (
                f"{base_key}/result-{len(result.units):012d}-{uuid4().hex}.json"
                if partial
                else f"{base_key}/result.json"
            )
            await self.objects.put(
                result_key,
                result_document,
                "application/json",
                sha256=hashlib.sha256(result_document).hexdigest(),
                retention_category="structured_result",
            )
            if previous is None or previous.object_key != result_key:
                written_keys.append(result_key)
            asset = (
                await self.state.get_asset(run.tenant_id, run.project_id, run.asset_id)
                if run.asset_id
                else None
            )
            source = (
                await self.state.get_source(
                    run.tenant_id, run.project_id, run.source_id
                )
                if run.source_id
                else None
            )
            reference = ResultReference(
                run_id=run.run_id,
                object_key=result_key,
                sha256=hashlib.sha256(result_document).hexdigest(),
                unit_count=len(result.units),
                shard_keys=shard_keys,
                shard_sha256=shard_sha256,
                shard_unit_counts=shard_unit_counts,
                domain=result.domain,
                created_at=result.created_at,
                asset_id=run.asset_id,
                source_id=run.source_id,
                media_kind=asset.kind
                if asset is not None
                else (MediaKind.STREAM if source else None),
                resource_name=asset.filename
                if asset is not None
                else source.name
                if source is not None
                else None,
                object_count=sum(len(unit.objects) for unit in result.units),
                person_count=len(getattr(result.domain_payload, "persons", [])),
                face_count=len(getattr(result.domain_payload, "faces", [])),
                ocr_block_count=len(getattr(result.domain_payload, "blocks", [])),
                text_length=len(getattr(result.domain_payload, "text", "") or ""),
                warning_count=len(result.warnings),
                index_status="partial" if partial else "ready",
            )
            expires_at = run.created_at + self.structured_result_retention_days * 86_400
            for object_key in written_keys:
                await self.state.track_object(
                    ObjectRetentionRecord(
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        object_key=object_key,
                        category="structured_result",
                        owner_type="run_result",
                        owner_id=run.run_id,
                        created_at=run.created_at,
                        expires_at=expires_at,
                    )
                )
            if sink is not None and not partial:
                # 特征裁剪图和单元帧属于派生预览，遵循预览保留窗口，
                # 而不是更长的结构化结果保留窗口。
                for record in sink.retention_records(
                    created_at=run.created_at,
                    expires_at=run.created_at + self.preview_retention_days * 86_400,
                ):
                    await self.state.track_object(record)
            if not partial and self.indexes is not None:
                try:
                    await self._index_result(run, result)
                except Exception:
                    logger.exception(
                        "result index update failed for run %s", run.run_id
                    )
                    reference = reference.model_copy(update={"index_status": "partial"})
            await self.state.save_result_reference(
                run.tenant_id, run.project_id, reference
            )
            if previous is not None and previous.object_key != reference.object_key:
                reused = set(reference.shard_keys)
                previous_keys = [
                    previous.object_key,
                    *(key for key in previous.shard_keys if key not in reused),
                ]
                for object_key in previous_keys:
                    with suppress(Exception):
                        await self.objects.delete(object_key)
                with suppress(Exception):
                    await self.state.mark_objects_deleted(previous_keys, time.time())
            return reference
        except Exception:
            for object_key in written_keys:
                with suppress(Exception):
                    await self.objects.delete(object_key)
            with suppress(Exception):
                await self.state.mark_objects_deleted(written_keys, time.time())
            raise

    async def _index_result(self, run: RunRecord, result: ResultEnvelope) -> None:
        if self.indexes is None:
            return
        index_id = f"result.{result.domain}"
        await self.indexes.delete_source(
            run.tenant_id, run.project_id, "run_result", run.run_id
        )
        await self.indexes.create_index(
            IndexDefinition(
                index_id=index_id,
                domain=result.domain,
                record_kind=IndexRecordKind.MULTIMODAL,
                text_analyzer="simple",
            )
        )
        index_expires_at = (
            run.created_at + self.structured_result_retention_days * 86_400
        )

        def safe_metadata(value: object) -> dict[str, object]:
            if not isinstance(value, dict):
                return {}
            return {
                str(key): nested
                for key, nested in value.items()
                if str(key)
                not in {
                    "embedding",
                    "_tracking_embedding",
                    "_face_embedding",
                    "vector",
                    "crop",
                }
                and isinstance(nested, (str, int, float, bool, list, dict, type(None)))
            }

        records: list[IndexRecord] = []
        for unit in result.units:
            for item in unit.objects:
                records.append(
                    IndexRecord(
                        record_id=f"idxr_{run.run_id}_{unit.unit_id}_{item.object_id}",
                        tenant_id=run.tenant_id,
                        project_id=run.project_id,
                        index_id=index_id,
                        domain=result.domain,
                        kind=IndexRecordKind.MULTIMODAL,
                        source=IndexSourceRef(
                            source_type="run_result",
                            source_id=run.run_id,
                            asset_id=run.asset_id,
                            run_id=run.run_id,
                            unit_id=unit.unit_id,
                            object_id=item.object_id,
                            artifact_id=item.crop_artifact_id,
                            page_number=unit.page_number,
                            pts_ms=unit.pts_ms,
                        ),
                        metadata={
                            "object_type": item.object_type,
                            "score": item.score,
                            "bbox": item.bbox.model_dump(mode="json")
                            if item.bbox
                            else None,
                            "attributes": safe_metadata(item.attributes),
                            "source_id": run.source_id,
                        },
                        expires_at=index_expires_at,
                    )
                )
        payload = result.domain_payload
        full_text = str(getattr(payload, "text", "") or "")
        if full_text:
            records.append(
                IndexRecord(
                    record_id=f"idxr_{run.run_id}_text",
                    tenant_id=run.tenant_id,
                    project_id=run.project_id,
                    index_id=index_id,
                    domain=result.domain,
                    kind=IndexRecordKind.MULTIMODAL,
                    source=IndexSourceRef(
                        source_type="run_result",
                        source_id=run.run_id,
                        asset_id=run.asset_id,
                        run_id=run.run_id,
                    ),
                    text=full_text,
                    metadata={
                        "language": getattr(payload, "language", None),
                        "block_count": len(getattr(payload, "blocks", [])),
                        "source_id": run.source_id,
                    },
                    expires_at=index_expires_at,
                )
            )
        for block in getattr(payload, "blocks", []):
            block_id = str(getattr(block, "block_id", ""))
            text = str(getattr(block, "text", "") or "")
            if not block_id or not text:
                continue
            records.append(
                IndexRecord(
                    record_id=f"idxr_{run.run_id}_block_{block_id}",
                    tenant_id=run.tenant_id,
                    project_id=run.project_id,
                    index_id=index_id,
                    domain=result.domain,
                    kind=IndexRecordKind.MULTIMODAL,
                    source=IndexSourceRef(
                        source_type="run_result",
                        source_id=run.run_id,
                        asset_id=run.asset_id,
                        run_id=run.run_id,
                    ),
                    text=text,
                    metadata={
                        "score": getattr(block, "score", None),
                        "block_type": getattr(block, "block_type", "text"),
                        "source_id": run.source_id,
                    },
                    expires_at=index_expires_at,
                )
            )
        await self.indexes.upsert_many(records)
        vector_records: list[IndexRecord] = []
        for hint in result._index_vectors:
            vector_index_id = f"result.{hint.feature_space_id}"
            await self.indexes.create_index(
                IndexDefinition(
                    index_id=vector_index_id,
                    domain=result.domain,
                    record_kind=IndexRecordKind.VECTOR,
                    vector_dimension=len(hint.vector),
                    vector_model_id=hint.model_id,
                    vector_model_version=hint.model_version,
                    distance_metric="cosine",
                    threshold=0.8,
                )
            )
            location: tuple[str | None, int | None, int | None, int | None] = (
                None,
                None,
                None,
                None,
            )
            artifact_id: str | None = None
            for unit in result.units:
                for item in unit.objects:
                    if item.object_id == hint.object_id:
                        location = (
                            unit.unit_id,
                            unit.page_number,
                            unit.pts_ms,
                            unit.index,
                        )
                        artifact_id = item.crop_artifact_id
                        break
                if location[0] is not None:
                    break
            unit_id, page_number, pts_ms, unit_index = location
            vector_records.append(
                IndexRecord(
                    record_id=f"idxv_{run.run_id}_{hint.object_id}",
                    tenant_id=run.tenant_id,
                    project_id=run.project_id,
                    index_id=vector_index_id,
                    domain=result.domain,
                    kind=IndexRecordKind.VECTOR,
                    source=IndexSourceRef(
                        source_type="run_result",
                        source_id=run.run_id,
                        asset_id=run.asset_id,
                        run_id=run.run_id,
                        unit_id=unit_id,
                        object_id=hint.object_id,
                        artifact_id=artifact_id,
                        page_number=page_number,
                        pts_ms=pts_ms,
                    ),
                    vector=hint.vector,
                    metadata={
                        "object_type": "face",
                        "feature_space_id": hint.feature_space_id,
                        "model_id": hint.model_id,
                        "model_version": hint.model_version,
                        "quality": hint.quality,
                        "unit_index": unit_index,
                        "source_id": run.source_id,
                    },
                    expires_at=index_expires_at,
                )
            )
        await self.indexes.upsert_many(vector_records)

    async def _discard_partial_result(self, run: RunRecord) -> None:
        try:
            reference = await self.state.get_result_reference(
                run.tenant_id, run.project_id, run.run_id
            )
        except Exception:
            logger.exception("could not inspect partial result for run %s", run.run_id)
            return
        if reference is None or "/partial/" not in reference.object_key:
            return
        object_keys = [reference.object_key, *reference.shard_keys]
        for object_key in object_keys:
            with suppress(Exception):
                await self.objects.delete(object_key)
        with suppress(Exception):
            await self.state.mark_objects_deleted(object_keys, time.time())

    async def _begin_execution(self, run: RunRecord) -> RunRecord:
        for _ in range(4):
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            if run.status == RunStatus.CANCELLING:
                return await self._set_status(
                    run,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
            if run.status == RunStatus.QUEUED:
                try:
                    return await self._set_status(
                        run, RunStatus.RUNNING, started_at=time.time()
                    )
                except StateConflict:
                    latest = await self.state.get_run(
                        run.tenant_id, run.project_id, run.run_id
                    )
                    if latest is None:
                        raise ResourceNotFound(
                            "run disappeared before execution"
                        ) from None
                    run = latest
                    continue
            if run.status in {RunStatus.RUNNING, RunStatus.PAUSING, RunStatus.PAUSED}:
                return run
            raise InvalidTransition(f"run cannot start from {run.status.value}")
        raise StateConflict("run could not acquire execution state")

    async def _checkpoint(
        self, run: RunRecord, control: ExecutionControl | None = None
    ) -> None:
        while True:
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is None:
                if control is not None:
                    control.cancel()
                raise ExecutionStopped
            if latest.status == RunStatus.CANCELLING:
                if control is not None:
                    control.cancel()
                await self._set_status(
                    latest,
                    RunStatus.CANCELLED,
                    completed_at=time.time(),
                    termination_reason="cancelled_by_user",
                )
                raise ExecutionStopped
            if latest.status == RunStatus.PAUSING:
                if control is not None:
                    control.pause()
                latest = await self._set_status(latest, RunStatus.PAUSED)
            if latest.status == RunStatus.PAUSED:
                if control is not None:
                    control.pause()
                await asyncio.sleep(0.1)
                continue
            if control is not None:
                control.resume()
            return

    async def _set_status(
        self, run: RunRecord, status: RunStatus, **changes: Any
    ) -> RunRecord:
        updated = run.model_copy(
            update={"status": status, "updated_at": time.time(), **changes}
        )
        saved = await self.state.save_run(updated, expected_revision=run.revision)
        await self._event(saved, f"run.{status.value}")
        return saved

    async def _rollover_stream_segment(self, run: RunRecord) -> None:
        """Queue the next bounded stream segment after a normal segment boundary."""

        if not run.source_id or not run.stream_session_id:
            return
        next_index = (run.stream_segment_index or 0) + 1
        context = PrincipalContext(
            tenant_id=run.tenant_id,
            project_id=run.project_id,
            principal_id=run.principal_id,
        )
        request = CreateRunRequest(
            domain=run.domain,
            pipeline=run.pipeline,
            source_id=run.source_id,
            parameters=dict(run.parameters),
            priority=run.priority,
        )
        try:
            outcome = await self.create_run(
                context,
                request,
                idempotency_key=f"stream:{run.stream_session_id}:{next_index}",
                stream_session_id=run.stream_session_id,
                stream_segment_index=next_index,
                previous_run_id=run.run_id,
            )
            latest = await self.state.get_run(run.tenant_id, run.project_id, run.run_id)
            if latest is not None and latest.next_run_id != outcome.run.run_id:
                updated = latest.model_copy(
                    update={
                        "next_run_id": outcome.run.run_id,
                        "updated_at": time.time(),
                    }
                )
                try:
                    saved = await self.state.save_run(
                        updated, expected_revision=latest.revision
                    )
                except StateConflict:
                    saved = latest
            else:
                saved = latest or run
            await self._event(
                saved,
                "stream.segment.completed",
                {
                    "session_id": run.stream_session_id,
                    "segment_index": run.stream_segment_index or 0,
                    "next_run_id": outcome.run.run_id,
                    "next_segment_index": next_index,
                },
            )
        except Exception as exc:
            logger.exception(
                "could not roll over stream session %s", run.stream_session_id
            )
            await self._event(
                run,
                "stream.session.error",
                {"session_id": run.stream_session_id, "message": str(exc)[:500]},
            )

    async def _event(
        self, run: RunRecord, event_type: str, payload: dict[str, Any] | None = None
    ) -> RunEvent:
        created_at = time.time()
        occurred_at = (
            datetime.fromtimestamp(created_at, UTC).isoformat().replace("+00:00", "Z")
        )
        trace_id = run.trace_id or uuid4().hex
        return await self.state.append_event(
            run.tenant_id,
            run.project_id,
            RunEvent(
                run_id=run.run_id,
                event_id=1,
                event_type=event_type,
                event_version="1.0",
                occurred_at=occurred_at,
                producer="scenara",
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                request_id=run.request_id,
                trace_id=trace_id,
                status=run.status,
                payload=payload or {},
                created_at=created_at,
            ),
        )
