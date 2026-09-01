from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.server import create_app
from scenara.domains.portrait.service import (
    CreateIdentityRequest,
    EnrollIdentityRequest,
)
from scenara.domains.portrait.trajectory import RegisterCameraRequest
from scenara.platform.features import DistanceMetric
from scenara.platform.models import MediaSource, PrincipalContext
from scenara.platform.models import WebhookSubscription
from scenara.platform.surveillance import (
    AlertStatus,
    CreateSurveillanceTaskRequest,
    CreateWatchlistMemberRequest,
    CreateWatchlistRequest,
    ObservationBatch,
    ObservationEvidence,
    SurveillanceTaskStatus,
    TaskBinding,
    ThresholdPolicy,
    TriageAlertRequest,
    SurveillanceSchedule,
)


CONTEXT = PrincipalContext(
    tenant_id="default", project_id="default", principal_id="surveillance-test"
)


def test_schedule_accepts_fixed_offset_defaults_without_tzdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scenara.platform import surveillance as surveillance_module

    class MissingTzdata:
        def __init__(self, _: str) -> None:
            raise surveillance_module.ZoneInfoNotFoundError("tzdata unavailable")

    monkeypatch.setattr(surveillance_module, "ZoneInfo", MissingTzdata)
    schedule = SurveillanceSchedule(timezone="GMT")
    assert schedule.timezone == "UTC"
    assert schedule.is_active(1_700_000_000)


async def _runtime(development_settings):
    runtime = build_runtime(replace(development_settings, queue_backend="inline"))
    await runtime.open()
    return runtime


async def _prepared_task(runtime):
    identity = await runtime.portrait.create_identity(
        CONTEXT, CreateIdentityRequest(display_name="目标人员")
    )
    await runtime.portrait.enroll(
        CONTEXT,
        identity.identity_id,
        EnrollIdentityRequest(
            feature_space_id="portrait.face.test.v1",
            modality="face",
            model_id="face-test",
            model_version="1.0.0",
            distance_metric=DistanceMetric.COSINE,
            threshold=0.8,
            embedding=[1.0, 0.0, 0.0],
            quality=0.95,
        ),
    )
    source = MediaSource(
        source_id="src_surveillance",
        tenant_id=CONTEXT.tenant_id,
        project_id=CONTEXT.project_id,
        name="测试视频源",
        masked_url="rtsp://***",
        secret_ref="secret://tests/surveillance-source",
        created_at=1.0,
    )
    await runtime.state.create_source(source)
    await runtime.trajectory.register_camera(
        CONTEXT,
        RegisterCameraRequest(camera_id="camera-surveillance", display_name="测试点位"),
    )
    watchlist = await runtime.surveillance.create_watchlist(
        CONTEXT, CreateWatchlistRequest(name="测试名单", category="blacklist")
    )
    member = await runtime.surveillance.create_member(
        CONTEXT,
        watchlist.watchlist_id,
        CreateWatchlistMemberRequest(
            portrait_identity_id=identity.identity_id, display_label="目标人员"
        ),
    )
    task = await runtime.surveillance.create_task(
        CONTEXT,
        CreateSurveillanceTaskRequest(
            name="测试布控",
            watchlist_ids=[watchlist.watchlist_id],
            bindings=[
                TaskBinding(
                    binding_id="bind-surveillance",
                    source_id=source.source_id,
                    camera_id="camera-surveillance",
                )
            ],
            threshold_policy=ThresholdPolicy(
                policy_version="test-v1", face_threshold=0.8, body_threshold=None
            ),
            cooldown_seconds=30,
        ),
    )
    task = await runtime.surveillance._repository.save_task(
        task.model_copy(update={"status": SurveillanceTaskStatus.ACTIVE}),
        expected_revision=task.revision,
    )
    return identity, watchlist, member, task


@pytest.mark.asyncio
async def test_watchlist_reuses_portrait_identity_and_alert_debounce(
    development_settings,
) -> None:
    runtime = await _runtime(development_settings)
    try:
        identity, watchlist, member, task = await _prepared_task(runtime)
        await runtime.state.create_webhook_subscription(
            WebhookSubscription(
                endpoint_id="whk_surveillance",
                tenant_id=CONTEXT.tenant_id,
                project_id=CONTEXT.project_id,
                name="告警订阅",
                url="https://example.com/alerts",
                secret_ref="secret://tests/surveillance-webhook",
                event_types=frozenset({"alert.triggered"}),
                created_at=1.0,
            )
        )
        binding = task.bindings[0]
        observation = ObservationBatch(
            run_id="run_surveillance",
            source_id="src_surveillance",
            camera_id="camera-surveillance",
            unit_id="unit_0",
            track_id="track_1",
            first_seen_at=1_000.0,
            last_seen_at=1_001.0,
            timestamp_source="recording",
            evidence=[
                ObservationEvidence(
                    modality="face",
                    embedding=[0.99, 0.01, 0.0],
                    quality=0.99,
                    model_id="face-test",
                    model_version="1.0.0",
                )
            ],
        )
        await runtime.surveillance._evaluate_observation(
            CONTEXT, task, binding, observation
        )
        await runtime.surveillance._evaluate_observation(
            CONTEXT, task, binding, observation
        )
        page = await runtime.surveillance.list_alerts(
            CONTEXT,
            status=None,
            task_id=task.task_id,
            camera_id=None,
            watchlist_id=watchlist.watchlist_id,
            portrait_identity_id=identity.identity_id,
            since=None,
            until=None,
            offset=0,
            limit=10,
        )
        assert page.total == 1
        assert page.items[0].member_id == member.member_id
        assert page.items[0].occurrence_count == 2
        assert page.items[0].status == AlertStatus.PENDING
        events = await runtime.surveillance.events_after(CONTEXT, 0)
        assert [event.event_type for event in events] == ["alert.triggered"]
        assert "embedding" not in events[0].model_dump_json()
        deliveries = await runtime.state.list_webhook_deliveries(
            CONTEXT.tenant_id, CONTEXT.project_id, 10
        )
        assert [(item.event_type, item.event_id) for item in deliveries] == [
            ("alert.triggered", events[0].event_id)
        ]
        assert "embedding" not in deliveries[0].model_dump_json()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_alert_triage_is_revision_protected_and_replayed(
    development_settings,
) -> None:
    runtime = await _runtime(development_settings)
    try:
        _identity, _watchlist, _member, task = await _prepared_task(runtime)
        await runtime.surveillance._evaluate_observation(
            CONTEXT,
            task,
            task.bindings[0],
            ObservationBatch(
                run_id="run_triage",
                source_id="src_surveillance",
                camera_id="camera-surveillance",
                first_seen_at=2_000.0,
                last_seen_at=2_001.0,
                timestamp_source="recording",
                evidence=[
                    ObservationEvidence(
                        modality="face",
                        embedding=[1.0, 0.0, 0.0],
                        quality=1.0,
                        model_id="face-test",
                        model_version="1.0.0",
                    )
                ],
            ),
        )
        alert = (
            await runtime.surveillance.list_alerts(
                CONTEXT,
                status=None,
                task_id=None,
                camera_id=None,
                watchlist_id=None,
                portrait_identity_id=None,
                since=None,
                until=None,
                offset=0,
                limit=10,
            )
        ).items[0]
        triaged = await runtime.surveillance.triage_alert(
            CONTEXT,
            alert.alert_id,
            TriageAlertRequest(
                expected_revision=alert.revision,
                status="false_positive",
                reason="人工核验不一致",
            ),
        )
        assert triaged.status == AlertStatus.FALSE_POSITIVE
        assert triaged.triaged_by == CONTEXT.principal_id
        with pytest.raises(Exception, match="triaged|revision"):
            await runtime.surveillance.triage_alert(
                CONTEXT,
                alert.alert_id,
                TriageAlertRequest(
                    expected_revision=alert.revision,
                    status="ignored",
                    reason="重复操作",
                ),
            )
        events = await runtime.surveillance.events_after(CONTEXT, 0)
        assert [event.event_type for event in events] == [
            "alert.triggered",
            "alert.triaged",
        ]
        assert events[-1].status == AlertStatus.FALSE_POSITIVE
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_surveillance_watchlist_api_uses_standard_envelopes(
    development_settings,
) -> None:
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        created = await api.post(
            "/api/v1/surveillance/watchlists",
            json={"name": "接口名单", "category": "custom", "description": "测试"},
        )
        assert created.status_code == 201, created.text
        payload = created.json()["data"]
        assert payload["name"] == "接口名单"
        assert payload["revision"] == 1
        page = await api.get("/api/v1/surveillance/watchlists?offset=0&limit=10")
        assert page.status_code == 200
        assert page.json()["data"]["total"] == 1
        updated = await api.patch(
            f"/api/v1/surveillance/watchlists/{payload['watchlist_id']}",
            json={"expected_revision": 1, "status": "paused"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["revision"] == 2
        stale = await api.patch(
            f"/api/v1/surveillance/watchlists/{payload['watchlist_id']}",
            json={"expected_revision": 1, "status": "active"},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "SURVEILLANCE_CONFLICT"
