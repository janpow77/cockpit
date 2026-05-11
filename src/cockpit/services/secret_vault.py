"""Secret-Vault: Fernet-basierte Symmetric-Verschluesselung at-rest.

Key-Quelle: Env ``COCKPIT_VAULT_KEY`` (32-byte url-safe-base64).
Wenn nicht gesetzt: alle Encrypt/Decrypt-Aufrufe werfen ``VaultDisabledError``,
die Routes liefern dann einen 503 mit klarer Fehlermeldung.

Key generieren:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)


class VaultDisabledError(RuntimeError):
    """Wird geworfen, wenn der Vault-Key fehlt."""


class VaultDecryptError(RuntimeError):
    """Wird geworfen, wenn ein Token nicht entschluesselt werden kann."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet | None:
    raw = os.environ.get("COCKPIT_VAULT_KEY", "").strip()
    if not raw:
        log.warning("COCKPIT_VAULT_KEY nicht gesetzt — Vault-Endpoints liefern 503.")
        return None
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        log.error("COCKPIT_VAULT_KEY ist ungueltig (%s) — Vault deaktiviert.", exc)
        return None


def is_enabled() -> bool:
    return _get_fernet() is not None


def encrypt(plaintext: str) -> str:
    f = _get_fernet()
    if f is None:
        raise VaultDisabledError("Vault ist nicht konfiguriert (COCKPIT_VAULT_KEY fehlt)")
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    f = _get_fernet()
    if f is None:
        raise VaultDisabledError("Vault ist nicht konfiguriert (COCKPIT_VAULT_KEY fehlt)")
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise VaultDecryptError("Token kann nicht entschluesselt werden (falscher Key?)") from exc


# Test-Helfer
def _reset_cache_for_tests() -> None:
    _get_fernet.cache_clear()
