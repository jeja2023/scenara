"""Portrait watchlist matching, alert lifecycle, and Stream Run observation hook."""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from scenara.domains.portrait.service import PortraitRepository
from scenara.domains.portrait.trajectory import TrajectoryService
from scenara.platform.audit import AuditLogger
from scenara.platform.features import FeatureStore
from scenara.platform.models import CreateRunRequest, PipelineRef, PrincipalContext, ResultEnvelope, RunRecord
from scenara.platform.observability import SurveillanceMetrics
from scenara.platform.policy import PolicyProvider, require_allowed
from scenara.platform.store import StateStore
from scenara.platform.surveillance import (
    AlertCandidate,
    AlertEvent,
    AlertModality,
    AlertPage,
    AlertRecord,
    AlertStatus,
    CreateSurveillanceTaskRequest,
    CreateWatchlistMemberRequest,
    CreateWatchlistRequest,
    DebounceState,
    MatchPolicy,
    ObservationBatch,
    ObservationEvidence,
    SurveillanceConflict,
    SurveillanceNotFound,
    SurveillanceRepository,
    SurveillanceTask,
    SurveillanceTaskPage,
    SurveillanceTaskStatus,
    TaskBinding,
    ThresholdPolicy,
    TriageAlertRequest,
    UpdateSurveillanceTaskRequest,
    UpdateWatchlistMemberRequest,
    UpdateWatchlistRequest,
    Watchlist,
    WatchlistMember,
    WatchlistMemberPage,
    WatchlistPage,
)


class StreamRunPort(Protocol):
    async def create_run(
        self, context: PrincipalContext, request: CreateRunRequest, *, idempotency_key: str
    ) -> Any: ...

    async def cancel_stream_session(self, context: PrincipalContext, session_id: str) -> Any: ...


def _utc_rfc3339(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _binding_for_source(task: SurveillanceTask, source_id: str) -> list[TaskBinding]:
    return [item for item in task.bindings if item.source_id == source_id]


class PortraitSurveillanceMatcher:
    """Matches private run observations against enrolled watchlist identities.

    Enrollment vectors remain inside ``FeatureStore`` and are never serialized
    into public run or alert responses.  The implementation deliberately uses
    per-feature-space search and filters results to active watchlist members.
    """

    def __init__(self, features: FeatureStore, portraits: PortraitRepository) -> None:
        self._features = features
        self._portraits = portraits

    async def match(
        self,
        *,
        tenant_id: str,
        project_id: str,
        members: list[WatchlistMember],
        observation: ObservationBatch,
        policy: ThresholdPolicy,
    ) -> list[tuple[WatchlistMember, float, AlertModality, dict[str, dict[str, str]]]]:
        """Return one highest-quality candidate per active watchlist member."""

        members_by_identity: dict[str, list[WatchlistMember]] = {}
        for member in members:
            members_by_identity.setdefault(member.portrait_identity_id, []).append(member)
        enrollments: dict[tuple[str, str], set[str]] = {}
        for identity_id in members_by_identity:
            for enrollment in await self._portraits.list_enrollments(tenant_id, project_id, identity_id):
                if enrollment.expires_at is not None and enrollment.expires_at <= observation.last_seen_at:
                    continue
                enrollments.setdefault((enrollment.feature_space_id, enrollment.modality), set()).add(identity_id)

        scores: dict[str, dict[str, float]] = {}
        bindings: dict[str, dict[str, dict[str, str]]] = {}
        for evidence in observation.evidence:
            threshold = policy.face_threshold if evidence.modality == "face" else policy.body_threshold
            quality_floor = policy.min_face_quality if evidence.modality == "face" else policy.min_body_quality
            if evidence.quality < quality_floor or threshold is None:
                continue
            for (space_id, modality), identities in enrollments.items():
                if modality != evidence.modality:
                    continue
                space = await self._features.get_space(space_id)
                if (
                    space is None
                    or space.domain != "portrait"
                    or space.model_id != evidence.model_id
                    or space.model_version != evidence.model_version
                    or space.dimension != len(evidence.embedding)
                ):
                    continue
                matches = await self._features.search(
                    tenant_id,
                    project_id,
                    space_id,
                    evidence.embedding,
                    limit=1000,
                    threshold=threshold,
                )
                for match in matches:
                    if match.subject_type != "portrait_identity" or match.subject_id not in identities:
                        continue
                    bucket = scores.setdefault(match.subject_id, {})
                    if match.score > bucket.get(evidence.modality, -1.0):
                        bucket[evidence.modality] = match.score
                        bindings.setdefault(match.subject_id, {})[evidence.modality] = {
                            "feature_space_id": space_id,
                            "model_id": evidence.model_id,
                            "model_version": evidence.model_version,
                        }

        resolved: list[tuple[WatchlistMember, float, AlertModality, dict[str, dict[str, str]]]] = []
        for identity_id, modality_scores in scores.items():
            face = modality_scores.get("face")
            body = modality_scores.get("body")
            if face is not None and body is not None:
                score = (policy.face_weight * face + policy.body_weight * body) / (policy.face_weight + policy.body_weight)
                modality = AlertModality.FUSED
            elif face is not None:
                score, modality = face, AlertModality.FACE
            elif body is not None:
                score, modality = body, AlertModality.BODY
            else:  # pragma: no cover - scores is never populated with an empty dictionary
                continue
            for member in members_by_identity[identity_id]:
                resolved.append((member, score, modality, bindings.get(identity_id, {})))
        return sorted(resolved, key=lambda item: (-item[1], item[0].member_id))


class SurveillanceService:
    def __init__(
        self,
        *,
        repository: SurveillanceRepository,
        features: FeatureStore,
        portraits: PortraitRepository,
        trajectory: TrajectoryService,
        state: StateStore,
        policy: PolicyProvider,
        audit: AuditLogger,
        alert_snapshot_retention_days: int = 30,
        metrics: SurveillanceMetrics | None = None,
    ) -> None:
        self._repository = repository
        self._matcher = PortraitSurveillanceMatcher(features, portraits)
        self._portraits = portraits
        self._trajectory = trajectory
        self._state = state
        self._policy = policy
        self._audit = audit
        self._runs: StreamRunPort | None = None
        self._alert_snapshot_retention_days = alert_snapshot_retention_days
        self._metrics = metrics

    def bind_run_service(self, runs: StreamRunPort) -> None:
        self._runs = runs

    async def create_watchlist(self, context: PrincipalContext, request: CreateWatchlistRequest) -> Watchlist:
        await require_allowed(self._policy, context, "create", "surveillance_watchlist")
        now = time.time()
        watchlist = Watchlist(
            watchlist_id=f"wsl_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        stored = await self._repository.create_watchlist(watchlist)
        await self._audit.record(
            context,
            action="surveillance.watchlist.create",
            resource_type="surveillance_watchlist",
            resource_id=stored.watchlist_id,
        )
        return stored

    async def list_watchlists(self, context: PrincipalContext, *, offset: int, limit: int) -> WatchlistPage:
        await require_allowed(self._policy, context, "list", "surveillance_watchlist")
        items, total = await self._repository.list_watchlists(context.tenant_id, context.project_id, offset=offset, limit=limit)
        return WatchlistPage(items=items, offset=offset, limit=limit, total=total)

    async def get_watchlist(self, context: PrincipalContext, watchlist_id: str) -> Watchlist:
        await require_allowed(self._policy, context, "read", "surveillance_watchlist", {"watchlist_id": watchlist_id})
        value = await self._repository.get_watchlist(context.tenant_id, context.project_id, watchlist_id)
        if value is None:
            raise SurveillanceNotFound("watchlist not found")
        return value

    async def update_watchlist(
        self, context: PrincipalContext, watchlist_id: str, request: UpdateWatchlistRequest
    ) -> Watchlist:
        await require_allowed(self._policy, context, "write", "surveillance_watchlist", {"watchlist_id": watchlist_id})
        current = await self.get_watchlist(context, watchlist_id)
        updates = request.model_dump(exclude_none=True, exclude={"expected_revision"})
        stored = await self._repository.save_watchlist(
            current.model_copy(update={**updates, "updated_at": time.time()}), expected_revision=request.expected_revision
        )
        await self._audit.record(
            context,
            action="surveillance.watchlist.update",
            resource_type="surveillance_watchlist",
            resource_id=watchlist_id,
            evidence={"revision": stored.revision},
        )
        return stored

    async def delete_watchlist(self, context: PrincipalContext, watchlist_id: str) -> None:
        await require_allowed(self._policy, context, "delete", "surveillance_watchlist", {"watchlist_id": watchlist_id})
        await self.get_watchlist(context, watchlist_id)
        if not await self._repository.delete_watchlist(context.tenant_id, context.project_id, watchlist_id):
            raise SurveillanceConflict("watchlist changed during deletion")
        await self._audit.record(
            context,
            action="surveillance.watchlist.delete",
            resource_type="surveillance_watchlist",
            resource_id=watchlist_id,
        )

    async def create_member(
        self, context: PrincipalContext, watchlist_id: str, request: CreateWatchlistMemberRequest
    ) -> WatchlistMember:
        await require_allowed(self._policy, context, "create", "surveillance_watchlist", {"watchlist_id": watchlist_id})
        await self.get_watchlist(context, watchlist_id)
        # Do not accept a naked identity ID: ensure it is visible in the same tenant/project.
        identity = await self._portraits.get_identity(
            context.tenant_id, context.project_id, request.portrait_identity_id
        )
        if identity is None:
            raise SurveillanceNotFound("portrait identity not found")
        now = time.time()
        member = WatchlistMember(
            member_id=f"wsm_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            watchlist_id=watchlist_id,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        stored = await self._repository.create_member(member)
        await self._audit.record(
            context,
            action="surveillance.member.create",
            resource_type="surveillance_watchlist",
            resource_id=stored.member_id,
            evidence={"watchlist_id": watchlist_id, "portrait_identity_id": stored.portrait_identity_id},
        )
        return stored

    async def list_members(
        self, context: PrincipalContext, watchlist_id: str, *, offset: int, limit: int
    ) -> WatchlistMemberPage:
        await self.get_watchlist(context, watchlist_id)
        items, total = await self._repository.list_members(
            context.tenant_id, context.project_id, watchlist_id, offset=offset, limit=limit
        )
        return WatchlistMemberPage(items=items, offset=offset, limit=limit, total=total)

    async def update_member(
        self, context: PrincipalContext, watchlist_id: str, member_id: str, request: UpdateWatchlistMemberRequest
    ) -> WatchlistMember:
        await require_allowed(self._policy, context, "write", "surveillance_watchlist", {"watchlist_id": watchlist_id})
        current = await self._repository.get_member(context.tenant_id, context.project_id, member_id)
        if current is None or current.watchlist_id != watchlist_id:
            raise SurveillanceNotFound("watchlist member not found")
        updates = request.model_dump(exclude_none=True, exclude={"expected_revision"})
        stored = await self._repository.save_member(
            current.model_copy(update={**updates, "updated_at": time.time()}), expected_revision=request.expected_revision
        )
        await self._audit.record(
            context,
            action="surveillance.member.update",
            resource_type="surveillance_watchlist",
            resource_id=member_id,
            evidence={"watchlist_id": watchlist_id, "revision": stored.revision},
        )
        return stored

    async def delete_member(self, context: PrincipalContext, watchlist_id: str, member_id: str) -> None:
        await require_allowed(self._policy, context, "delete", "surveillance_watchlist", {"watchlist_id": watchlist_id})
        current = await self._repository.get_member(context.tenant_id, context.project_id, member_id)
        if current is None or current.watchlist_id != watchlist_id:
            raise SurveillanceNotFound("watchlist member not found")
        if not await self._repository.delete_member(context.tenant_id, context.project_id, member_id):
            raise SurveillanceConflict("watchlist member changed during deletion")
        await self._audit.record(
            context,
            action="surveillance.member.delete",
            resource_type="surveillance_watchlist",
            resource_id=member_id,
            evidence={"watchlist_id": watchlist_id},
        )

    async def _validate_task_references(
        self, context: PrincipalContext, watchlist_ids: list[str], bindings: list[TaskBinding]
    ) -> None:
        for watchlist_id in watchlist_ids:
            watchlist = await self._repository.get_watchlist(context.tenant_id, context.project_id, watchlist_id)
            if watchlist is None or watchlist.status.value == "archived":
                raise SurveillanceNotFound(f"watchlist is unavailable: {watchlist_id}")
        for binding in bindings:
            source = await self._state.get_source(context.tenant_id, context.project_id, binding.source_id)
            if source is None:
                raise SurveillanceNotFound(f"media source not found: {binding.source_id}")
            await self._trajectory.get_camera(context, binding.camera_id)

    async def create_task(self, context: PrincipalContext, request: CreateSurveillanceTaskRequest) -> SurveillanceTask:
        await require_allowed(self._policy, context, "create", "surveillance_task")
        await self._validate_task_references(context, request.watchlist_ids, request.bindings)
        now = time.time()
        task = SurveillanceTask(
            task_id=f"st_{uuid4().hex}",
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        stored = await self._repository.create_task(task)
        await self._audit.record(
            context,
            action="surveillance.task.create",
            resource_type="surveillance_task",
            resource_id=stored.task_id,
        )
        return stored

    async def list_tasks(self, context: PrincipalContext, *, offset: int, limit: int) -> SurveillanceTaskPage:
        await require_allowed(self._policy, context, "list", "surveillance_task")
        items, total = await self._repository.list_tasks(context.tenant_id, context.project_id, offset=offset, limit=limit)
        return SurveillanceTaskPage(items=items, offset=offset, limit=limit, total=total)

    async def get_task(self, context: PrincipalContext, task_id: str) -> SurveillanceTask:
        await require_allowed(self._policy, context, "read", "surveillance_task", {"task_id": task_id})
        task = await self._repository.get_task(context.tenant_id, context.project_id, task_id)
        if task is None:
            raise SurveillanceNotFound("surveillance task not found")
        return task

    async def update_task(
        self, context: PrincipalContext, task_id: str, request: UpdateSurveillanceTaskRequest
    ) -> SurveillanceTask:
        await require_allowed(self._policy, context, "write", "surveillance_task", {"task_id": task_id})
        current = await self.get_task(context, task_id)
        updates = request.model_dump(exclude_none=True, exclude={"expected_revision"})
        target_watchlists = updates.get("watchlist_ids", current.watchlist_ids)
        target_bindings = updates.get("bindings", current.bindings)
        await self._validate_task_references(context, target_watchlists, target_bindings)
        stored = await self._repository.save_task(
            current.model_copy(update={**updates, "updated_at": time.time()}), expected_revision=request.expected_revision
        )
        await self._audit.record(
            context,
            action="surveillance.task.update",
            resource_type="surveillance_task",
            resource_id=task_id,
            evidence={"revision": stored.revision},
        )
        return stored

    async def start_task(self, context: PrincipalContext, task_id: str) -> SurveillanceTask:
        await require_allowed(self._policy, context, "start", "surveillance_task", {"task_id": task_id})
        current = await self.get_task(context, task_id)
        if current.status == SurveillanceTaskStatus.ACTIVE:
            return current
        if current.status == SurveillanceTaskStatus.EXPIRED:
            raise SurveillanceConflict("expired surveillance task cannot be started")
        await self._validate_task_references(context, current.watchlist_ids, current.bindings)
        stored = await self._repository.save_task(
            current.model_copy(update={"status": SurveillanceTaskStatus.ACTIVE, "updated_at": time.time()}),
            expected_revision=current.revision,
        )
        await self._audit.record(
            context,
            action="surveillance.task.start",
            resource_type="surveillance_task",
            resource_id=task_id,
        )
        return await self._reconcile_task(context, stored)

    async def pause_task(self, context: PrincipalContext, task_id: str) -> SurveillanceTask:
        await require_allowed(self._policy, context, "pause", "surveillance_task", {"task_id": task_id})
        current = await self.get_task(context, task_id)
        if current.status == SurveillanceTaskStatus.PAUSED:
            return current
        stored = await self._repository.save_task(
            current.model_copy(update={"status": SurveillanceTaskStatus.PAUSED, "updated_at": time.time()}),
            expected_revision=current.revision,
        )
        await self._stop_bindings(context, stored)
        await self._audit.record(
            context,
            action="surveillance.task.pause",
            resource_type="surveillance_task",
            resource_id=task_id,
        )
        return await self.get_task(context, task_id)

    async def resume_task(self, context: PrincipalContext, task_id: str) -> SurveillanceTask:
        return await self.start_task(context, task_id)

    async def _stop_bindings(self, context: PrincipalContext, task: SurveillanceTask) -> None:
        if self._runs is None:
            return
        for binding in task.bindings:
            if binding.stream_session_id:
                try:
                    await self._runs.cancel_stream_session(context, binding.stream_session_id)
                except Exception:
                    continue

    async def _reconcile_task(self, context: PrincipalContext, task: SurveillanceTask, *, moment: float | None = None) -> SurveillanceTask:
        if self._runs is None or task.status != SurveillanceTaskStatus.ACTIVE:
            return task
        if not task.schedule.is_active(moment):
            await self._stop_bindings(context, task)
            return task
        updated_bindings = list(task.bindings)
        changed = False
        for index, binding in enumerate(updated_bindings):
            if binding.stream_session_id:
                continue
            try:
                outcome = await self._runs.create_run(
                    context,
                    CreateRunRequest(
                        domain="portrait",
                        pipeline=PipelineRef(pipeline_id="portrait.analysis", version="0.4.0"),
                        source_id=binding.source_id,
                        parameters={"camera_id": binding.camera_id},
                    ),
                    # A task transition changes its revision.  Keeping the revision
                    # in the idempotency key makes repeated reconciliation safe while
                    # still allowing a paused/cancelled binding to start a new stream.
                    idempotency_key=f"surveillance:{task.task_id}:{binding.binding_id}:{task.revision}",
                )
                run = outcome.run
                updated_bindings[index] = binding.model_copy(
                    update={"active_run_id": run.run_id, "stream_session_id": run.stream_session_id, "last_error": None}
                )
                changed = True
            except Exception as exc:
                updated_bindings[index] = binding.model_copy(update={"last_error": str(exc)[:500]})
                changed = True
        if not changed:
            return task
        try:
            return await self._repository.save_task(
                task.model_copy(update={"bindings": updated_bindings, "updated_at": time.time()}),
                expected_revision=task.revision,
            )
        except SurveillanceConflict:
            return await self.get_task(context, task.task_id)

    async def reconcile(self, *, moment: float | None = None) -> int:
        """Start scheduled active bindings; callable by the existing scheduler."""

        count = 0
        for task in await self._repository.list_all_active_tasks():
            context = PrincipalContext(
                tenant_id=task.tenant_id,
                project_id=task.project_id,
                principal_id=task.created_by,
            )
            await self._reconcile_task(context, task, moment=moment)
            count += 1
        if self._metrics is not None:
            self._metrics.set_active_tasks(count)
        return count

    async def evaluate_run_result(self, run: RunRecord, result: ResultEnvelope) -> None:
        """RunService hook.  Safe failures are logged by the caller and do not fail parsing."""

        if not run.source_id or result.domain != "portrait":
            return
        observations = self._observations(run, result)
        if not observations:
            return
        tasks = await self._repository.list_active_tasks_for_source(run.tenant_id, run.project_id, run.source_id)
        context = PrincipalContext(tenant_id=run.tenant_id, project_id=run.project_id, principal_id=run.principal_id)
        for task in tasks:
            if not task.schedule.is_active():
                continue
            if task.match_policy != MatchPolicy.ALERT_ON_MATCH:
                continue
            bindings = _binding_for_source(task, run.source_id)
            for binding in bindings:
                for observation in observations:
                    if observation.camera_id != binding.camera_id:
                        continue
                    await self._evaluate_observation(context, task, binding, observation)

    def _observations(self, run: RunRecord, result: ResultEnvelope) -> list[ObservationBatch]:
        raw_tracks = getattr(result, "_trajectory_tracks", [])
        if not isinstance(raw_tracks, list):
            raw_tracks = []
        camera_id = str(run.parameters.get("camera_id") or "")
        if not camera_id:
            return []
        bindings_by_capability = {item.capability: item for item in result.models}
        started = run.parameters.get("recording_started_at")
        base_time = float(started) if isinstance(started, int | float) and not isinstance(started, bool) else time.time()
        source: Literal["recording", "processing_time"] = (
            "recording"
            if isinstance(started, int | float) and not isinstance(started, bool)
            else "processing_time"
        )
        artifact = next((item for item in reversed(result.artifacts) if item.artifact_type == "unit_frame"), None)
        public_tracks = getattr(result.domain_payload, "tracks", [])
        trajectory_refs = {
            str(track.get("track_id") or ""): (
                track.get("long_term_identity_id"),
                track.get("trajectory_segment_id"),
            )
            for track in public_tracks
            if isinstance(track, dict)
        }
        observations: list[ObservationBatch] = []
        if not raw_tracks:
            index_vectors = getattr(result, "_index_vectors", [])
            last_unit = result.units[-1] if result.units else None
            for index in index_vectors if isinstance(index_vectors, list) else []:
                if getattr(index, "modality", "face") != "face":
                    continue
                vector = getattr(index, "vector", None)
                if not isinstance(vector, list) or not vector:
                    continue
                observations.append(
                    ObservationBatch(
                        run_id=run.run_id,
                        source_id=run.source_id or "",
                        camera_id=camera_id,
                        unit_id=last_unit.unit_id if last_unit else "",
                        track_id=str(getattr(index, "object_id", "")),
                        first_seen_at=base_time,
                        last_seen_at=base_time,
                        pts_ms=last_unit.pts_ms if last_unit else None,
                        timestamp_source=source,
                        evidence=[
                            ObservationEvidence(
                                modality="face",
                                embedding=[float(value) for value in vector],
                                quality=float(getattr(index, "quality", 0.0) or 0.0),
                                model_id=str(getattr(index, "model_id", "unknown")),
                                model_version=str(getattr(index, "model_version", "unknown")),
                            )
                        ],
                        snapshot_artifact_id=artifact.artifact_id if artifact else None,
                        snapshot_object_key=artifact.object_key if artifact else None,
                        trace_id=run.trace_id,
                    )
                )
            return observations
        for track in raw_tracks:
            if not isinstance(track, dict):
                continue
            evidence: list[ObservationEvidence] = []
            evidence_specs: tuple[tuple[Literal["body", "face"], str, str], ...] = (
                ("body", "template", "body_embedding"),
                ("face", "face_template", "face_embedding"),
            )
            for modality, key, capability in evidence_specs:
                template = track.get(key)
                vector = template.get("embedding") if isinstance(template, dict) else None
                binding = bindings_by_capability.get(capability)
                if not isinstance(vector, list) or not vector or binding is None:
                    continue
                quality = track.get("tracklet_quality_score", 0.0)
                evidence.append(
                    ObservationEvidence(
                        modality=modality,
                        embedding=[float(value) for value in vector],
                        quality=max(0.0, min(1.0, float(quality or 0.0))),
                        model_id=binding.model_id,
                        model_version=binding.version,
                    )
                )
            if not evidence:
                continue
            track_id = str(track.get("track_id") or "")
            trajectory_identity_id, trajectory_segment_id = trajectory_refs.get(track_id, (None, None))
            first_pts = track.get("first_pts_ms")
            last_pts = track.get("last_pts_ms")
            first = base_time + float(first_pts) / 1000 if isinstance(first_pts, int | float) else base_time
            last = base_time + float(last_pts) / 1000 if isinstance(last_pts, int | float) else first
            observations.append(
                ObservationBatch(
                    run_id=run.run_id,
                    source_id=run.source_id or "",
                    camera_id=camera_id,
                    unit_id=result.units[-1].unit_id if result.units else "",
                    track_id=track_id,
                    first_seen_at=min(first, last),
                    last_seen_at=max(first, last),
                    pts_ms=int(last_pts) if isinstance(last_pts, int | float) else None,
                    timestamp_source=source,
                    evidence=evidence,
                    snapshot_artifact_id=artifact.artifact_id if artifact else None,
                    snapshot_object_key=artifact.object_key if artifact else None,
                    trajectory_identity_id=str(trajectory_identity_id) if trajectory_identity_id else None,
                    trajectory_segment_id=str(trajectory_segment_id) if trajectory_segment_id else None,
                    trace_id=run.trace_id,
                )
            )
        return observations

    async def _evaluate_observation(
        self, context: PrincipalContext, task: SurveillanceTask, binding: TaskBinding, observation: ObservationBatch
    ) -> None:
        now = observation.last_seen_at
        members = await self._repository.list_active_members(
            context.tenant_id, context.project_id, task.watchlist_ids, at=now
        )
        if not members:
            return
        started = time.perf_counter()
        matches = await self._matcher.match(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            members=members,
            observation=observation,
            policy=task.threshold_policy,
        )
        if self._metrics is not None:
            observed = "fused" if len(observation.evidence) == 2 else observation.evidence[0].modality
            self._metrics.observe_match(observed, "feature_store", time.perf_counter() - started)
        for member, score, modality, model_bindings in matches:
            key_text = "|".join(
                (context.tenant_id, context.project_id, task.task_id, binding.binding_id, member.watchlist_id, member.portrait_identity_id)
            )
            debounce_key = hashlib.sha256(key_text.encode("utf-8")).hexdigest()
            window_start = int(observation.first_seen_at // task.cooldown_seconds) * task.cooldown_seconds
            idempotency_key = hashlib.sha256(f"{key_text}|{window_start}".encode("utf-8")).hexdigest()
            created_at = time.time()
            alert_id = f"alt_{uuid4().hex}"
            alert = AlertRecord(
                alert_id=alert_id,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                task_id=task.task_id,
                binding_id=binding.binding_id,
                watchlist_id=member.watchlist_id,
                member_id=member.member_id,
                portrait_identity_id=member.portrait_identity_id,
                source_id=observation.source_id,
                camera_id=observation.camera_id,
                run_id=observation.run_id,
                unit_id=observation.unit_id,
                track_id=observation.track_id,
                trajectory_identity_id=observation.trajectory_identity_id,
                trajectory_segment_id=observation.trajectory_segment_id,
                match_score=score,
                max_score=score,
                modality=modality,
                threshold_policy_version=task.threshold_policy.policy_version,
                model_bindings=model_bindings,
                snapshot_artifact_id=observation.snapshot_artifact_id,
                snapshot_retention_expires_at=created_at + self._alert_snapshot_retention_days * 86_400,
                first_seen_at=observation.first_seen_at,
                last_seen_at=observation.last_seen_at,
                triggered_at=observation.last_seen_at,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
            )
            event = AlertEvent(
                event_id=f"alevt_{uuid4().hex}",
                event_type="alert.triggered",
                occurred_at=_utc_rfc3339(observation.last_seen_at),
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                trace_id=observation.trace_id,
                alert_id=alert.alert_id,
                task_id=task.task_id,
                camera_id=observation.camera_id,
                portrait_identity_id=member.portrait_identity_id,
                match_score=score,
                modality=modality,
                snapshot_artifact_id=observation.snapshot_artifact_id,
                deduplication_key=idempotency_key,
                status=AlertStatus.PENDING,
                created_at=created_at,
            )
            debounce = DebounceState(
                debounce_key=debounce_key,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                task_id=task.task_id,
                binding_id=binding.binding_id,
                watchlist_id=member.watchlist_id,
                portrait_identity_id=member.portrait_identity_id,
                first_seen_at=observation.first_seen_at,
                last_seen_at=observation.last_seen_at,
                max_score=score,
                modality=modality,
                cooldown_until=observation.last_seen_at + task.cooldown_seconds,
            )
            outcome = await self._repository.record_alert(AlertCandidate(alert=alert, event=event, debounce=debounce))
            if not outcome.emitted or outcome.event is None:
                if self._metrics is not None:
                    self._metrics.record_suppressed("cooldown_or_idempotency")
                continue
            if observation.snapshot_object_key is not None:
                await self._state.protect_object_for_alert(
                    context.tenant_id,
                    context.project_id,
                    observation.snapshot_object_key,
                    outcome.alert.alert_id,
                    outcome.alert.snapshot_retention_expires_at or outcome.alert.created_at,
                )
            if self._metrics is not None:
                self._metrics.record_alert(task.alert_level.value, outcome.alert.status.value, modality.value)
            if not getattr(self._repository, "atomic_webhook_outbox", False):
                await self._state.enqueue_webhook_event(
                    context.tenant_id,
                    context.project_id,
                    event_id=outcome.event.event_id,
                    event_type=outcome.event.event_type,
                    payload=outcome.event.model_dump(mode="json"),
                    created_at=outcome.event.created_at,
                )
            await self._audit.record(
                context,
                action="surveillance.alert.trigger",
                resource_type="surveillance_alert",
                resource_id=outcome.alert.alert_id,
                evidence={"task_id": task.task_id, "camera_id": observation.camera_id, "modality": modality.value},
            )

    async def list_alerts(
        self,
        context: PrincipalContext,
        *,
        status: AlertStatus | None,
        task_id: str | None,
        camera_id: str | None,
        watchlist_id: str | None,
        portrait_identity_id: str | None,
        since: float | None,
        until: float | None,
        offset: int,
        limit: int,
    ) -> AlertPage:
        await require_allowed(self._policy, context, "list", "surveillance_alert")
        items, total = await self._repository.list_alerts(
            context.tenant_id,
            context.project_id,
            status=status,
            task_id=task_id,
            camera_id=camera_id,
            watchlist_id=watchlist_id,
            portrait_identity_id=portrait_identity_id,
            since=since,
            until=until,
            offset=offset,
            limit=limit,
        )
        return AlertPage(items=items, offset=offset, limit=limit, total=total)

    async def get_alert(self, context: PrincipalContext, alert_id: str) -> AlertRecord:
        await require_allowed(self._policy, context, "read", "surveillance_alert", {"alert_id": alert_id})
        alert = await self._repository.get_alert(context.tenant_id, context.project_id, alert_id)
        if alert is None:
            raise SurveillanceNotFound("alert not found")
        return alert

    async def triage_alert(self, context: PrincipalContext, alert_id: str, request: TriageAlertRequest) -> AlertRecord:
        await require_allowed(self._policy, context, "triage", "surveillance_alert", {"alert_id": alert_id})
        current = await self.get_alert(context, alert_id)
        if current.status != AlertStatus.PENDING:
            raise SurveillanceConflict("alert has already been triaged")
        now = time.time()
        updated = current.model_copy(
            update={
                "status": AlertStatus(request.status),
                "triaged_by": context.principal_id,
                "triaged_at": now,
                "triage_reason": request.reason,
                "triage_notes": request.notes,
                "updated_at": now,
            }
        )
        event = AlertEvent(
            event_id=f"alevt_{uuid4().hex}",
            event_type="alert.triaged",
            occurred_at=_utc_rfc3339(now),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            trace_id=context.traceparent,
            alert_id=alert_id,
            task_id=updated.task_id,
            camera_id=updated.camera_id,
            portrait_identity_id=updated.portrait_identity_id,
            match_score=updated.match_score,
            modality=updated.modality,
            snapshot_artifact_id=updated.snapshot_artifact_id,
            deduplication_key=updated.idempotency_key,
            status=updated.status,
            created_at=now,
        )
        outcome = await self._repository.triage_alert(updated, event, expected_revision=request.expected_revision)
        if self._metrics is not None:
            self._metrics.record_alert("unknown", outcome.alert.status.value, outcome.alert.modality.value)
        if outcome.event is not None and not getattr(self._repository, "atomic_webhook_outbox", False):
            await self._state.enqueue_webhook_event(
                context.tenant_id,
                context.project_id,
                event_id=outcome.event.event_id,
                event_type=outcome.event.event_type,
                payload=outcome.event.model_dump(mode="json"),
                created_at=outcome.event.created_at,
            )
        await self._audit.record(
            context,
            action="surveillance.alert.triage",
            resource_type="surveillance_alert",
            resource_id=alert_id,
            evidence={"status": outcome.alert.status.value, "reason": request.reason},
        )
        return outcome.alert

    async def events_after(self, context: PrincipalContext, cursor: int, *, limit: int = 500) -> list[AlertEvent]:
        await require_allowed(self._policy, context, "read", "surveillance_alert")
        return await self._repository.events_after(context.tenant_id, context.project_id, cursor, limit=limit)


__all__ = ["PortraitSurveillanceMatcher", "SurveillanceService"]
