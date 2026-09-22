"""Unit tests for the typed configuration loader (FND-02, ch04).

Given: an environment mapping and scope documents.
When:  the loader loads / parses them.
Then:  typed scopes result; unknown security-sensitive keys are rejected.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from milpbooklm_api.config import (
    AppearanceTheme,
    ConfigScopes,
    InstallationConfig,
    NotebookPolicy,
    ResponseLength,
    UserPreferences,
)
from milpbooklm_api.config_loader import ConfigError, load_config, load_installation
from milpbooklm_api.health_routes import REQUIRED_POSTGRES_MAJOR
from pydantic import ValidationError

VALID_ENV: Mapping[str, str] = {
    "MILPBOOKLM_DATABASE_URL": "postgresql://user:pass@localhost/milpbooklm",
    "MILPBOOKLM_SECRET_KEY": "in-memory-secret",
    "MILPBOOKLM_BLOB_ROOT": "/var/lib/milpbooklm/blobs",
    "MILPBOOKLM_BASE_URL": "https://notebooks.example.org",
    "MILPBOOKLM_TRUSTED_PROXY_PEERS": "10.0.0.0/8, 192.168.1.5",
}
DEV_POSTGRES_MAJOR = 17
PRODUCTION_LOGIN_MAX_ATTEMPTS = 5
PRODUCTION_LOGIN_WINDOW_MINUTES = 15
PRODUCTION_REGISTER_MAX_ATTEMPTS = 3
PRODUCTION_REGISTER_WINDOW_MINUTES = 60
DEV_LOGIN_MAX_ATTEMPTS = 50
DEV_LOGIN_WINDOW_MINUTES = 5.5
DEV_REGISTER_MAX_ATTEMPTS = 20
DEV_REGISTER_WINDOW_MINUTES = 30.5


def test_installation_loads_from_env() -> None:
    given = dict(VALID_ENV)
    when = load_installation(given)
    then = when
    assert isinstance(then, InstallationConfig)
    assert then.database_url.get_secret_value() == "postgresql://user:pass@localhost/milpbooklm"
    assert then.secret_key.get_secret_value() == "in-memory-secret"
    assert then.blob_root == Path("/var/lib/milpbooklm/blobs")
    assert then.base_url == "https://notebooks.example.org"
    assert then.trusted_proxy_peers == ("10.0.0.0/8", "192.168.1.5")


def test_model_routing_uses_locked_local_first_order() -> None:
    when = load_installation(VALID_ENV)
    then = tuple(route.provider_id for route in when.model_routing.providers)
    assert then == ("llama_cpp_local", "big_pickle", "muse_spark_standard")


def test_file_secret_resolves_and_strips_single_trailing_newline(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.key"
    secret_file.write_text("file-backed-secret\n", encoding="utf-8")
    env = {
        "MILPBOOKLM_DATABASE_URL": "postgresql://user:pass@localhost/milpbooklm",
        "MILPBOOKLM_SECRET_KEY_FILE": str(secret_file),
        "MILPBOOKLM_BLOB_ROOT": "/var/lib/milpbooklm/blobs",
        "MILPBOOKLM_BASE_URL": "https://notebooks.example.org",
    }
    when = load_installation(env)
    then = when.secret_key.get_secret_value()
    assert then == "file-backed-secret"


def test_file_secret_without_trailing_newline_is_kept_verbatim(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.key"
    secret_file.write_text("no-newline-secret", encoding="utf-8")
    env = {
        "MILPBOOKLM_DATABASE_URL": "postgresql://u:p@localhost/x",
        "MILPBOOKLM_SECRET_KEY_FILE": str(secret_file),
        "MILPBOOKLM_BLOB_ROOT": "/blobs",
        "MILPBOOKLM_BASE_URL": "https://x",
    }
    assert load_installation(env).secret_key.get_secret_value() == "no-newline-secret"


def test_missing_secret_file_is_rejected(tmp_path: Path) -> None:
    env = {
        "MILPBOOKLM_DATABASE_URL": "postgresql://u:p@localhost/x",
        "MILPBOOKLM_SECRET_KEY_FILE": str(tmp_path / "absent"),
        "MILPBOOKLM_BLOB_ROOT": "/blobs",
        "MILPBOOKLM_BASE_URL": "https://x",
    }
    with pytest.raises(ConfigError) as excinfo:
        load_installation(env)
    assert str(tmp_path / "absent") in excinfo.value.keys


def test_plain_and_file_secret_together_are_rejected(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.key"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    env = {
        "MILPBOOKLM_DATABASE_URL": "postgresql://u:p@localhost/x",
        "MILPBOOKLM_SECRET_KEY": "plain-secret",
        "MILPBOOKLM_SECRET_KEY_FILE": str(secret_file),
        "MILPBOOKLM_BLOB_ROOT": "/blobs",
        "MILPBOOKLM_BASE_URL": "https://x",
    }
    with pytest.raises(ConfigError, match="ambiguous"):
        load_installation(env)


def test_unknown_security_sensitive_key_is_rejected() -> None:
    env = {**VALID_ENV, "MILPBOOKLM_TRUST_PROXY": "yes"}
    with pytest.raises(ConfigError) as excinfo:
        load_installation(env)
    assert excinfo.value.keys == ("MILPBOOKLM_TRUST_PROXY",)
    assert "MILPBOOKLM_TRUST_PROXY" in str(excinfo.value)


def test_unknown_key_rejection_happens_before_partial_load() -> None:
    env = {**VALID_ENV, "MILPBOOKLM_SECRET_OVERRIDE": "x", "MILPBOOKLM_AAD_DB": "y"}
    with pytest.raises(ConfigError) as excinfo:
        load_installation(env)
    assert excinfo.value.keys == ("MILPBOOKLM_AAD_DB", "MILPBOOKLM_SECRET_OVERRIDE")


def test_non_prefixed_environment_keys_are_not_ours() -> None:
    env = {**VALID_ENV, "PATH": "/usr/bin", "HOME": "/root"}
    when = load_installation(env)
    assert when.base_url == "https://notebooks.example.org"


def test_required_postgres_major_defaults_to_the_production_value() -> None:
    assert load_installation(VALID_ENV).required_postgres_major == REQUIRED_POSTGRES_MAJOR


def test_required_postgres_major_is_overridable_for_dev() -> None:
    env = {**VALID_ENV, "MILPBOOKLM_REQUIRED_POSTGRES_MAJOR": str(DEV_POSTGRES_MAJOR)}
    assert load_installation(env).required_postgres_major == DEV_POSTGRES_MAJOR


def test_required_postgres_major_rejects_non_positive_values() -> None:
    env = {**VALID_ENV, "MILPBOOKLM_REQUIRED_POSTGRES_MAJOR": "0"}
    with pytest.raises(ConfigError) as excinfo:
        load_installation(env)
    assert excinfo.value.keys == ("MILPBOOKLM_REQUIRED_POSTGRES_MAJOR",)


def test_auth_rate_limits_default_to_production_values() -> None:
    installation = load_installation(VALID_ENV)
    assert installation.login_max_attempts == PRODUCTION_LOGIN_MAX_ATTEMPTS
    assert installation.login_window_minutes == PRODUCTION_LOGIN_WINDOW_MINUTES
    assert installation.register_max_attempts == PRODUCTION_REGISTER_MAX_ATTEMPTS
    assert installation.register_window_minutes == PRODUCTION_REGISTER_WINDOW_MINUTES


def test_auth_rate_limits_are_env_overridable() -> None:
    env = {
        **VALID_ENV,
        "MILPBOOKLM_LOGIN_MAX_ATTEMPTS": str(DEV_LOGIN_MAX_ATTEMPTS),
        "MILPBOOKLM_LOGIN_WINDOW_MINUTES": str(DEV_LOGIN_WINDOW_MINUTES),
        "MILPBOOKLM_REGISTER_MAX_ATTEMPTS": str(DEV_REGISTER_MAX_ATTEMPTS),
        "MILPBOOKLM_REGISTER_WINDOW_MINUTES": str(DEV_REGISTER_WINDOW_MINUTES),
    }
    installation = load_installation(env)
    assert installation.login_max_attempts == DEV_LOGIN_MAX_ATTEMPTS
    assert installation.login_window_minutes == DEV_LOGIN_WINDOW_MINUTES
    assert installation.register_max_attempts == DEV_REGISTER_MAX_ATTEMPTS
    assert installation.register_window_minutes == DEV_REGISTER_WINDOW_MINUTES


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MILPBOOKLM_LOGIN_MAX_ATTEMPTS", "0"),
        ("MILPBOOKLM_LOGIN_MAX_ATTEMPTS", "1.5"),
        ("MILPBOOKLM_REGISTER_MAX_ATTEMPTS", "-1"),
        ("MILPBOOKLM_REGISTER_MAX_ATTEMPTS", "many"),
        ("MILPBOOKLM_LOGIN_WINDOW_MINUTES", "0"),
        ("MILPBOOKLM_LOGIN_WINDOW_MINUTES", "nan"),
        ("MILPBOOKLM_REGISTER_WINDOW_MINUTES", "-1"),
        ("MILPBOOKLM_REGISTER_WINDOW_MINUTES", "minutes"),
    ],
)
def test_auth_rate_limits_reject_invalid_values(key: str, value: str) -> None:
    env = {**VALID_ENV, key: value}
    with pytest.raises(ConfigError) as excinfo:
        load_installation(env)
    assert excinfo.value.keys == (key,)
    assert "must be a positive" in str(excinfo.value)


def test_missing_required_key_is_a_typed_config_error() -> None:
    env = {k: v for k, v in VALID_ENV.items() if k != "MILPBOOKLM_DATABASE_URL"}
    with pytest.raises(ConfigError) as excinfo:
        load_installation(env)
    assert excinfo.value.keys == ("MILPBOOKLM_DATABASE_URL",)


def test_user_preferences_parses_json_and_rejects_unknown_keys() -> None:
    document = {"theme": "dark", "output_language": "pl", "response_length": "shorter"}
    with pytest.raises(ValidationError):
        load_config(VALID_ENV, user_preferences=json.dumps(document))
    good = json.dumps({"theme": "dark", "output_language": "pl", "response_length": "longer"})
    when = load_config(VALID_ENV, user_preferences=good)
    then = when.user_preferences
    assert (then.theme, then.output_language, then.response_length) == (
        AppearanceTheme.DARK,
        "pl",
        ResponseLength.LONGER,
    )


def test_notebook_policy_can_disable_external_providers() -> None:
    policy = json.dumps({"allow_external_providers": False})
    when = load_config(VALID_ENV, notebook_policy=policy)
    assert when.notebook_policy.allow_external_providers is False
    assert NotebookPolicy().allow_external_providers is True


def test_notebook_policy_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        load_config(VALID_ENV, notebook_policy=json.dumps({"allow_external_providersx": False}))


def test_three_scopes_are_distinct_documents() -> None:
    installation_env = dict(VALID_ENV)
    prefs = json.dumps({"theme": "light"})
    policy = json.dumps({"allow_external_providers": False})
    when = load_config(installation_env, user_preferences=prefs, notebook_policy=policy)
    then: ConfigScopes = when
    assert isinstance(then.installation, InstallationConfig)
    assert isinstance(then.user_preferences, UserPreferences)
    assert isinstance(then.notebook_policy, NotebookPolicy)
    assert then.user_preferences.theme is AppearanceTheme.LIGHT
    assert then.notebook_policy.allow_external_providers is False
    assert then.installation.blob_root == Path("/var/lib/milpbooklm/blobs")
