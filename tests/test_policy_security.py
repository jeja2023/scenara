from __future__ import annotations

import hashlib
import time

import pytest

from scenara.platform.audit import AuditLogger
from scenara.platform.control_plane import (
    ControlPlaneService,
    InteractiveSession,
    MemoryControlPlaneStore,
)
from scenara.platform.models import PrincipalContext
from scenara.platform.policy import DevelopmentPolicyProvider, PolicyDenied, require_allowed


@pytest.mark.asyncio
async def test_empty_scope_context_is_denied_even_with_development_provider() -> None:
    context = PrincipalContext(
        tenant_id="tenant-a",
        project_id="project-a",
        scopes=frozenset(),
        product_ids=frozenset({"console"}),
    )
    with pytest.raises(PolicyDenied, match="scope denied"):
        await require_allowed(DevelopmentPolicyProvider(), context, "read", "operations")


@pytest.mark.asyncio
async def test_session_lookup_is_indexed_and_expired_sessions_are_purged() -> None:
    store = MemoryControlPlaneStore()
    audit = AuditLogger(store)  # type: ignore[arg-type]
    service = ControlPlaneService(store, DevelopmentPolicyProvider(), audit)
    now = time.time()
    token = "session-token"
    record = InteractiveSession(
        session_id="ses_1",
        tenant_id="tenant-a",
        project_id="project-a",
        user_id="user-a",
        token_prefix=token[:8],
        token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        scopes=frozenset({"iam:read"}),
        product_ids=frozenset({"console"}),
        created_at=now,
        expires_at=now + 3600,
    )
    await service._save("session", record)
    context = await service.authenticate_session(token)
    assert context is not None
    assert context.principal_id == "user-a"

    expired = record.model_copy(
        update={"session_id": "ses_2", "expires_at": now - 1, "token_sha256": "b" * 64}
    )
    await service._save("session", expired)
    assert await service.purge_expired_sessions(now) == 1
    assert await store.get("session", "tenant-a", "project-a", "ses_2") is None
