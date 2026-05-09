"""Startup announces the active persistence backend.

The API and dashboard each log one INFO line at startup so ops can
confirm the right backend is wired without exec'ing into the
container. This pins the contract.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

try:
    from aml_framework.api import main as api_main

    HAS_FASTAPI = True
except ImportError:  # pragma: no cover -- depends on env
    HAS_FASTAPI = False

# Probe streamlit availability without importing — other tests assert
# `"streamlit" not in sys.modules` at fixture-setup time, and a top-level
# `import streamlit` here would pollute sys.modules for the whole suite.
HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None


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
def _restore_sys_modules():
    """Importing the dashboard app pulls in streamlit; other test files
    assert streamlit isn't in sys.modules. Snapshot + restore the keys
    we touch so cross-file ordering doesn't matter."""
    snapshot = {
        k: sys.modules[k]
        for k in list(sys.modules)
        if k == "streamlit" or k.startswith("streamlit.") or k.startswith("aml_framework.dashboard")
    }
    pre_keys = set(sys.modules)
    yield
    for k in list(sys.modules):
        if k not in pre_keys and (
            k == "streamlit"
            or k.startswith("streamlit.")
            or k.startswith("aml_framework.dashboard")
        ):
            del sys.modules[k]
    for k, v in snapshot.items():
        sys.modules[k] = v


@pytest.mark.skipif(not HAS_STREAMLIT, reason="streamlit not installed")
@pytest.mark.usefixtures("_restore_sys_modules")
class TestDashboardStartupLogsBackend:
    """Mirror of the API contract for the dashboard pod. The dashboard
    emits the same `Persistence backend: %s` line at module import to
    the `aml.dashboard` logger so ops can confirm the right backend is
    wired without exec'ing into the streamlit container.
    """

    @staticmethod
    def _reload_dashboard_app(caplog, monkeypatch):
        caplog.set_level(logging.INFO, logger="aml.dashboard")
        # initialize_session() at app.py:42 parses sys.argv for the spec
        # path; under pytest sys.argv carries flags like -v that break
        # int(seed) parsing. Empty argv routes through the multi-tenant
        # fallback path which doesn't fail outside a streamlit runtime.
        monkeypatch.setattr(sys, "argv", ["streamlit"])
        # The log line fires at module-import time, so force a fresh
        # import. Drop both the dashboard module and its initialize_session
        # dep so the side effects re-run under the active patches.
        for mod in (
            "aml_framework.dashboard.app",
            "aml_framework.dashboard.state",
        ):
            sys.modules.pop(mod, None)
        try:
            importlib.import_module("aml_framework.dashboard.app")
        except Exception:
            # Streamlit-runtime side effects (st.session_state access,
            # st.markdown, etc.) raise outside `streamlit run`. The log
            # emit at app.py:40 runs first and is what we're asserting,
            # so swallow downstream import errors.
            pass

    def test_emits_sqlite_in_clean_env(self, caplog, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        from aml_framework.api import db

        with (
            patch.object(db, "_use_postgres", return_value=False),
            patch.object(db, "_use_cosmos", return_value=False),
        ):
            self._reload_dashboard_app(caplog, monkeypatch)

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.dashboard"]
        assert any("Persistence backend: sqlite" in m for m in msgs), msgs

    def test_emits_postgres_when_both_flags_set(self, caplog, monkeypatch):
        """Mirrors the precedence pinned in test_db_precedence.py."""
        from aml_framework.api import db

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=True),
        ):
            self._reload_dashboard_app(caplog, monkeypatch)

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.dashboard"]
        assert any("Persistence backend: postgres" in m for m in msgs), msgs


@pytest.fixture
def anyio_backend():
    return "asyncio"
