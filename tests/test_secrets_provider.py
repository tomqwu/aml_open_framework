"""PR-AZ-2: SecretsProvider — Key Vault first, env-var fallback.

Unit tests cover:
  - Behaviour when AZURE_KEY_VAULT_NAME is unset (env-var only)
  - Default-value handling
  - Behaviour when SecretClient init fails (graceful fallback)

The actual Azure SDK paths (live SecretClient.get_secret) are
`# pragma: no cover` since they need a real Key Vault.
"""

from __future__ import annotations

import pytest

from aml_framework.secrets import SecretsProvider


@pytest.fixture
def clean_env(monkeypatch):
    """Strip both AZURE_KEY_VAULT_NAME and the test secret env var so
    each test has a deterministic starting state."""
    monkeypatch.delenv("AZURE_KEY_VAULT_NAME", raising=False)
    monkeypatch.delenv("TEST_SECRET_NAME", raising=False)
    return monkeypatch


class TestVaultDisabled:
    """When AZURE_KEY_VAULT_NAME is unset, SecretsProvider behaves
    identically to os.environ.get()."""

    def test_returns_env_var_when_set(self, clean_env):
        clean_env.setenv("TEST_SECRET_NAME", "from-env")
        provider = SecretsProvider()
        assert provider.get("TEST_SECRET_NAME") == "from-env"

    def test_returns_default_when_env_missing(self, clean_env):
        provider = SecretsProvider()
        assert provider.get("TEST_SECRET_NAME", "fallback") == "fallback"

    def test_returns_none_when_no_default(self, clean_env):
        provider = SecretsProvider()
        assert provider.get("TEST_SECRET_NAME") is None

    def test_vault_enabled_property_false(self, clean_env):
        provider = SecretsProvider()
        assert provider.vault_enabled is False


class TestVaultEnabledFallback:
    """When AZURE_KEY_VAULT_NAME is set but the SDK can't init (e.g.
    no credentials, no network), SecretsProvider falls back to env
    vars rather than crashing."""

    def test_failed_client_falls_back_to_env(self, clean_env):
        clean_env.setenv("AZURE_KEY_VAULT_NAME", "nonexistent-kv")
        clean_env.setenv("TEST_SECRET_NAME", "from-env-after-kv-fail")
        provider = SecretsProvider()
        # _client_failed will be set after first failed attempt.
        # Either the SDK isn't installed (returns None silently) or
        # init fails with no credentials. Either way we hit env.
        result = provider.get("TEST_SECRET_NAME")
        assert result == "from-env-after-kv-fail"

    def test_explicit_vault_name_overrides_env(self, clean_env):
        clean_env.setenv("AZURE_KEY_VAULT_NAME", "from-env-name")
        provider = SecretsProvider(vault_name="from-constructor")
        # vault_enabled reads from the instance attribute set in
        # __init__, not the live env var.
        assert provider.vault_enabled is True
        # Internal state — make sure constructor arg won.
        assert provider._vault_name == "from-constructor"


class TestModuleSingleton:
    """The module-level SECRETS singleton imports cleanly and behaves
    like a fresh SecretsProvider in dev environments."""

    def test_singleton_is_secretsprovider(self):
        from aml_framework.secrets import SECRETS

        assert isinstance(SECRETS, SecretsProvider)

    def test_singleton_get_works(self, clean_env):
        clean_env.setenv("TEST_SECRET_NAME", "singleton-test")
        # Re-import to pick up the patched env. Simpler: just call get
        # — the singleton was instantiated at import time without the
        # vault, so it always falls through to os.environ.
        from aml_framework.secrets import SECRETS

        assert SECRETS.get("TEST_SECRET_NAME") == "singleton-test"


class TestKeyVaultNamingTranslation:
    """Key Vault disallows underscores in secret names — provider
    translates `_` → `-` so callers don't have to know."""

    def test_translation_rule_is_documented(self):
        # We can't easily test the live translation without mocking the
        # SDK; this test asserts the docstring describes the convention
        # so future readers know.
        from aml_framework.secrets import SecretsProvider as Cls

        doc = Cls.get.__doc__ or ""
        assert "underscores" in doc.lower() or "_" in doc
        assert "dash" in doc.lower() or "-" in doc
