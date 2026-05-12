"""Purview lineage connector tests.

All HTTP IO is patched via `_post_to_purview`; the bearer-token mint
is patched via the `_bearer_token` symbol on the module. No live
Azure required.
"""

from __future__ import annotations

import json
import sys
from unittest import mock

import pytest

from aml_framework.integrations import purview


def _sample_chain() -> dict:
    return {
        "case_id": "case-abc",
        "rule_id": "structuring_cash",
        "rule_version": "v3",
        "spec_content_hash": "deadbeef",
        "queue": "l1_aml_analyst",
        "rule_sql": "SELECT * FROM txn WHERE amount > 9000",
        "input_files": [
            {"path": "data/txn.csv", "sha256": "abc123"},
            {"path": "data/customer.csv", "sha256": "def456"},
        ],
    }


class TestEnabledByDefaultOff:
    def test_no_endpoint_is_noop(self, monkeypatch):
        monkeypatch.delenv("PURVIEW_ENDPOINT", raising=False)
        with mock.patch.object(purview, "_post_to_purview") as posted:
            purview.push_lineage(_sample_chain(), spec_name="canadian_schedule_i_bank")
        posted.assert_not_called()


class TestBuildEntities:
    """Direct unit tests on the entity-builder — no env, no network."""

    def test_emits_process_with_inputs_and_outputs(self, monkeypatch):
        monkeypatch.setenv("AML_DEPLOYMENT_ID", "prod-rev-001")
        entities = purview._build_entities(_sample_chain(), "canadian_schedule_i_bank")
        # 2 DataSet (sources) + 1 Process + 1 DataSet (case) = 4
        assert len(entities) == 4
        process = next(e for e in entities if e["typeName"] == "Process")
        assert process["attributes"]["qualifiedName"].endswith("/rule/structuring_cash")
        assert process["attributes"]["name"] == "rule:structuring_cash"
        # ruleVersion + specContentHash go under customAttributes since
        # Atlas's built-in `Process` type doesn't declare them.
        assert process["customAttributes"]["ruleVersion"] == "v3"
        assert process["customAttributes"]["specContentHash"] == "deadbeef"
        # Inputs reference the two source DataSets.
        assert len(process["attributes"]["inputs"]) == 2
        # Output references the case DataSet.
        assert len(process["attributes"]["outputs"]) == 1
        assert (
            "case-abc" in process["attributes"]["outputs"][0]["uniqueAttributes"]["qualifiedName"]
        )

    def test_qualified_names_namespace_by_deployment_id(self, monkeypatch):
        """UAT vs prod in the same tenant must not collide on identical
        spec/rule/case triples. The `aml://<deployment_id>/<spec>/...`
        scheme guarantees that — verified by building the same chain
        with two different deployment ids and asserting NO overlap."""
        monkeypatch.setenv("AML_DEPLOYMENT_ID", "prod-rev-001")
        prod = purview._build_entities(_sample_chain(), "canadian_schedule_i_bank")
        monkeypatch.setenv("AML_DEPLOYMENT_ID", "uat-rev-001")
        uat = purview._build_entities(_sample_chain(), "canadian_schedule_i_bank")
        prod_names = {e["attributes"]["qualifiedName"] for e in prod}
        uat_names = {e["attributes"]["qualifiedName"] for e in uat}
        assert prod_names.isdisjoint(uat_names), (
            f"qualifiedName collision between deployments: {prod_names & uat_names}"
        )

    def test_qualified_name_is_stable_across_pushes(self, monkeypatch):
        """Same chain pushed twice from the same deployment produces
        identical qualifiedNames so Purview updates rather than
        duplicates."""
        monkeypatch.setenv("AML_DEPLOYMENT_ID", "prod-rev-001")
        e1 = purview._build_entities(_sample_chain(), "canadian_schedule_i_bank")
        e2 = purview._build_entities(_sample_chain(), "canadian_schedule_i_bank")
        names1 = sorted(e["attributes"]["qualifiedName"] for e in e1)
        names2 = sorted(e["attributes"]["qualifiedName"] for e in e2)
        assert names1 == names2

    def test_chain_without_rule_id_short_circuits(self):
        """Sparse chains (old runs predating Round 12) shouldn't crash;
        return empty so the push is a no-op."""
        entities = purview._build_entities({"case_id": "case-x"}, "canadian_schedule_i_bank")
        assert entities == []

    def test_chain_without_input_files_still_builds_process(self):
        """Process + case entities should emit even when source list
        is empty — partial lineage is better than no lineage."""
        chain = {"case_id": "case-x", "rule_id": "r1", "input_files": []}
        entities = purview._build_entities(chain, "demo")
        assert any(e["typeName"] == "Process" for e in entities)
        # No DataSets for sources.
        sources = [
            e
            for e in entities
            if e["typeName"] == "DataSet" and e["attributes"]["qualifiedName"].endswith("/source/")
        ]
        assert sources == []

    def test_qualified_name_url_escapes_path_segments(self):
        """Source paths containing `/` (the common case) must not
        fragment the qualifiedName — the parts get URL-escaped so the
        full path becomes one segment. Otherwise two different files
        in two subdirs could end up with the same qualifiedName tail."""
        chain = {
            "case_id": "case-x",
            "rule_id": "r1",
            "input_files": [{"path": "data/input/txn.csv"}],
        }
        entities = purview._build_entities(chain, "demo")
        source = next(
            e
            for e in entities
            if e["typeName"] == "DataSet" and "source" in e["attributes"]["qualifiedName"]
        )
        # `/` characters in the path get URL-escaped to `%2F`.
        assert "data%2Finput%2Ftxn.csv" in source["attributes"]["qualifiedName"]


class TestCheckMutationResult:
    """Atlas bulk returns HTTP 200 even on partial failure. The
    `failedEntities` map carries the per-entity errors. `_check_mutation_result`
    must raise PurviewError when that map is non-empty so partial
    failures aren't silently swallowed."""

    def test_no_failures_returns_silently(self):
        purview._check_mutation_result({"failedEntities": {}})  # no raise
        purview._check_mutation_result({})  # missing key, ok

    def test_failed_entities_raise_with_per_entity_detail(self):
        payload = {
            "failedEntities": {
                "guid-1": {
                    "typeName": "Process",
                    "qualifiedName": "aml://prod/spec1/rule/r1",
                    "errorMessage": "qualifiedName already exists with different type",
                },
                "guid-2": {
                    "typeName": "DataSet",
                    "errorMessage": "required attribute missing",
                },
            }
        }
        with pytest.raises(purview.PurviewError, match="2 failed entities") as exc_info:
            purview._check_mutation_result(payload)
        # First failure's detail should be in the message.
        assert "aml://prod/spec1/rule/r1" in str(exc_info.value)
        assert "qualifiedName already exists" in str(exc_info.value)


class TestPushLineageHTTP:
    def test_push_uses_bearer_token_and_atlas_endpoint(self, monkeypatch):
        monkeypatch.setenv("PURVIEW_ENDPOINT", "https://my-purview.purview.azure.com")

        captured: dict = {}

        def fake_post(endpoint, token, body, timeout=30.0):
            captured["endpoint"] = endpoint
            captured["token"] = token
            captured["body"] = body

        with (
            mock.patch.object(purview, "_bearer_token", return_value="fake-token"),
            mock.patch.object(purview, "_post_to_purview", side_effect=fake_post),
        ):
            purview.push_lineage(_sample_chain(), spec_name="canadian_schedule_i_bank")

        assert captured["endpoint"] == "https://my-purview.purview.azure.com"
        assert captured["token"] == "fake-token"
        payload = json.loads(captured["body"])
        assert "entities" in payload
        # Process + case + 2 sources = 4 entities.
        assert len(payload["entities"]) == 4

    def test_actionable_error_when_credential_unavailable(self, monkeypatch):
        """When DefaultAzureCredential fails, `_bearer_token` raises
        `PurviewError` with an actionable message naming the fix."""
        monkeypatch.setenv("PURVIEW_ENDPOINT", "https://my-purview.purview.azure.com")

        class _FakeCred:
            def get_token(self, _scope):
                raise RuntimeError("no creds")

        fake_module = type(sys)("azure.identity")
        fake_module.DefaultAzureCredential = _FakeCred  # type: ignore[attr-defined]
        with mock.patch.dict(sys.modules, {"azure.identity": fake_module}):
            with pytest.raises(purview.PurviewError, match="Purview Data Curator"):
                purview._bearer_token()
