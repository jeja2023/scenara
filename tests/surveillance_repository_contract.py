"""布控预警仓储的跨后端契约。

`record_alert` 是全平台最依赖事务语义的一段代码：它在冷却窗口内把重复命中
折叠进同一条告警，跨窗口才产生新告警。内存实现用字典模拟、PostgreSQL 实现用
跨两表的 FOR UPDATE 加锁，两者必须给出同一套可观察行为。
"""

from __future__ import annotations

import time
from uuid import uuid4

from scenara.platform.surveillance import (
    AlertCandidate,
    AlertEvent,
    AlertModality,
    AlertRecord,
    AlertStatus,
    DebounceState,
    MatchPolicy,
    SurveillanceRepository,
    SurveillanceTask,
    SurveillanceTaskStatus,
    TaskBinding,
    ThresholdPolicy,
    Watchlist,
    WatchlistCategory,
    WatchlistMember,
    WatchlistMemberStatus,
    WatchlistStatus,
)


def _rfc3339(moment: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(moment))


class _Fixture:
    """一套彼此关联的名单、成员与布控任务标识。"""

    def __init__(
        self,
        tenant_id: str,
        project_id: str,
        portrait_identity_ids: tuple[str, str] | None = None,
        source_id: str = "src_contract",
        camera_id: str = "camera-contract",
    ) -> None:
        suffix = uuid4().hex[:20]
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.watchlist_id = f"wl-{suffix}"
        self.member_id = f"wm-{suffix}"
        self.task_id = f"st-{suffix}"
        self.binding_id = f"bind-{suffix}"
        self.source_id = source_id
        self.camera_id = camera_id
        identities = portrait_identity_ids or (f"pid-{suffix}", f"pid-{suffix}-alt")
        self.identity_id, self.paused_identity_id = identities
        self.debounce_key = f"debounce-{suffix}-{uuid4().hex}"

    def alert(self, *, triggered_at: float, score: float, window: int) -> AlertCandidate:
        alert_id = f"alt_{uuid4().hex}"
        now = time.time()
        alert = AlertRecord(
            alert_id=alert_id,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            task_id=self.task_id,
            binding_id=self.binding_id,
            watchlist_id=self.watchlist_id,
            member_id=self.member_id,
            portrait_identity_id=self.identity_id,
            source_id=self.source_id,
            camera_id=self.camera_id,
            run_id=f"run_{uuid4().hex[:12]}",
            match_score=score,
            max_score=score,
            modality=AlertModality.FACE,
            threshold_policy_version="contract-v1",
            first_seen_at=triggered_at,
            last_seen_at=triggered_at,
            triggered_at=triggered_at,
            idempotency_key=f"{self.debounce_key}-{window}",
            created_at=now,
            updated_at=now,
        )
        event = AlertEvent(
            event_id=f"alevt_{uuid4().hex}",
            event_type="alert.triggered",
            occurred_at=_rfc3339(triggered_at),
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            alert_id=alert_id,
            task_id=self.task_id,
            camera_id=self.camera_id,
            portrait_identity_id=self.identity_id,
            match_score=score,
            modality=AlertModality.FACE,
            deduplication_key=alert.idempotency_key,
            status=AlertStatus.PENDING,
            created_at=now,
        )
        debounce = DebounceState(
            debounce_key=self.debounce_key,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            task_id=self.task_id,
            binding_id=self.binding_id,
            watchlist_id=self.watchlist_id,
            portrait_identity_id=self.identity_id,
            first_seen_at=triggered_at,
            last_seen_at=triggered_at,
            max_score=score,
            modality=AlertModality.FACE,
            cooldown_until=triggered_at + 30,
        )
        return AlertCandidate(alert=alert, event=event, debounce=debounce)


async def assert_surveillance_repository_contract(
    repository: SurveillanceRepository,
    *,
    tenant_id: str,
    project_id: str,
    portrait_identity_ids: tuple[str, str] | None = None,
    source_id: str = "src_contract",
    camera_id: str = "camera-contract",
) -> None:
    """跑完整套契约；任一后端不满足即抛 AssertionError。

    PostgreSQL 侧的名单成员、任务绑定分别以外键指向 scenara_portrait_identities、
    scenara_media_sources 与 scenara_trajectory_cameras，调用方需要传入已登记的
    人像身份、媒体来源和点位；内存实现不做这些约束，缺省值即可运行。
    """

    fixture = _Fixture(tenant_id, project_id, portrait_identity_ids, source_id, camera_id)
    now = time.time()

    watchlist = await repository.create_watchlist(
        Watchlist(
            watchlist_id=fixture.watchlist_id,
            tenant_id=tenant_id,
            project_id=project_id,
            name="契约名单",
            category=WatchlistCategory.BLACKLIST,
            created_by="contract",
            created_at=now,
            updated_at=now,
        )
    )
    fetched = await repository.get_watchlist(tenant_id, project_id, fixture.watchlist_id)
    assert fetched is not None
    assert fetched.name == "契约名单"
    assert fetched.category == WatchlistCategory.BLACKLIST
    listed, total = await repository.list_watchlists(tenant_id, project_id, offset=0, limit=10)
    assert total >= 1
    assert fixture.watchlist_id in {item.watchlist_id for item in listed}

    # 乐观锁按 revision 递增，陈旧写入必须被拒绝。
    renamed = await repository.save_watchlist(
        watchlist.model_copy(update={"name": "契约名单改"}),
        expected_revision=watchlist.revision,
    )
    assert renamed.revision == watchlist.revision + 1
    try:
        await repository.save_watchlist(
            watchlist.model_copy(update={"name": "冲突写入"}),
            expected_revision=watchlist.revision,
        )
    except Exception:
        pass
    else:  # pragma: no cover - 后端未实现乐观锁即失败
        raise AssertionError("stale watchlist revision must be rejected")

    # 成员有效期决定它是否参与匹配。
    await repository.create_member(
        WatchlistMember(
            member_id=fixture.member_id,
            tenant_id=tenant_id,
            project_id=project_id,
            watchlist_id=fixture.watchlist_id,
            portrait_identity_id=fixture.identity_id,
            valid_from=now,
            valid_until=now + 3_600,
            created_by="contract",
            created_at=now,
            updated_at=now,
        )
    )
    inside = await repository.list_active_members(
        tenant_id, project_id, [fixture.watchlist_id], at=now + 60
    )
    assert [item.member_id for item in inside] == [fixture.member_id]
    before = await repository.list_active_members(
        tenant_id, project_id, [fixture.watchlist_id], at=now - 60
    )
    assert before == []
    expired = await repository.list_active_members(
        tenant_id, project_id, [fixture.watchlist_id], at=now + 7_200
    )
    assert expired == []

    # 暂停的成员即使在有效期内也不参与匹配。
    paused_member_id = f"{fixture.member_id}-paused"
    await repository.create_member(
        WatchlistMember(
            member_id=paused_member_id,
            tenant_id=tenant_id,
            project_id=project_id,
            watchlist_id=fixture.watchlist_id,
            portrait_identity_id=fixture.paused_identity_id,
            status=WatchlistMemberStatus.PAUSED,
            created_by="contract",
            created_at=now,
            updated_at=now,
        )
    )
    active_only = await repository.list_active_members(
        tenant_id, project_id, [fixture.watchlist_id], at=now + 60
    )
    assert [item.member_id for item in active_only] == [fixture.member_id]

    # 归档名单的状态要能落库并读回，供上层决定是否继续布控。
    archived = await repository.save_watchlist(
        renamed.model_copy(update={"status": WatchlistStatus.ARCHIVED}),
        expected_revision=renamed.revision,
    )
    assert archived.status == WatchlistStatus.ARCHIVED
    await repository.save_watchlist(
        archived.model_copy(update={"status": WatchlistStatus.ACTIVE}),
        expected_revision=archived.revision,
    )

    task = await repository.create_task(
        SurveillanceTask(
            task_id=fixture.task_id,
            tenant_id=tenant_id,
            project_id=project_id,
            name="契约布控",
            status=SurveillanceTaskStatus.DRAFT,
            watchlist_ids=[fixture.watchlist_id],
            bindings=[
                TaskBinding(
                    binding_id=fixture.binding_id,
                    source_id=fixture.source_id,
                    camera_id=fixture.camera_id,
                )
            ],
            threshold_policy=ThresholdPolicy(
                policy_version="contract-v1", face_threshold=0.8, body_threshold=None
            ),
            match_policy=MatchPolicy.ALERT_ON_MATCH,
            cooldown_seconds=30,
            created_by="contract",
            created_at=now,
            updated_at=now,
        )
    )
    stored_task = await repository.get_task(tenant_id, project_id, fixture.task_id)
    assert stored_task is not None
    assert stored_task.bindings[0].binding_id == fixture.binding_id
    assert stored_task.threshold_policy.face_threshold == 0.8

    # 草稿任务不得进入调度面，激活后才可见。
    assert await repository.list_active_tasks_for_source(tenant_id, project_id, fixture.source_id) == []
    activated = await repository.save_task(
        task.model_copy(update={"status": SurveillanceTaskStatus.ACTIVE}),
        expected_revision=task.revision,
    )
    assert activated.status == SurveillanceTaskStatus.ACTIVE
    scheduled = await repository.list_active_tasks_for_source(tenant_id, project_id, fixture.source_id)
    assert [item.task_id for item in scheduled] == [fixture.task_id]
    assert fixture.task_id in {item.task_id for item in await repository.list_all_active_tasks()}

    # 首次命中产生告警与事件。
    first = await repository.record_alert(fixture.alert(triggered_at=now, score=0.80, window=0))
    assert first.emitted is True
    assert first.event is not None
    assert first.alert.occurrence_count == 1

    # 冷却窗口内的重复命中折叠进同一条告警，只累计次数与峰值分数。
    folded = await repository.record_alert(fixture.alert(triggered_at=now + 5, score=0.91, window=0))
    assert folded.emitted is False
    assert folded.event is None
    assert folded.alert.alert_id == first.alert.alert_id
    assert folded.alert.occurrence_count == 2
    assert folded.alert.max_score == 0.91
    assert folded.alert.last_seen_at == now + 5

    # 冷却窗口结束后重新触发，冷却期不因持续命中而顺延。
    reopened = await repository.record_alert(fixture.alert(triggered_at=now + 100, score=0.70, window=1))
    assert reopened.emitted is True
    assert reopened.alert.alert_id != first.alert.alert_id

    # 幂等键相同的重放即便已过冷却也不得产生第二条告警。
    replay = await repository.record_alert(fixture.alert(triggered_at=now + 200, score=0.60, window=1))
    assert replay.emitted is False
    assert replay.alert.alert_id == reopened.alert.alert_id

    # 列表过滤按状态、点位与时间窗收敛。
    pending, pending_total = await repository.list_alerts(
        tenant_id,
        project_id,
        status=AlertStatus.PENDING,
        task_id=fixture.task_id,
        camera_id=fixture.camera_id,
        watchlist_id=fixture.watchlist_id,
        portrait_identity_id=fixture.identity_id,
        since=None,
        until=None,
        offset=0,
        limit=10,
    )
    assert pending_total == 2
    assert {item.alert_id for item in pending} == {first.alert.alert_id, reopened.alert.alert_id}
    _, other_camera = await repository.list_alerts(
        tenant_id,
        project_id,
        status=None,
        task_id=None,
        camera_id="camera-absent",
        watchlist_id=None,
        portrait_identity_id=None,
        since=None,
        until=None,
        offset=0,
        limit=10,
    )
    assert other_camera == 0

    # 人工处置改写状态并追加一条事件。
    triaged_at = now + 300
    confirmed = reopened.alert.model_copy(
        update={
            "status": AlertStatus.CONFIRMED,
            "triaged_by": "contract-reviewer",
            "triaged_at": triaged_at,
            "triage_reason": "命中确认",
            "updated_at": triaged_at,
        }
    )
    triage_event = AlertEvent(
        event_id=f"alevt_{uuid4().hex}",
        event_type="alert.triaged",
        occurred_at=_rfc3339(triaged_at),
        tenant_id=tenant_id,
        project_id=project_id,
        alert_id=confirmed.alert_id,
        task_id=fixture.task_id,
        camera_id=fixture.camera_id,
        portrait_identity_id=fixture.identity_id,
        match_score=confirmed.match_score,
        modality=AlertModality.FACE,
        deduplication_key=confirmed.idempotency_key,
        status=AlertStatus.CONFIRMED,
        created_at=triaged_at,
    )
    outcome = await repository.triage_alert(
        confirmed, triage_event, expected_revision=reopened.alert.revision
    )
    assert outcome.emitted is True
    assert outcome.alert.status == AlertStatus.CONFIRMED
    assert outcome.alert.revision == reopened.alert.revision + 1
    try:
        await repository.triage_alert(
            confirmed, triage_event, expected_revision=reopened.alert.revision
        )
    except Exception:
        pass
    else:  # pragma: no cover - 后端未实现乐观锁即失败
        raise AssertionError("stale alert revision must be rejected")

    # 事件游标单调递增，且可从任意位置续读。
    events = await repository.events_after(tenant_id, project_id, 0, limit=50)
    cursors = [item.event_cursor for item in events]
    assert cursors == sorted(cursors)
    assert len(set(cursors)) == len(cursors)
    types = [item.event_type for item in events]
    assert types.count("alert.triggered") == 2
    assert types.count("alert.triaged") == 1
    resumed = await repository.events_after(tenant_id, project_id, cursors[0], limit=50)
    assert [item.event_cursor for item in resumed] == cursors[1:]


__all__ = ["assert_surveillance_repository_contract"]
