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


class TestCrudFunctionsRouteToPostgresUnderDualConfig:
    """Every public CRUD function must take the SQL path (not Cosmos)
    when both DATABASE_URL and COSMOS_ENDPOINT are set. Asserts the
    `_active_backend() == "cosmos"` branch is never entered, so a
    Cosmos-to-Postgres migration is observable: writes go to Postgres
    and Cosmos is never touched.
    """

    @staticmethod
    def _patches(db_mod):
        """Force dual-config (postgres-first) and stub out the SQL +
        Cosmos backends so the function bodies run without I/O."""
        cosmos_db_mock = MagicMock()
        sql_cur = MagicMock()
        sql_cur.fetchall.return_value = []
        sql_cur.fetchone.return_value = None

        from contextlib import contextmanager as _cm

        @_cm
        def fake_with_conn():
            yield sql_cur

        return (
            cosmos_db_mock,
            sql_cur,
            [
                patch.object(db_mod, "_use_postgres", return_value=True),
                patch.object(db_mod, "_use_cosmos", return_value=True),
                patch.object(db_mod, "_get_cosmos_db", return_value=cosmos_db_mock),
                patch.object(db_mod, "_with_conn", fake_with_conn),
            ],
        )

    def _assert_no_cosmos(self, cosmos_db_mock):
        # _get_cosmos_db is called for the container handle, but no
        # methods like read_item/upsert_item/query_items should fire.
        cosmos_db_mock.get_container_client.assert_not_called()

    def test_store_run_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            db.store_run(
                run_id="r1",
                spec_path="x.yaml",
                seed=42,
                manifest={},
                alerts={},
                metrics=[],
            )
        self._assert_no_cosmos(cosmos_db_mock)

    def test_list_runs_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            assert db.list_runs() == []
        self._assert_no_cosmos(cosmos_db_mock)

    def test_get_run_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            assert db.get_run("r1") is None
        self._assert_no_cosmos(cosmos_db_mock)

    def test_get_run_alerts_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            assert db.get_run_alerts("r1") == []
        self._assert_no_cosmos(cosmos_db_mock)

    def test_get_run_metrics_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            assert db.get_run_metrics("r1") == []
        self._assert_no_cosmos(cosmos_db_mock)

    def test_store_spec_version_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            db.store_spec_version(
                spec_hash="h",
                spec_content="x: 1",
                program_name="prog",
            )
        self._assert_no_cosmos(cosmos_db_mock)

    def test_list_spec_versions_uses_sql_path(self):
        import aml_framework.api.db as db

        cosmos_db_mock, _, patches = self._patches(db)
        with patches[0], patches[1], patches[2], patches[3]:
            assert db.list_spec_versions() == []
        self._assert_no_cosmos(cosmos_db_mock)


class TestDualConfigEmitsWarningOnce:
    def test_warn_emitted_when_both_flags_set(self, caplog):
        import logging

        import aml_framework.api.db as db

        # Reset the one-time guard so the test exercises the emit path.
        db._dual_config_warned = False
        caplog.set_level(logging.WARNING, logger="aml.api.db")

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=True),
        ):
            db._active_backend()

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.api.db"]
        assert any("postgres-first precedence" in m for m in msgs)

    def test_warn_emitted_only_once(self, caplog):
        import logging

        import aml_framework.api.db as db

        db._dual_config_warned = False
        caplog.set_level(logging.WARNING, logger="aml.api.db")

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_use_cosmos", return_value=True),
        ):
            for _ in range(5):
                db._active_backend()

        msgs = [r.getMessage() for r in caplog.records if r.name == "aml.api.db"]
        warns = [m for m in msgs if "postgres-first precedence" in m]
        assert len(warns) == 1, f"expected exactly 1 warning, got {len(warns)}"


class TestStripAadMarker:
    """`_strip_aad_marker` must touch only the URL's query component
    (never userinfo / path / fragment) so a DSN where the literal
    string `authentication=azure_ad` happens to appear inside the
    password isn't false-stripped."""

    def test_marker_alone_in_query(self):
        from aml_framework.api.db import _strip_aad_marker

        dsn = "postgresql://uami@host:5432/db?authentication=azure_ad"
        cleaned, is_aad = _strip_aad_marker(dsn)
        assert is_aad is True
        assert cleaned == "postgresql://uami@host:5432/db"

    def test_marker_first_with_sslmode(self):
        from aml_framework.api.db import _strip_aad_marker

        dsn = "postgresql://uami@host:5432/db?authentication=azure_ad&sslmode=require"
        cleaned, is_aad = _strip_aad_marker(dsn)
        assert is_aad is True
        assert cleaned == "postgresql://uami@host:5432/db?sslmode=require"

    def test_marker_last_with_sslmode(self):
        from aml_framework.api.db import _strip_aad_marker

        dsn = "postgresql://uami@host:5432/db?sslmode=require&authentication=azure_ad"
        cleaned, is_aad = _strip_aad_marker(dsn)
        assert is_aad is True
        assert cleaned == "postgresql://uami@host:5432/db?sslmode=require"

    def test_no_marker_passthrough(self):
        from aml_framework.api.db import _strip_aad_marker

        dsn = "postgresql://user:pw@localhost:5432/aml"
        cleaned, is_aad = _strip_aad_marker(dsn)
        assert is_aad is False
        assert cleaned == dsn

    def test_marker_substring_in_password_not_stripped(self):
        """If the literal substring `authentication=azure_ad` appears
        in the userinfo (e.g. as part of an unusual password), it must
        NOT be stripped — only the actual query parameter is."""
        from aml_framework.api.db import _strip_aad_marker

        # Contrived password containing the literal marker substring.
        dsn = "postgresql://u:authentication=azure_ad@host:5432/db?sslmode=require"
        cleaned, is_aad = _strip_aad_marker(dsn)
        assert is_aad is False
        assert "authentication=azure_ad" in cleaned


class TestGetPgConnEntraIdAuth:
    """End-to-end behaviour of `_get_pg_conn`: detect AAD marker,
    fetch token via DefaultAzureCredential at the correct scope,
    pass it to psycopg2 as password."""

    def test_aad_marker_triggers_token_fetch(self):
        import sys

        import aml_framework.api.db as db

        psycopg2_mock = MagicMock()
        azure_identity_mock = MagicMock()
        cred_instance = MagicMock()
        cred_instance.get_token.return_value = MagicMock(token="fake-aad-token")
        azure_identity_mock.DefaultAzureCredential.return_value = cred_instance

        aad_dsn = (
            "postgresql://abc-uami@psql-aml-dev-foo.postgres.database.azure.com:5432/"
            "aml?sslmode=require&authentication=azure_ad"
        )
        with (
            patch.dict(
                sys.modules,
                {"psycopg2": psycopg2_mock, "azure.identity": azure_identity_mock},
            ),
            patch.object(db, "_DATABASE_URL", aad_dsn),
        ):
            db._get_pg_conn()

        # Scope literal must be the ossrdbms-aad one — wrong scope yields
        # tokens Postgres rejects.
        cred_instance.get_token.assert_called_once_with(
            "https://ossrdbms-aad.database.windows.net/.default"
        )
        # Exact cleaned DSN passed to psycopg2 — sslmode preserved, AAD
        # marker gone.
        called_args, called_kwargs = psycopg2_mock.connect.call_args
        assert called_args[0] == (
            "postgresql://abc-uami@psql-aml-dev-foo.postgres.database.azure.com:5432/"
            "aml?sslmode=require"
        )
        assert called_kwargs["password"] == "fake-aad-token"

    def test_plain_dsn_passes_through_unmodified(self):
        """Password-auth DSNs (e.g. local docker-compose Postgres) skip
        the token path and go through psycopg2.connect verbatim."""
        import sys

        import aml_framework.api.db as db

        psycopg2_mock = MagicMock()
        plain_dsn = "postgresql://user:pw@localhost:5432/aml"
        with (
            patch.dict(sys.modules, {"psycopg2": psycopg2_mock}),
            patch.object(db, "_DATABASE_URL", plain_dsn),
        ):
            db._get_pg_conn()

        psycopg2_mock.connect.assert_called_once_with(plain_dsn)
