"""
Browser-automation policy for research runs (guide/11 "Playwright").

"Browser automation is invoked only when static fetch cannot render required
public content or an explicit authorized workflow requires interaction."

The decision point is server-side and reads TRUSTED inputs only:

* **authorized workflow** — the run's recorded approvals explicitly include
  ``browser.open`` (the UI approval flow the run was created with; the model
  has no vote in populating it);
* **static fetch insufficient** — a prior ``web.fetch`` of the SAME url
  already failed in this run, so static fetching demonstrably cannot
  retrieve the content and rendering is the fallback.

Anything else is denied with a stable reason recorded as an audited
``tool.denied`` entry (the injection log).
"""

from __future__ import annotations

from milpbooklm_domain.research import ResearchTool

from .research_planner import ToolTurn

DENIED_AUTOMATION_NOT_AUTHORIZED = "browser_automation_not_authorized"


def browser_automation_denial(
    approved_tools: frozenset[str], prior_turns: tuple[ToolTurn, ...], url: str
) -> str | None:
    """
    Decide one proposed browser.open from trusted configuration + history.

    Returns None when automation may proceed, else the stable denial reason.
    """
    if ResearchTool.BROWSER_OPEN.value in approved_tools:
        return None
    marker = f"fetch failed for {url}"
    for turn in prior_turns:
        if (
            turn.tool == ResearchTool.WEB_FETCH.value
            and not turn.ok
            and marker in turn.summary
        ):
            return None
    return DENIED_AUTOMATION_NOT_AUTHORIZED
