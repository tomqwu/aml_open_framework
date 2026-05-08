"""Backend selection precedence in `aml_framework.api.db`.

Postgres should win when both `DATABASE_URL` and `COSMOS_ENDPOINT` are
set — see the docstring on `_active_backend()`. This test pins that
contract so the precedence can't silently flip again.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestActiveBackend:
    def test_postgres_wins_when_both_flags_set(self):
        import aml_framework.api.db as db

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=True),
        ):
            assert db._active_backend() == "postgres"

    def test_cosmos_when_only_cosmos_flag_set(self):
        import aml_framework.api.db as db

        with (
            patch.object(db, "_use_postgres", return_value=False),
            patch.object(db, "_use_cosmos", return_value=True),
        ):
            assert db._active_backend() == "cosmos"

    def test_postgres_when_only_postgres_flag_set(self):
        import aml_framework.api.db as db

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=False),
        ):
            assert db._active_backend() == "postgres"

    def test_sqlite_when_neither_flag_set(self):
        import aml_framework.api.db as db

        with (
            patch.object(db, "_use_postgres", return_value=False),
            patch.object(db, "_use_cosmos", return_value=False),
        ):
            assert db._active_backend() == "sqlite"


class TestInitDbRoutesToPostgresWhenBothFlagsSet:
    """End-to-end: init_db() must take the Postgres branch and never reach
    Cosmos when both env vars are set. Asserts the public function honors
    `_active_backend()`'s ordering, not just the helper itself.
    """

    def test_init_db_uses_postgres_not_cosmos(self):
        import aml_framework.api.db as db

        mock_pg_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pg_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_pg_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        cosmos_db_mock = MagicMock()

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_pg_conn),
            patch.object(db, "_get_cosmos_db", return_value=cosmos_db_mock),
        ):
            db.init_db()

        mock_cursor.execute.assert_called_once()
        mock_pg_conn.commit.assert_called_once()
        cosmos_db_mock.read.assert_not_called()
