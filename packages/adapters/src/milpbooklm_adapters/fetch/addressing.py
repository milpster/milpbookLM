"""
SSRF-hardened URL normalization and address validation (guide/19, guide/11).

Two layers, both pure and unit-testable without a socket:

* :func:`normalize_url` — scheme/port allowlist, embedded-credential and
  host-shape rejection; produces the canonical target the transport dials.
* :func:`select_pinned_address` — resolves EVERY candidate address of the
  host and refuses the connection if ANY of them is loopback/private/
  link-local/multicast/reserved (rebinding defense), then returns ONE
  validated public numeric address to pin.

The rejection reasons are stable strings; the transport (``pinned.py``)
raises :class:`SSRFBlockedError` before any socket is opened.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Final


class SSRFBlockedError(Exception):
    """A resolved address is not publicly routable; the connection is refused."""

    def __init__(self, address: str, reason: str, host: str) -> None:
        """Bind the offending address, the stable reason, and the requested host."""
        super().__init__(f"fetch destination {host} refused: {address} ({reason})")
        self.address: str = address
        self.reason: str = reason
        self.host: str = host


# Explicit rejection tables (guide/19: loopback/private/link-local/multicast/
# metadata ranges, both address families). Kept explicit instead of leaning on
# ipaddress flags, whose ``is_private`` semantics shift between Python versions.
_IPV4_BLOCKED: Final[tuple[ipaddress.IPv4Network, ...]] = tuple(
    ipaddress.IPv4Network(cidr)
    for cidr in (
        "0.0.0.0/8",  # this network / unspecified
        "10.0.0.0/8",  # RFC1918 private
        "100.64.0.0/10",  # CGNAT shared space
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local incl. cloud metadata 169.254.169.254
        "172.16.0.0/12",  # RFC1918 private
        "192.0.0.0/29",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1 documentation
        "192.88.99.0/24",  # 6to4 relay anycast
        "192.168.0.0/16",  # RFC1918 private
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2 documentation
        "203.0.113.0/24",  # TEST-NET-3 documentation
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved
        "255.255.255.255/32",  # broadcast
    )
)
_IPV6_BLOCKED: Final[tuple[ipaddress.IPv6Network, ...]] = tuple(
    ipaddress.IPv6Network(cidr)
    for cidr in (
        "::/128",  # unspecified
        "::1/128",  # loopback
        "64:ff9b::/96",  # NAT64 (carries an embedded IPv4 - validated separately)
        "100::/64",  # discard-only
        "2001:db8::/32",  # documentation
        "fc00::/7",  # unique local (private)
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
)
# IPv6 forms that EMBED an IPv4 address which must itself be validated
# (the plain ::ffff:a.b.c.d mapped form is handled by ip.ipv4_mapped first).
_V4_EMBEDDED_CHECKS: Final = (
    ("nat64", "64:ff9b::/96"),
    ("6to4", "2002::/16"),
    ("teredo", "2001:a::/32"),
)


def classify_address(address: str) -> str | None:
    """Return None for a public address, else the stable rejection reason."""
    text = address.strip("[]")
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        reason: str | None = "unparseable_address"
        return reason
    if isinstance(ip, ipaddress.IPv4Address):
        reason = None
        for network in _IPV4_BLOCKED:
            if ip in network:
                reason = _v4_reason(ip)
                break
        return reason
    return _classify_v6(ip)


def _classify_v6(ip: ipaddress.IPv6Address) -> str | None:
    mapped = ip.ipv4_mapped
    if mapped is not None:
        return classify_address(str(mapped))
    for name, prefix in _V4_EMBEDDED_CHECKS:
        if ip in ipaddress.ip_network(prefix):
            return classify_address(_embedded_v4(ip, name, prefix))
    reason = None
    for network in _IPV6_BLOCKED:
        if ip in network:
            reason = _v6_reason(ip)
            break
    return reason if reason is not None or ip.is_global else "reserved"


def _v4_reason(ip: ipaddress.IPv4Address) -> str:
    reason = "private_range"
    if ip.is_loopback:
        reason = "loopback"
    elif ip.is_unspecified:
        reason = "unspecified"
    elif ip in ipaddress.ip_network("169.254.0.0/16"):
        reason = "link_local_metadata"
    elif ip in ipaddress.ip_network("224.0.0.0/4"):
        reason = "multicast"
    elif ip in ipaddress.ip_network("240.0.0.0/4"):
        reason = "reserved"
    elif ip in ipaddress.ip_network("255.255.255.255/32"):
        reason = "broadcast"
    return reason


def _v6_reason(ip: ipaddress.IPv6Address) -> str:
    if ip.is_loopback:
        return "loopback"
    if ip.is_unspecified:
        return "unspecified"
    if ip in ipaddress.ip_network("fe80::/10"):
        return "link_local"
    if ip in ipaddress.ip_network("fc00::/7"):
        return "private_range"
    if ip in ipaddress.ip_network("ff00::/8"):
        return "multicast"
    return "reserved"


def _embedded_v4(ip: ipaddress.IPv6Address, name: str, prefix: str) -> str:
    """Extract the embedded IPv4 octets from an embedding form (RFC 4291/3056/4380)."""
    if ip not in ipaddress.ip_network(prefix):
        raise AssertionError("embedded IPv4 prefix mismatch")
    if name == "nat64":
        return str(ipaddress.IPv4Address(ip.packed[12:16]))
    if name == "6to4":
        return str(ipaddress.IPv4Address(ip.packed[2:6]))
    if name != "teredo":
        raise AssertionError("unknown embedded IPv4 format")
    # Teredo inverts the client address in the low 32 bits (RFC 4380).
    return str(ipaddress.IPv4Address(bytes(0xFF ^ b for b in ip.packed[12:16])))


AddressResolver = Callable[[str, int], list[str]]


def default_resolver(host: str, port: int) -> list[str]:
    """Resolve a host to every candidate address (deduplicated, stable order)."""
    candidates: list[str] = []
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    for info in addresses:
        address = str(info[4][0])
        if address not in candidates:
            candidates.append(address)
    return candidates


def select_pinned_address(
    host: str,
    port: int,
    resolver: AddressResolver | None = None,
) -> str:
    """
    Validate ALL candidate addresses of ``host`` and return one to pin.

    An IP-literal host is validated directly (no DNS). A hostname is resolved
    and the connection is refused when ANY candidate is non-public: a
    rebinding server that answers public-then-private cannot win, because we
    never connect before every answer has been checked.
    """
    try:
        _ = ipaddress.ip_address(host)
        reason = classify_address(host)
        if reason is not None:
            raise SSRFBlockedError(host, reason, host)
        return host
    except ValueError:
        pass
    resolve = resolver or default_resolver
    candidates = resolve(host, port)
    if not candidates:
        raise SSRFBlockedError("none", "no_address", host)
    for candidate in candidates:
        reason = classify_address(candidate)
        if reason is not None:
            raise SSRFBlockedError(candidate, reason, host)
    return candidates[0]
