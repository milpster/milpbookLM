"""
Default log redaction (ch18): scrub tokens/cookies/prompts before export (stdlib).

Two complementary passes:

* :func:`redact_structure` walks an arbitrary dict/list tree and replaces the value
  of any key whose name names a secret (authorization, cookie, session, token,
  password, secret, key, credential, prompt, source content, provider payloads) with
  :data:`REDACTED`, preserving the surrounding non-sensitive metadata.
* :func:`scrub_message` scrubs obvious credential/token/cookie values out of a plain
  message string (e.g. an interpolated ``Authorization: Bearer ...``).

Over-redaction is preferred to under-redaction: a key that merely *contains* a
sensitive fragment is redacted, so new sensitive fields are safe by default.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

# Exact (lowercased) key names that always carry a secret value.
_EXACT_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "session",
        "session_id",
        "sessionid",
        "token",
        "csrf_token",
        "access_token",
        "refresh_token",
        "api_token",
        "api_key",
        "apikey",
        "password",
        "passwd",
        "pwd",
        "secret",
        "secret_key",
        "client_secret",
        "private_key",
        "certificate",
        "credential",
        "credentials",
        "prompt",
        "prompts",
        "source_text",
        "source_content",
        "content",
        "provider_payload",
        "bearer",
    }
)

# Substring fragments (lowercased): a key containing any of these is redacted.
_FRAGMENTS: tuple[str, ...] = (
    "password",
    "passwd",
    "token",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "prompt",
    "private_key",
    "client_secret",
    "access_key",
    "master_key",
)

# Conservative value-level scrubs for plain message strings (never whole-field).
_MESSAGE_SCRUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + REDACTED),
    (re.compile(r"(?i)\bauthorization\s*[:=]\s*\S+"), "authorization: " + REDACTED),
    (re.compile(r"(?i)\bset-cookie\s*[:=]\s*\S+"), "set-cookie: " + REDACTED),
    (
        re.compile(r"(?i)\bcookie\s*[:=]\s*[^\s;]+(?:;\s*[^\s=]+\s*=\s*[^\s;]+)*"),
        "cookie: " + REDACTED,
    ),
    (re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*\S+"), "api_key: " + REDACTED),
    (re.compile(r"(?i)\bpassword\s*[:=]\s*\S+"), "password: " + REDACTED),
    (re.compile(r"(?i)\b(?:access[_-]?)?token\s*[:=]\s*\S+"), "token: " + REDACTED),
    (re.compile(r"(?i)\bsecret\s*[:=]\s*\S+"), "secret: " + REDACTED),
)


def is_sensitive_key(key: object) -> bool:
    """Return True when a mapping key names a secret (exact name or sensitive fragment)."""
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in _EXACT_KEYS:
        return True
    return any(fragment in lowered for fragment in _FRAGMENTS)


def scrub_message(text: str) -> str:
    """Scrub obvious credential/token/cookie values from a plain message string."""
    result = text
    for pattern, replacement in _MESSAGE_SCRUBS:
        result = pattern.sub(replacement, result)
    return result


def redact_structure(value: Any) -> Any:
    """
    Return a copy of ``value`` with sensitive values redacted (recursive).

    Dicts redact by key name and recurse into the rest; lists/tuples recurse into
    elements; strings pass through (value scrubbing is the caller's job via
    :func:`scrub_message`); other scalars are returned unchanged.
    """
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            redacted[key] = REDACTED if is_sensitive_key(key) else redact_structure(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_structure(item) for item in value]
    return value
