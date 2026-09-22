"""Research runtime adapters: browser ports and the deterministic fake web."""

from milpbooklm_adapters.research.browser import UnavailableBrowserSession
from milpbooklm_adapters.research.fakeweb import (
    FAKE_SEARCH_RESULTS,
    FAKE_WEB_PAGES,
    FakeResearchWeb,
)

__all__ = [
    "FAKE_SEARCH_RESULTS",
    "FAKE_WEB_PAGES",
    "FakeResearchWeb",
    "UnavailableBrowserSession",
]
