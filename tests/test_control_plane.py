from dataclasses import replace

import httpx
import pytest

from scenara.bootstrap import build_runtime
from scenara.platform.models import Membership, PrincipalType, Role, UserAccount
from scenara.server import create_app


@pytest.fixture
async def control_plane_client(development_settings):
    runtime = build_runtime(development_settings)
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        yield api


@pytest.mark.asyncio
async def test_control_plane_data_search_flow_and_agent(control_plane_client: httpx.AsyncClient) -> None:
    api = control_plane_client
    task = await api.post(
        "/api/v1/data/annotation-tasks",
        json={"asset_ids": ["asset_1"], "schema_name": "portrait.v1"},
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["data"]["record_id"]
    reviewed = await api.post(
        f"/api/v1/data/annotation-tasks/{task_id}/review",
        json={"approved": True, "consistency_score": 0.96},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["status"] == "approved"

    profile = await api.post(
        "/api/v1/search/ranking-profiles",
        json={"name": "默认混合排序", "exact_weight": 0.7, "vector_weight": 0.3},
    )
    assert profile.status_code == 201
    evaluation = await api.post(
        "/api/v1/search/evaluations",
        json={"query": "合同", "expected_record_ids": ["r1", "r2"], "result_record_ids": ["r2", "r3"]},
    )
    assert evaluation.status_code == 201
    assert evaluation.json()["data"]["precision"] == 0.5
    assert evaluation.json()["data"]["recall"] == 0.5

    flow = await api.post(
        "/api/v1/flows",
        json={
            "name": "解析审核",
            "version": "1.0.0",
            "entry_node_id": "review",
            "nodes": [{"node_id": "review", "kind": "approval"}],
        },
    )
    assert flow.status_code == 201, flow.text
    execution = await api.post(
        f"/api/v1/flows/{flow.json()['data']['record_id']}/execute",
        json={"context": {"run_id": "run_1"}},
    )
    assert execution.status_code == 202
    execution_id = execution.json()["data"]["record_id"]
    approvals = await api.get(f"/api/v1/flows/{flow.json()['data']['record_id']}/executions/{execution_id}/approvals")
    assert approvals.status_code == 200
    approval_id = approvals.json()["data"][0]["record_id"]
    decided = await api.post(f"/api/v1/flows/approvals/{approval_id}/decide", json={"approved": True})
    assert decided.status_code == 200

    tool = await api.post(
        "/api/v1/agents/tools",
        json={"name": "search", "description": "执行受控检索", "scopes": ["search:read"]},
    )
    assert tool.status_code == 201
    action = await api.post(
        "/api/v1/agents/actions",
        json={"tool_id": tool.json()["data"]["record_id"], "input": {"query": "合同"}},
    )
    assert action.status_code == 202
    approved = await api.post(
        f"/api/v1/agents/actions/{action.json()['data']['record_id']}/decide",
        json={"approved": True, "comment": "已审核"},
    )
    assert approved.status_code == 200
    executed = await api.post(f"/api/v1/agents/actions/{action.json()['data']['record_id']}/execute")
    assert executed.status_code == 200
    assert executed.json()["data"]["status"] == "executed"


@pytest.mark.asyncio
async def test_control_plane_edge_workers_and_quota(control_plane_client: httpx.AsyncClient) -> None:
    api = control_plane_client
    quota = await api.post(
        "/api/v1/platform/quotas/plans",
        json={"name": "标准", "limits": {"runs": 2}, "window_seconds": 3600},
    )
    assert quota.status_code == 201
    assert (await api.post("/api/v1/platform/quotas/check", json={"metric": "runs"})).json()["data"]["allowed"]
    assert (await api.post("/api/v1/platform/quotas/check", json={"metric": "runs", "amount": 2})).json()["data"][
        "allowed"
    ] is False

    device = await api.post("/api/v1/edge/devices", json={"name": "门岗-01", "capabilities": ["portrait"]})
    assert device.status_code == 201
    device_id = device.json()["data"]["record_id"]
    heartbeat = await api.post(f"/api/v1/edge/devices/{device_id}/heartbeat", json={"status": "online"})
    assert heartbeat.status_code == 200
    sync = await api.post(
        f"/api/v1/edge/devices/{device_id}/sync",
        params={"object_ref": "result/r1", "sha256": "a" * 64},
    )
    assert sync.status_code == 202
    ack = await api.post(f"/api/v1/edge/sync/{sync.json()['data']['record_id']}/acknowledge", json={})
    assert ack.status_code == 200
    worker = await api.post("/api/v1/platform/workers", json={"worker_id": "worker-1", "lane": "realtime"})
    assert worker.status_code == 201
    beat = await api.post("/api/v1/platform/workers/worker-1/heartbeat", json={})
    assert beat.status_code == 200


@pytest.mark.asyncio
async def test_interactive_session_is_usable_as_a_bearer_credential(development_settings) -> None:
    settings = replace(development_settings, auth_required=True, api_token="root-secret")
    runtime = build_runtime(settings)
    await runtime.access.repository.create_user(
        UserAccount(
            tenant_id=settings.default_tenant_id,
            user_id="user-1",
            display_name="User One",
            created_at=1.0,
            updated_at=1.0,
        )
    )
    await runtime.access.repository.create_role(
        Role(
            tenant_id=settings.default_tenant_id,
            role_id="viewer",
            display_name="Viewer",
            scopes=frozenset({"iam:read"}),
            product_ids=frozenset({"console"}),
            created_at=1.0,
            updated_at=1.0,
        )
    )
    await runtime.access.repository.create_membership(
        Membership(
            tenant_id=settings.default_tenant_id,
            project_id=settings.default_project_id,
            principal_id="user-1",
            principal_type=PrincipalType.USER,
            role_ids=frozenset({"viewer"}),
            created_at=1.0,
            updated_at=1.0,
        )
    )
    app = create_app(runtime=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        session = await api.post(
            "/api/v1/platform/sessions",
            headers={"Authorization": "Bearer root-secret"},
            json={"user_id": "user-1", "ttl_seconds": 3600},
        )
        assert session.status_code == 201, session.text
        token = session.json()["data"]["token"]
        identity_providers = await api.get(
            "/api/v1/platform/identity-providers", headers={"Authorization": f"Bearer {token}"}
        )
        assert identity_providers.status_code == 200, identity_providers.text
        assert identity_providers.json()["data"] == []


@pytest.mark.asyncio
async def test_flow_runner_and_index_rebuild_are_durable(control_plane_client: httpx.AsyncClient) -> None:
    api = control_plane_client
    index = await api.post(
        "/api/v1/indexes",
        json={"index_id": "result.test", "domain": "test", "record_kind": "text"},
    )
    assert index.status_code == 201, index.text
    rebuilt = await api.post("/api/v1/indexes/rebuild", json={"index_id": "result.test"})
    assert rebuilt.status_code == 202, rebuilt.text
    assert rebuilt.json()["data"]["status"] == "completed"
    assert rebuilt.json()["data"]["records_seen"] == 0

    flow = await api.post(
        "/api/v1/flows",
        json={
            "name": "runner",
            "version": "1.0.0",
            "entry_node_id": "set_flag",
            "nodes": [
                {"node_id": "set_flag", "kind": "run", "config": {"output": {"ready": True}}, "next_nodes": ["review"]},
                {"node_id": "review", "kind": "approval", "next_nodes": ["finish"]},
                {"node_id": "finish", "kind": "webhook", "config": {"target": "internal"}},
            ],
        },
    )
    assert flow.status_code == 201, flow.text
    flow_id = flow.json()["data"]["record_id"]
    execution = await api.post(f"/api/v1/flows/{flow_id}/execute", json={})
    assert execution.status_code == 202
    assert execution.json()["data"]["status"] == "waiting_approval"
    approval = (await api.get(f"/api/v1/flows/{flow_id}/executions/{execution.json()['data']['record_id']}/approvals"))
    approval_id = approval.json()["data"][0]["record_id"]
    decided = await api.post(f"/api/v1/flows/approvals/{approval_id}/decide", json={"approved": True})
    assert decided.status_code == 200


@pytest.mark.asyncio
async def test_control_plane_lifecycle_audit_billing_and_provider_contracts(
    control_plane_client: httpx.AsyncClient,
) -> None:
    api = control_plane_client

    lifecycle = await api.post(
        "/api/v1/platform/projects/lifecycle-requests",
        json={"project_id": "default", "action": "disable", "reason": "maintenance"},
    )
    assert lifecycle.status_code == 202, lifecycle.text
    request_id = lifecycle.json()["data"]["record_id"]
    decision = await api.post(
        f"/api/v1/platform/projects/lifecycle-requests/{request_id}/decide",
        json={"approved": True, "comment": "approved"},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["data"]["status"] == "approved"
    lifecycle_state = await api.post(
        "/api/v1/platform/lifecycle/project/default/restore", params={"reason": "test cleanup"}
    )
    assert lifecycle_state.status_code == 200
    assert lifecycle_state.json()["data"]["status"] == "active"
    other_project = await api.post(
        "/api/v1/platform/projects/lifecycle-requests",
        json={"project_id": "project-2", "action": "disable", "reason": "capacity change"},
    )
    assert other_project.status_code == 202
    other_request_id = other_project.json()["data"]["record_id"]
    other_decision = await api.post(
        f"/api/v1/platform/projects/lifecycle-requests/{other_request_id}/decide",
        json={"approved": True},
    )
    assert other_decision.status_code == 200
    assert (await api.get("/api/v1/platform/projects/lifecycle-requests")).json()["data"]

    retention = await api.put("/api/v1/platform/audit/retention", json={"retention_days": 30})
    assert retention.status_code == 200, retention.text
    assert retention.json()["data"]["retention_days"] == 30
    purge = await api.post(
        "/api/v1/platform/audit/purge",
        json={"dry_run": True, "reason": "scheduled retention check"},
    )
    assert purge.status_code == 200, purge.text
    assert purge.json()["data"]["dry_run"] is True

    account = await api.post(
        "/api/v1/platform/billing/accounts",
        json={"plan_id": "team", "currency": "USD", "seat_limit": 1},
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["data"]["record_id"]
    meter = {
        "account_id": account_id,
        "metric": "runs",
        "amount": 3,
        "idempotency_key": "meter-runs-0001",
    }
    first_meter = await api.post("/api/v1/platform/billing/meter-events", json=meter)
    second_meter = await api.post("/api/v1/platform/billing/meter-events", json=meter)
    assert first_meter.status_code == second_meter.status_code == 201
    assert first_meter.json()["data"]["record_id"] == second_meter.json()["data"]["record_id"]
    conflicting_meter = await api.post(
        "/api/v1/platform/billing/meter-events",
        json={**meter, "amount": 4},
    )
    assert conflicting_meter.status_code == 400
    usage = await api.get("/api/v1/platform/billing/usage", params={"account_id": account_id})
    assert usage.status_code == 200
    assert usage.json()["data"][0]["amount"] == 3
    seat = await api.post(
        "/api/v1/platform/billing/seats", json={"account_id": account_id, "user_id": "operator-1"}
    )
    assert seat.status_code == 201, seat.text
    over_limit = await api.post(
        "/api/v1/platform/billing/seats", json={"account_id": account_id, "user_id": "operator-2"}
    )
    assert over_limit.status_code == 400

    annotation_provider = await api.post(
        "/api/v1/data/annotation-providers",
        json={"name": "local-labeler", "kind": "http", "endpoint": "http://localhost:9001"},
    )
    assert annotation_provider.status_code == 201, annotation_provider.text
    provider_id = annotation_provider.json()["data"]["record_id"]
    probed = await api.post(f"/api/v1/data/annotation-providers/{provider_id}/probe")
    assert probed.status_code == 200
    assert probed.json()["data"]["last_health"] == "configured"

    index_backend = await api.post(
        "/api/v1/search/index-backends",
        json={"name": "pgvector", "kind": "postgres", "endpoint": "postgresql://db", "capabilities": ["vector"]},
    )
    assert index_backend.status_code == 201, index_backend.text
    reranker = await api.post(
        "/api/v1/search/rerankers",
        json={"name": "deterministic-reranker", "kind": "local", "endpoint": "http://localhost:9002"},
    )
    assert reranker.status_code == 201, reranker.text
    assert (await api.get("/api/v1/search/index-backends")).json()["data"]
    assert (await api.get("/api/v1/search/rerankers")).json()["data"]

    trace = await api.post(
        "/api/v1/agents/traces",
        json={"trace_type": "tool.call", "payload": {"tool": "search", "latency_ms": 4}},
    )
    assert trace.status_code == 201, trace.text
    evaluation = await api.post(
        "/api/v1/agents/evaluations",
        json={"suite_name": "smoke", "sample_count": 10, "success_rate": 0.9},
    )
    assert evaluation.status_code == 201, evaluation.text
    memory = await api.put(
        "/api/v1/agents/memory",
        json={"namespace": "assistant", "key": "last_query", "value": {"query": "portrait"}},
    )
    assert memory.status_code == 200, memory.text
    fetched = await api.get("/api/v1/agents/memory", params={"namespace": "assistant", "key": "last_query"})
    assert fetched.status_code == 200
    assert fetched.json()["data"]["value"]["query"] == "portrait"


@pytest.mark.asyncio
async def test_external_adapter_registration_and_probe_contracts(control_plane_client: httpx.AsyncClient) -> None:
    api = control_plane_client
    identity = await api.post(
        "/api/v1/platform/identity-providers",
        json={
            "kind": "oidc",
            "display_name": "local oidc",
            "issuer_url": "https://id.example.test",
            "client_id": "scenara-console",
        },
    )
    assert identity.status_code == 201, identity.text
    identity_id = identity.json()["data"]["record_id"]
    identity_probe = await api.post(f"/api/v1/platform/identity-providers/{identity_id}/probe")
    assert identity_probe.status_code == 200
    assert identity_probe.json()["data"]["last_health"] == "configured"

    backend = await api.post(
        "/api/v1/search/index-backends",
        json={"name": "ann", "kind": "pgvector", "endpoint": "postgresql://db", "capabilities": ["ann"]},
    )
    backend_probe = await api.post(
        f"/api/v1/search/index-backends/{backend.json()['data']['record_id']}/probe"
    )
    assert backend_probe.status_code == 200
    assert backend_probe.json()["data"]["health"] == "configured"

    reranker = await api.post(
        "/api/v1/search/rerankers",
        json={"name": "semantic", "kind": "http", "endpoint": "https://reranker.example.test"},
    )
    reranker_probe = await api.post(
        f"/api/v1/search/rerankers/{reranker.json()['data']['record_id']}/probe"
    )
    assert reranker_probe.status_code == 200
    assert reranker_probe.json()["data"]["health"] == "configured"
