"""
Typed configuration scopes (ch04).

Installation configuration, user preferences and notebook policy are three
distinct scopes: the first is deployment-wide (environment/file secrets at
startup), the other two are per-user and per-notebook policy documents.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AppearanceTheme(StrEnum):
    """Light/dark/system UI preference (ch02 parity matrix: Appearance)."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class ResponseLength(StrEnum):
    """Chat response-length preference (ch02 parity matrix: Chat configuration)."""

    SHORT = "short"
    DEFAULT = "default"
    LONGER = "longer"


class ChatProvider(StrEnum):
    """Supported installation-level ordinary-chat providers."""

    LLAMA_CPP = "llama_cpp"
    FAKE = "fake"


class ModelRoute(BaseModel):
    """One ordered provider route loaded from the checked-in selection record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str
    model: str
    external: bool
    privacy_class: str
    disclosure_required: bool
    availability: str
    lapse_behavior: str | None = None


class ModelRoutingConfig(BaseModel):
    """Versioned ordinary-chat fallback order consumed by composition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    providers: tuple[ModelRoute, ...]


class InstallationConfig(BaseModel):
    """
    Installation scope: deployment-wide values, loaded from the environment at startup.

    Secrets cross the boundary as :class:`SecretStr`; the loader resolves
    ``_FILE`` variants (ch04: environment/file secrets) before validation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_url: SecretStr
    secret_key: SecretStr
    blob_root: Path
    base_url: str
    trusted_proxy_peers: tuple[str, ...] = ()
    master_keyring_file: Path | None = None
    audit_retention_days: int = Field(default=365, gt=0)
    max_acquisition_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    prerequisites_file: Path = Path("/run/milpbooklm/prerequisites.json")
    enabled_capability_flags: tuple[str, ...] = ()
    configured_provider_capabilities: tuple[str, ...] = ()
    chat_provider: ChatProvider = ChatProvider.LLAMA_CPP
    model_routing: ModelRoutingConfig
    # IDX-01: optional local embedding endpoint; when unset, vector retrieval is
    # unavailable (the API answers an explicit problem, never a silent failure).
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = Field(default=None, gt=0)


class UserPreferences(BaseModel):
    """User preference scope: per-user settings, kept distinct from installation config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    theme: AppearanceTheme = AppearanceTheme.SYSTEM
    output_language: str | None = None
    response_length: ResponseLength = ResponseLength.DEFAULT


class NotebookPolicy(BaseModel):
    """
    Notebook policy scope: per-notebook administrative policy.

    ``allow_external_providers`` defaults to True (ARCH-01-002: external
    providers remain allowed unless explicitly disabled by policy); a policy
    document may disable them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allow_external_providers: bool = True


class ConfigScopes(BaseModel):
    """The three distinct configuration scopes as a single typed aggregate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    installation: InstallationConfig
    user_preferences: UserPreferences = UserPreferences()
    notebook_policy: NotebookPolicy = NotebookPolicy()
