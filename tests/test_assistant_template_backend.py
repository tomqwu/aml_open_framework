"""Behaviour tests for the GenAI Assistant's template backend (PR-K).

The template backend is the default — it must work without any
optional deps, return a valid `AssistantReply`, and never make a
network call. These tests pin those invariants.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from aml_framework.assistant import (
    Assistant,
    AssistantContext,
    AssistantError,
    AssistantReply,
    TemplateBackend,
    get_assistant,
)
from aml_framework.assistant.models import reply_to_audit_dict


class TestTemplateBackendBasics:
    def test_factory_returns_template_by_default(self):
        backend = get_assistant()
        assert isinstance(backend, Assistant)
        assert backend.name.startswith("template")

    def test_factory_explicit_template(self):
        backend = get_assistant("template")
        assert isinstance(backend, TemplateBackend)
        assert backend.name == "template:v1"

    def test_reply_is_valid_AssistantReply(self):
        backend = TemplateBackend()
        ctx = AssistantContext(
            page="Executive Dashboard",
            persona="cco",
            spec_name="Test Bank",
            rule_count=12,
            metric_count=8,
        )
        reply = backend.reply("why is alert volume high?", ctx)
        assert isinstance(reply, AssistantReply)
        assert reply.text  # non-empty
        assert reply.backend == "template:v1"
        assert reply.prompted_with_page == "Executive Dashboard"
        assert reply.prompted_with_persona == "cco"
        assert reply.confidence in {"high", "medium", "low"}

    def test_reply_echoes_question_back(self):
        backend = TemplateBackend()
        ctx = AssistantContext(page="Run History")
        reply = backend.reply("how do I tune this rule?", ctx)
        # The template backend acknowledges the question so the operator
        # sees the panel is reaching them. This is part of the canned
        # scaffolding contract — replies aren't useful but they are present.
        assert (
            "how do I tune this rule" in reply.text.lower()
            or "how do i tune this rule" in reply.text.lower()
        )

    def test_reply_picks_up_deep_link_focus(self):
        backend = TemplateBackend()
        ctx = AssistantContext(
            page="Case Investigation",
            selected_case_id="CASE-2026-04-001",
        )
        reply = backend.reply("draft me an STR", ctx)
        assert "CASE-2026-04-001" in reply.referenced_case_ids
        # Focused-on-case line surfaces in the body too.
        assert "CASE-2026-04-001" in reply.text

    def test_focus_line_covers_other_deep_link_entities(self):
        assert "customer: `C-1`" in TemplateBackend._focus_line(
            AssistantContext(page="Customer 360", selected_customer_id="C-1")
        )
        assert "rule: `R-1`" in TemplateBackend._focus_line(
            AssistantContext(page="Rules", selected_rule_id="R-1")
        )
        assert "metric: `M-1`" in TemplateBackend._focus_line(
            AssistantContext(page="Metrics", selected_metric_id="M-1")
        )
        assert TemplateBackend._focus_line(AssistantContext(page="Executive Dashboard")) == ""


class TestAuditDict:
    def test_hash_only_mode_omits_full_text(self):
        backend = TemplateBackend(_now=datetime(2026, 4, 30, tzinfo=timezone.utc))
        ctx = AssistantContext(page="Risk Assessment", persona="cco")
        reply = backend.reply("how risky is this portfolio?", ctx)
        row = reply_to_audit_dict(reply, full_text=False)
        assert "reply_text" not in row
        assert "reply_text_hash" in row
        assert len(row["reply_text_hash"]) == 64  # sha-256 hex

    def test_full_text_mode_logs_complete_reply(self):
        backend = TemplateBackend(_now=datetime(2026, 4, 30, tzinfo=timezone.utc))
        ctx = AssistantContext(page="Risk Assessment", persona="cco")
        reply = backend.reply("explain to me", ctx)
        row = reply_to_audit_dict(reply, full_text=True)
        assert "reply_text" in row
        assert row["reply_text"] == reply.text
        assert "reply_text_hash" not in row

    def test_audit_dict_carries_provenance(self):
        backend = TemplateBackend(_now=datetime(2026, 4, 30, tzinfo=timezone.utc))
        ctx = AssistantContext(page="Audit & Evidence", persona="auditor")
        reply = backend.reply("when was this run finalised?", ctx)
        row = reply_to_audit_dict(reply, full_text=False)
        assert row["page"] == "Audit & Evidence"
        assert row["persona"] == "auditor"
        assert row["backend"] == "template:v1"
        assert row["confidence"] in {"high", "medium", "low"}
        assert isinstance(row["citations"], list)


class TestFactoryEnvLookup:
    def test_factory_reads_AML_AI_BACKEND_env(self, monkeypatch):
        monkeypatch.setenv("AML_AI_BACKEND", "template")
        backend = get_assistant()
        assert backend.name.startswith("template")

    def test_factory_unknown_backend_raises(self):
        try:
            get_assistant("not_a_real_backend")
        except AssistantError as e:
            assert "not_a_real_backend" in str(e)
        else:
            raise AssertionError("expected AssistantError")

    def test_factory_returns_ollama_backend(self):
        backend = get_assistant("ollama", model="llama3.1:8b")
        assert backend.name == "ollama:llama3.1:8b"

    def test_factory_openai_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(AssistantError, match="OPENAI_API_KEY"):
            get_assistant("openai")


class TestAssistantOllamaBackend:
    def test_happy_path_returns_validated_reply(self):
        from aml_framework.assistant.ollama import OllamaBackend

        # Ollama Cloud + local /api/chat both return responses under
        # `message.content` (per docs.ollama.com/cloud). The framework
        # uses the /api/chat path on both, so the fake mirrors that.
        fake_response = {
            "message": {
                "content": json.dumps(
                    {
                        "text": "Alert volume is concentrated in case CASE-1.",
                        "confidence": "high",
                        "referenced_metric_ids": ["metric-alert-volume"],
                        "referenced_case_ids": ["CASE-1"],
                        "referenced_customer_ids": ["C-1"],
                        "citations": [
                            {
                                "rule_id": "structuring_cash_deposits",
                                "citation": "PCMLTFA s.11.1",
                                "claim": "Structuring typology",
                            }
                        ],
                    }
                )
            }
        }
        ctx = AssistantContext(page="Executive Dashboard", persona="cco")
        with mock.patch("aml_framework.assistant.ollama._call_ollama", return_value=fake_response):
            reply = OllamaBackend(model="llama3.1:8b").reply("why is volume high?", ctx)

        assert reply.text.startswith("Alert volume")
        assert reply.backend == "ollama:llama3.1:8b"
        assert reply.confidence == "high"
        assert reply.referenced_metric_ids == ["metric-alert-volume"]
        assert reply.referenced_case_ids == ["CASE-1"]
        assert reply.referenced_customer_ids == ["C-1"]
        assert reply.citations[0].citation == "PCMLTFA s.11.1"

    def test_missing_optional_fields_get_defaults(self):
        from aml_framework.assistant.ollama import OllamaBackend

        fake = {
            "message": {"content": json.dumps({"text": "Short answer.", "confidence": "certain"})}
        }
        with mock.patch("aml_framework.assistant.ollama._call_ollama", return_value=fake):
            reply = OllamaBackend().reply("summarize", AssistantContext(page="Run History"))

        assert reply.text == "Short answer."
        assert reply.confidence == "low"
        assert reply.citations == []
        assert reply.referenced_metric_ids == []

    def test_invalid_citations_are_ignored(self):
        from aml_framework.assistant.ollama import _build_reply

        reply = _build_reply(
            {
                "text": "Answer",
                "citations": [
                    "not a citation",
                    {"rule_id": "r1", "citation": "ref", "claim": "claim"},
                    {"rule_id": 1, "citation": [], "claim": {}},
                ],
            },
            AssistantContext(page="Case Investigation", persona="analyst"),
            backend="test",
        )

        assert len(reply.citations) == 1
        assert reply.citations[0].rule_id == "r1"

    def test_unexpected_response_shape_raises(self):
        from aml_framework.assistant.ollama import OllamaBackend

        with (
            mock.patch("aml_framework.assistant.ollama._call_ollama", return_value={}),
            pytest.raises(AssistantError, match="response shape"),
        ):
            OllamaBackend().reply("hello", AssistantContext(page="Today"))

    def test_non_json_response_raises(self):
        from aml_framework.assistant.ollama import OllamaBackend

        with (
            mock.patch(
                "aml_framework.assistant.ollama._call_ollama",
                return_value={"message": {"content": "<html>oops</html>"}},
            ),
            pytest.raises(AssistantError, match="non-JSON"),
        ):
            OllamaBackend().reply("hello", AssistantContext(page="Today"))

    # ------------------------------------------------------------------
    # Ollama Cloud (Bearer auth) — wired in PR feat/ollama-cloud-bearer-auth
    # ------------------------------------------------------------------

    def test_sends_chat_payload_not_generate(self):
        """The backend must POST {"messages":[…]} to /api/chat, not
        the older flat {"prompt": "…"} /api/generate shape that the
        cloud endpoint no longer supports."""
        from aml_framework.assistant.ollama import OllamaBackend

        captured: dict[str, object] = {}

        def fake_call(url, model, prompt, *, api_key=None, timeout=60.0):
            captured["url"] = url
            captured["model"] = model
            captured["prompt"] = prompt
            return {"message": {"content": json.dumps({"text": "ok", "confidence": "high"})}}

        with mock.patch("aml_framework.assistant.ollama._call_ollama", side_effect=fake_call):
            OllamaBackend().reply("hi", AssistantContext(page="Today"))
        assert captured["url"].endswith("/api/chat"), captured["url"]

    def test_bearer_token_sent_when_api_key_set(self, monkeypatch):
        """When `OLLAMA_API_KEY` is set (or passed in), the HTTP layer
        must add `Authorization: Bearer …`. Patch the lower-level
        `urlopen` so we can inspect the actual headers."""
        from aml_framework.assistant.ollama import OllamaBackend, _call_ollama

        captured_headers: dict[str, str] = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps(
                    {"message": {"content": json.dumps({"text": "ok", "confidence": "high"})}}
                ).encode()

        def fake_urlopen(req, timeout=None):
            # Header keys come back capitalized — normalise.
            captured_headers.update({k.lower(): v for k, v in req.headers.items()})
            return _FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        _call_ollama("https://ollama.com/api/chat", "m", "p", api_key="fake-bearer")
        assert captured_headers.get("authorization") == "Bearer fake-bearer"

        # And via the high-level OllamaBackend with env var routing.
        captured_headers.clear()
        monkeypatch.setenv("AML_OLLAMA_URL", "https://ollama.com/api/chat")
        monkeypatch.setenv("OLLAMA_API_KEY", "env-key-abc")
        OllamaBackend().reply("hi", AssistantContext(page="Today"))
        assert captured_headers.get("authorization") == "Bearer env-key-abc"

    def test_local_url_no_key_omits_authorization(self, monkeypatch):
        """Local-daemon path is backward compatible: no key → no
        Authorization header sent. Don't accidentally leak any
        previously-set key when targeting localhost."""
        from aml_framework.assistant.ollama import _call_ollama

        captured_headers: dict[str, str] = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps(
                    {"message": {"content": json.dumps({"text": "ok", "confidence": "high"})}}
                ).encode()

        def fake_urlopen(req, timeout=None):
            captured_headers.update({k.lower(): v for k, v in req.headers.items()})
            return _FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        _call_ollama("http://localhost:11434/api/chat", "m", "p")
        assert "authorization" not in captured_headers

    def test_cloud_url_without_key_raises(self, monkeypatch):
        """Pointing at a non-localhost host with no key is almost
        certainly a misconfiguration. Fail fast at construction with
        an actionable message instead of letting the server return 401."""
        from aml_framework.assistant.ollama import OllamaBackend

        monkeypatch.setenv("AML_OLLAMA_URL", "https://ollama.com/api/chat")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        # Also clear vault state — SECRETS.get falls back to env.
        with pytest.raises(AssistantError, match="OLLAMA_API_KEY"):
            OllamaBackend()

    def test_local_url_no_key_constructs_ok(self, monkeypatch):
        """The guardrail above must NOT fire for a localhost URL."""
        from aml_framework.assistant.ollama import OllamaBackend

        monkeypatch.setenv("AML_OLLAMA_URL", "http://localhost:11434/api/chat")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        backend = OllamaBackend()
        assert backend.api_key == ""

    def test_is_local_host_recognises_loopback_variants(self):
        from aml_framework.assistant.ollama import _is_local_host

        assert _is_local_host("http://localhost:11434/api/chat")
        assert _is_local_host("http://127.0.0.1:11434/api/chat")
        assert _is_local_host("http://0.0.0.0:11434/api/chat")
        assert _is_local_host("http://[::1]:11434/api/chat")
        assert not _is_local_host("https://ollama.com/api/chat")
        assert not _is_local_host("https://anything-else.example.com/api/chat")

    def test_is_local_host_returns_false_on_malformed_url(self):
        """urlparse can raise ValueError on some pathological strings
        (e.g. a port that doesn't fit a uint16). The try/except
        treats those as 'not local' rather than crashing — so the
        Bearer-required guard still fires for misconfigured URLs."""
        from aml_framework.assistant.ollama import _is_local_host

        # Malformed IPv6 brackets — `urlparse(...).hostname` raises
        # ValueError. Helper must return False (i.e. treat as non-local
        # so the Bearer-required guard fires).
        assert not _is_local_host("http://[invalid:ipv6:url/")


class TestAssistantOpenAIBackend:
    def test_refuses_without_api_key(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(AssistantError, match="OPENAI_API_KEY"):
            OpenAIBackend()

    def test_constructor_arg_overrides_env(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        backend = OpenAIBackend(api_key="sk-test", model="gpt-test")
        assert backend.api_key == "sk-test"
        assert backend.name == "openai:gpt-test"

    def test_happy_path_with_mocked_call(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "text": "Use the case queue trend.",
                                "confidence": "medium",
                                "referenced_case_ids": ["CASE-9"],
                            }
                        )
                    }
                }
            ]
        }
        with mock.patch("aml_framework.assistant.openai._call_openai", return_value=fake_response):
            reply = OpenAIBackend(model="gpt-4o-mini").reply(
                "what should I inspect?", AssistantContext(page="Case Queue")
            )

        assert reply.backend == "openai:gpt-4o-mini"
        assert reply.confidence == "medium"
        assert reply.referenced_case_ids == ["CASE-9"]

    def test_unexpected_response_shape_raises(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with (
            mock.patch("aml_framework.assistant.openai._call_openai", return_value={"choices": []}),
            pytest.raises(AssistantError, match="response shape"),
        ):
            OpenAIBackend().reply("hello", AssistantContext(page="Today"))

    def test_non_json_response_raises(self, monkeypatch):
        from aml_framework.assistant.openai import OpenAIBackend

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with (
            mock.patch(
                "aml_framework.assistant.openai._call_openai",
                return_value={"choices": [{"message": {"content": "not json"}}]},
            ),
            pytest.raises(AssistantError, match="non-JSON"),
        ):
            OpenAIBackend().reply("hello", AssistantContext(page="Today"))


class TestAssistantAzureOpenAIBackend:
    """Round 18 PR 4 — Azure OpenAI backend for enterprise tenants
    with Azure commitments. Mirrors `TestAssistantOpenAIBackend`
    structurally so the Cloud-OpenAI ↔ Azure-OpenAI swap is just an
    env-var change for the operator."""

    def test_refuses_without_endpoint_and_deployment(self, monkeypatch):
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        with pytest.raises(AssistantError, match="AZURE_OPENAI_ENDPOINT"):
            AzureOpenAIBackend()

    def test_constructor_args_override_env(self, monkeypatch):
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o-mini-prod",
            api_key="aoai-key",
            api_version="2024-10-01-preview",
        )
        assert backend.deployment == "gpt-4o-mini-prod"
        assert backend.api_key == "aoai-key"
        assert backend.name == "azure_openai:gpt-4o-mini-prod"

    def test_url_composition_matches_azure_route(self):
        from aml_framework.assistant.azure_openai import _azure_openai_url

        url = _azure_openai_url(
            "https://my-aoai.openai.azure.com/",
            "gpt-4o-mini-prod",
            "2024-10-01-preview",
        )
        assert url == (
            "https://my-aoai.openai.azure.com/openai/deployments/"
            "gpt-4o-mini-prod/chat/completions?api-version=2024-10-01-preview"
        )

    def test_happy_path_with_mocked_call(self, monkeypatch):
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "text": "Inspect the case queue trend.",
                                "confidence": "high",
                                "referenced_case_ids": [],
                            }
                        )
                    }
                }
            ]
        }
        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o-prod",
            api_key="aoai-key",
        )
        with mock.patch(
            "aml_framework.assistant.azure_openai._call_azure_openai",
            return_value=fake_response,
        ):
            reply = backend.reply("what next?", AssistantContext(page="Today"))
        assert reply.backend == "azure_openai:gpt-4o-prod"
        assert reply.confidence == "high"

    def test_factory_routes_azure_openai(self, monkeypatch):
        """`get_assistant("azure_openai")` returns the new backend."""
        from aml_framework.assistant.factory import get_assistant

        monkeypatch.delenv("AML_AI_BACKEND", raising=False)
        backend = get_assistant(
            "azure_openai",
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o",
            api_key="aoai-key",
        )
        assert backend.name == "azure_openai:gpt-4o"

    def test_unexpected_response_shape_raises(self, monkeypatch):
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o",
            api_key="aoai-key",
        )
        with (
            mock.patch(
                "aml_framework.assistant.azure_openai._call_azure_openai",
                return_value={"choices": []},
            ),
            pytest.raises(AssistantError, match="response shape"),
        ):
            backend.reply("hi", AssistantContext(page="Today"))

    def test_bearer_token_path_passes_token_not_api_key(self, monkeypatch):
        """When no api_key is set, `reply()` mints an Entra-ID token
        via `_bearer_token()` and passes it through. Pin the auth
        plumbing so the production Azure-native path is exercised
        (the api-key path is the dev-friendly default but enterprise
        Azure shops use the bearer-token path)."""
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o-prod",
        )
        assert backend.api_key == ""  # no key → bearer-token branch
        # Stub the token-minting so no live azure-identity needed.
        backend._bearer_token = lambda: "fake-aad-token"  # type: ignore[method-assign]

        captured = {}

        def fake_call(url, *, api_key, bearer_token, prompt, timeout):
            captured["api_key"] = api_key
            captured["bearer_token"] = bearer_token
            return {
                "choices": [
                    {"message": {"content": json.dumps({"text": "ok", "confidence": "high"})}}
                ]
            }

        with mock.patch(
            "aml_framework.assistant.azure_openai._call_azure_openai", side_effect=fake_call
        ):
            backend.reply("hi", AssistantContext(page="Today"))
        assert captured["api_key"] is None
        assert captured["bearer_token"] == "fake-aad-token"

    def test_bearer_token_unmintable_raises_actionable_error(self, monkeypatch):
        """When DefaultAzureCredential can't resolve a token (no env
        creds, no UAMI, etc.), `_bearer_token` wraps the raw azure SDK
        exception in an `AssistantError` that names the two fixes:
        set the API key or attach a managed identity."""
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o",
        )

        # Fake an azure.identity module whose DefaultAzureCredential
        # always fails.
        class _FakeCred:
            def get_token(self, _scope):
                raise RuntimeError("no credential available")

        import sys

        fake_module = type(sys)("azure.identity")
        fake_module.DefaultAzureCredential = _FakeCred  # type: ignore[attr-defined]
        with mock.patch.dict(sys.modules, {"azure.identity": fake_module}):
            with pytest.raises(AssistantError, match="could not mint an Entra-ID token"):
                backend._bearer_token()

    def test_bearer_token_missing_azure_identity_raises(self, monkeypatch):
        """When `azure-identity` is not installed (i.e. the `[azure]`
        extras were skipped), the bearer-token path must raise an
        AssistantError that points the operator at either installing
        the extras or setting AZURE_OPENAI_API_KEY — not a bare
        ImportError."""
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o",
        )

        import builtins

        real_import = builtins.__import__

        def _raise_for_azure_identity(name, *args, **kwargs):
            if name == "azure.identity":
                raise ImportError("simulated missing azure-identity")
            return real_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", side_effect=_raise_for_azure_identity):
            with pytest.raises(AssistantError, match=r"`azure-identity`"):
                backend._bearer_token()

    def test_non_json_response_raises(self, monkeypatch):
        """Azure OpenAI is asked for `response_format=json_object`; if
        the model returns prose instead, we wrap the JSONDecodeError
        with an actionable message."""
        from aml_framework.assistant.azure_openai import AzureOpenAIBackend

        backend = AzureOpenAIBackend(
            endpoint="https://my-aoai.openai.azure.com/",
            deployment="gpt-4o",
            api_key="aoai-key",
        )
        fake_response = {"choices": [{"message": {"content": "this is not JSON at all"}}]}
        with (
            mock.patch(
                "aml_framework.assistant.azure_openai._call_azure_openai",
                return_value=fake_response,
            ),
            pytest.raises(AssistantError, match="non-JSON despite response_format"),
        ):
            backend.reply("hi", AssistantContext(page="Today"))
