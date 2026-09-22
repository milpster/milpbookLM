"""URL normalization policy for the dedicated fetch service."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import SplitResult, urlsplit

ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
ALLOWED_PORTS: Final = frozenset({80, 443})
_DEFAULT_PORTS: Final = {"http": 80, "https": 443}
_MAX_URL_LENGTH: Final = 2048
_MAX_HOST_LENGTH: Final = 253
_HOST_LABEL: Final = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


class FetchPolicyError(Exception):
    """The URL violates the fetch policy (scheme, port, credentials, host)."""


@dataclass(frozen=True, slots=True)
class FetchTarget:
    """A normalized, policy-checked fetch target (pre-resolution)."""

    scheme: str
    host: str
    port: int
    url: str


def normalize_url(
    url: str,
    *,
    allowed_schemes: frozenset[str] = ALLOWED_SCHEMES,
    allowed_ports: frozenset[int] = ALLOWED_PORTS,
) -> FetchTarget:
    """Parse and policy-check one URL before any resolution happens."""
    if not url or len(url) > _MAX_URL_LENGTH:
        raise FetchPolicyError("url is empty or exceeds the length limit")
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in allowed_schemes:
        raise FetchPolicyError(f"scheme {parts.scheme!r} is not allowed (http/https only)")
    if parts.username is not None or parts.password is not None:
        raise FetchPolicyError("embedded credentials are not allowed")
    host, is_ip_literal = _normalized_host(parts)
    port = _normalized_port(parts, scheme, allowed_ports)
    authority = f"[{host}]" if is_ip_literal and ":" in host else host
    if port != _DEFAULT_PORTS[scheme]:
        authority = f"{authority}:{port}"
    path = parts.path or "/"
    query = f"?{parts.query}" if parts.query else ""
    return FetchTarget(
        scheme=scheme,
        host=host,
        port=port,
        url=f"{scheme}://{authority}{path}{query}",
    )


def _normalized_host(parts: SplitResult) -> tuple[str, bool]:
    host = parts.hostname
    if not host:
        raise FetchPolicyError("url has no host")
    host = host.lower().rstrip(".")
    if len(host) > _MAX_HOST_LENGTH:
        raise FetchPolicyError("host exceeds the length limit")
    try:
        _ = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            raise FetchPolicyError("host is not a valid hostname") from None
        if not _HOST_LABEL.match(host):
            raise FetchPolicyError("host is not a valid hostname") from None
        return host, False
    return host, True


def _normalized_port(
    parts: SplitResult, scheme: str, allowed_ports: frozenset[int]
) -> int:
    try:
        port = parts.port
    except ValueError:
        raise FetchPolicyError("url port is invalid") from None
    if port is None:
        return _DEFAULT_PORTS[scheme]
    if port not in allowed_ports:
        raise FetchPolicyError(f"port {port} is not an allowed web port")
    return port
