"""Secrets resolution — Azure Key Vault first, env-var fallback.

Why this exists: bank deployments on Azure want JWT signing keys,
API tokens, and DB credentials in Microsoft Key Vault rather than
in environment variables / Kubernetes Secrets. Local dev still wants
plain env-var lookup.

This module provides a single resolution point so callers don't have
to know which backend is in play. The resolver checks Key Vault when
`AZURE_KEY_VAULT_NAME` is set; otherwise it's behaviorally identical
to `os.environ.get()`.

Usage:
    from aml_framework.secrets import SECRETS
    jwt_secret = SECRETS.get("JWT_SECRET", default="dev-insecure")

Migration: existing `os.environ.get()` calls for SECRETS should swap
to `SECRETS.get()`. Calls for non-secret config (URLs, role claims,
flags) can stay on `os.environ` — they don't belong in a vault.

Auth: when Key Vault is configured, the module uses
`azure.identity.DefaultAzureCredential`, which picks up workload
identity inside AKS, then falls back to azure-cli login, env vars,
and managed identity in that order. No static credentials in code.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("aml.secrets")


class SecretsProvider:
    """Resolve a secret name to a value, Key-Vault-first.

    Caches the underlying Azure SDK client lazily — the first call
    that hits Key Vault constructs `SecretClient`; subsequent calls
    reuse it. Failures from Key Vault are logged and treated as
    "secret not found", so the env-var fallback runs.

    Construct with `vault_name=` to override the env var (mostly
    useful in tests).
    """

    def __init__(self, vault_name: str | None = None) -> None:
        self._vault_name = vault_name or os.environ.get("AZURE_KEY_VAULT_NAME") or ""
        self._client: Any | None = None
        self._client_failed = False  # avoid retry storm on bad config

    @property
    def vault_enabled(self) -> bool:
        return bool(self._vault_name)

    def _client_or_none(self) -> Any | None:
        """Lazy SecretClient. Returns None when Key Vault isn't
        configured or the SDK isn't installed (azure extras)."""
        if not self.vault_enabled or self._client_failed:
            return None
        if self._client is not None:
            return self._client
        try:  # pragma: no cover — needs azure-keyvault-secrets installed
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            credential = DefaultAzureCredential()
            url = f"https://{self._vault_name}.vault.azure.net"
            self._client = SecretClient(vault_url=url, credential=credential)
            return self._client
        except Exception as exc:
            logger.warning(
                "Key Vault SecretClient init failed (%s); falling back to env vars",
                exc,
            )
            self._client_failed = True
            return None

    def get(self, name: str, default: str | None = None) -> str | None:
        """Resolve `name` from Key Vault if configured, else env var.

        Key Vault secret naming: dots and underscores in `name` are
        translated to dashes per Key Vault's allowed-character rule.
        Example: `JWT_SECRET` → secret named `JWT-SECRET`.

        Returns `default` when neither source has the value.
        """
        client = self._client_or_none()
        if client is not None:  # pragma: no cover — needs live Key Vault
            kv_name = name.replace("_", "-").replace(".", "-")
            try:
                secret = client.get_secret(kv_name)
                if secret.value is not None:
                    return secret.value
            except Exception as exc:
                logger.debug(
                    "Key Vault lookup of %s failed (%s); falling back to env var",
                    kv_name,
                    exc,
                )
        return os.environ.get(name, default)


# Module-level singleton. Importers do
#   from aml_framework.secrets import SECRETS
# rather than constructing their own — avoids re-init costs on a
# hot path (every API request goes through auth.py which goes
# through here).
SECRETS = SecretsProvider()
