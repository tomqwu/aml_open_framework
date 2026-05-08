"""Startup announces the active persistence backend.

The API and dashboard each log one INFO line at startup so ops can
confirm the right backend is wired without exec'ing into the
container. This pins the contract.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

try:
    from aml_framework.api import main as api_main

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover -- depends on env
    HAS_FASTAPI = False


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestApiLifespanLogsBackend:
    async def _drive_lifespan(self, caplog):
        caplog.set_level(logging.INFO, logger="aml.api")
        # init_db() is patched out so the log line is the only side effect.
        with patch.object(api_main, "init_db"):
            async with api_main.lifespan(MagicMock()):
                pass

    @pytest.mark.anyio
    async def test_emits_sqlite_in_clean_env(self, caplog, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        # The module-level constants are read once at import; patch the
        # helpers the active-backend resolver delegates to.
        from aml_framework.api import db

        with (
            patch.object(db, "_use_postgres", return_value=False),
            patch.object(db, "_use_cosmos", return_value=False),
        ):
            await self._drive_lifespan(caplog)

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.api"]
        assert any("Persistence backend: sqlite" in m for m in msgs), msgs

    @pytest.mark.anyio
    async def test_emits_postgres_when_database_url_set(self, caplog):
        from aml_framework.api import db

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=False),
        ):
            await self._drive_lifespan(caplog)

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.api"]
        assert any("Persistence backend: postgres" in m for m in msgs), msgs

    @pytest.mark.anyio
    async def test_emits_postgres_when_both_flags_set(self, caplog):
        """Mirrors the precedence pinned in test_db_precedence.py."""
        from aml_framework.api import db

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=True),
        ):
            await self._drive_lifespan(caplog)

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.api"]
        assert any("Persistence backend: postgres" in m for m in msgs), msgs


@pytest.fixture
def anyio_backend():
    return "asyncio"
