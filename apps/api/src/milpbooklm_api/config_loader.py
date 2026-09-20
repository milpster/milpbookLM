"""
Startup configuration loader (ch04).

Reads the installation scope from the environment with ``_FILE`` secret
support, rejects unknown security-sensitive keys, and parses the user
preference and notebook policy scopes at the boundary into typed models.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pydantic import SecretStr

from milpbooklm_api.config import ConfigScopes, InstallationConfig, NotebookPolicy, UserPreferences

ENV_PREFIX = "MILPBOOKLM_"
FILE_SUFFIX = "_FILE"

# Closed set of known installation-scope keys (without the optional _FILE suffix).
# Any other MILPBOOKLM_* key is security-sensitive and rejected at startup.
INSTALLATION_ENV_KEYS = frozenset(
    {
        "MILPBOOKLM_DATABASE_URL",
        "MILPBOOKLM_SECRET_KEY",
        "MILPBOOKLM_BLOB_ROOT",
        "MILPBOOKLM_BASE_URL",
        "MILPBOOKLM_TRUSTED_PROXY_PEERS",
        # FND-07: credential keyring path (no _FILE suffix - the path IS a value)
        # and the audit bounded-retention window in days.
        "MILPBOOKLM_KEYRING_PATH",
        "MILPBOOKLM_AUDIT_RETENTION_DAYS",
        "MILPBOOKLM_PREREQUISITES_PATH",
    }
)

# Keys without a default; a startup with any of them missing is invalid.
REQUIRED_INSTALLATION_ENV_KEYS = frozenset(
    {
        "MILPBOOKLM_DATABASE_URL",
        "MILPBOOKLM_SECRET_KEY",
        "MILPBOOKLM_BLOB_ROOT",
        "MILPBOOKLM_BASE_URL",
    }
)


class ConfigError(Exception):
    """Typed configuration failure; ``keys`` names the offending settings."""

    def __init__(self, message: str, keys: tuple[str, ...] = ()) -> None:
        """Carry the offending key names alongside the message."""
        super().__init__(message)
        self.keys = keys


def read_secret_file(path: str) -> str:
    """Read a ``_FILE`` secret: the file content minus one trailing newline."""
    candidate = Path(path)
    if not candidate.is_file():
        raise ConfigError(f"secret file not found: {candidate}", keys=(str(candidate),))
    content = candidate.read_text(encoding="utf-8")
    return content[:-1] if content.endswith("\n") else content


def resolve_file_secrets(env: Mapping[str, str]) -> dict[str, str]:
    """Resolve ``<KEY>_FILE`` entries: the base key takes the file's content."""
    resolved: dict[str, str] = {}
    for key, value in env.items():
        if not (key.startswith(ENV_PREFIX) and key.endswith(FILE_SUFFIX)):
            resolved[key] = value
            continue
        base = key[: -len(FILE_SUFFIX)]
        if base in env:
            raise ConfigError(
                f"ambiguous installation key {base}: both plain and _FILE values are set",
                keys=(base, key),
            )
        resolved[base] = read_secret_file(value)
    return resolved


def load_installation(env: Mapping[str, str]) -> InstallationConfig:
    """Load the installation scope; reject unknown security-sensitive keys."""
    resolved = resolve_file_secrets(env)
    unknown = sorted(
        key for key in resolved if key.startswith(ENV_PREFIX) and key not in INSTALLATION_ENV_KEYS
    )
    if unknown:
        raise ConfigError(
            "unknown security-sensitive configuration key(s) rejected: " + ", ".join(unknown),
            keys=tuple(unknown),
        )
    missing = sorted(key for key in REQUIRED_INSTALLATION_ENV_KEYS if key not in resolved)
    if missing:
        raise ConfigError(
            "missing required installation configuration key(s): " + ", ".join(missing),
            keys=tuple(missing),
        )
    peers_raw = resolved.get("MILPBOOKLM_TRUSTED_PROXY_PEERS", "")
    peers = tuple(peer.strip() for peer in peers_raw.split(",") if peer.strip())
    keyring_raw = resolved.get("MILPBOOKLM_KEYRING_PATH", "").strip()
    keyring = Path(keyring_raw) if keyring_raw else None
    retention = _parse_retention_days(resolved.get("MILPBOOKLM_AUDIT_RETENTION_DAYS", ""))
    return InstallationConfig(
        database_url=SecretStr(resolved["MILPBOOKLM_DATABASE_URL"]),
        secret_key=SecretStr(resolved["MILPBOOKLM_SECRET_KEY"]),
        blob_root=Path(resolved["MILPBOOKLM_BLOB_ROOT"]),
        base_url=resolved["MILPBOOKLM_BASE_URL"],
        trusted_proxy_peers=peers,
        master_keyring_file=keyring,
        audit_retention_days=retention,
        prerequisites_file=Path(
            resolved.get(
                "MILPBOOKLM_PREREQUISITES_PATH",
                "/run/milpbooklm/prerequisites.json",
            )
        ),
    )


def _parse_retention_days(raw: str) -> int:
    """Parse the audit bounded-retention window; a positive integer (days)."""
    value = raw.strip()
    if not value:
        return 365
    try:
        days = int(value)
    except ValueError as exc:
        raise ConfigError(
            "MILPBOOKLM_AUDIT_RETENTION_DAYS must be a positive integer",
            keys=("MILPBOOKLM_AUDIT_RETENTION_DAYS",),
        ) from exc
    if days <= 0:
        raise ConfigError(
            "MILPBOOKLM_AUDIT_RETENTION_DAYS must be a positive integer",
            keys=("MILPBOOKLM_AUDIT_RETENTION_DAYS",),
        )
    return days


def load_user_preferences(data: str | bytes | Mapping[str, object]) -> UserPreferences:
    """Parse the user preference scope from JSON text or a mapping at the boundary."""
    if isinstance(data, (str, bytes)):
        return UserPreferences.model_validate_json(data)
    return UserPreferences.model_validate(data)


def load_notebook_policy(data: str | bytes | Mapping[str, object]) -> NotebookPolicy:
    """Parse the notebook policy scope from JSON text or a mapping at the boundary."""
    if isinstance(data, (str, bytes)):
        return NotebookPolicy.model_validate_json(data)
    return NotebookPolicy.model_validate(data)


def load_config(
    env: Mapping[str, str],
    *,
    user_preferences: str | bytes | Mapping[str, object] | None = None,
    notebook_policy: str | bytes | Mapping[str, object] | None = None,
) -> ConfigScopes:
    """Load all three distinct scopes into one typed aggregate."""
    return ConfigScopes(
        installation=load_installation(env),
        user_preferences=(
            load_user_preferences(user_preferences)
            if user_preferences is not None
            else UserPreferences()
        ),
        notebook_policy=(
            load_notebook_policy(notebook_policy)
            if notebook_policy is not None
            else NotebookPolicy()
        ),
    )
