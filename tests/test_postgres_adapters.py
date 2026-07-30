from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from scenara.infrastructure.postgres_features import _vector
from scenara.infrastructure.postgres_state import PostgresStateStore, _register_pgvector


class _Pool:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


def test_postgres_pool_registers_pgvector_on_each_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    psycopg_pool = ModuleType("psycopg_pool")
    psycopg_pool.AsyncConnectionPool = _Pool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg_pool", psycopg_pool)

    store = PostgresStateStore("postgresql://test")

    assert store.pool.kwargs["configure"] is _register_pgvector


@pytest.mark.asyncio
async def test_pgvector_connection_registration_uses_async_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    async def register(connection: object) -> None:
        calls.append(connection)

    package = ModuleType("pgvector")
    package.__path__ = []  # type: ignore[attr-defined]
    psycopg = ModuleType("pgvector.psycopg")
    psycopg.register_vector_async = register  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pgvector", package)
    monkeypatch.setitem(sys.modules, "pgvector.psycopg", psycopg)
    connection = object()

    await _register_pgvector(connection)

    assert calls == [connection]


def test_postgres_feature_binding_uses_pgvector_type(monkeypatch: pytest.MonkeyPatch) -> None:
    package = ModuleType("pgvector")
    package.Vector = tuple  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pgvector", package)

    assert _vector([1.0, 2.0]) == (1.0, 2.0)
