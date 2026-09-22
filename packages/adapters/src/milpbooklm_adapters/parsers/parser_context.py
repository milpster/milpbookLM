"""Typed context passed from acquisition jobs into isolated parsers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebLocatorContext:
    """Canonical URL and capture time required by web snapshot locators."""

    canonical_url: str
    captured_at: str
