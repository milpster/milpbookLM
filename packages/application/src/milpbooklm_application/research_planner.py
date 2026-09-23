"""
Research planner port, structured actions, and the deterministic planner (RSR-01b).

Structured tool selection (guide/19 prompt injection): a planner never emits
free-form text that is executed. It emits one schema-validated action per
decision - :func:`parse_action` is the boundary that accepts exactly the seven
constrained tools' argument shapes and nothing else (unknown tools, eval-style
calls, and malformed payloads are typed refusals). Planner CONTEXT carries
tool outputs strictly as untrusted data inside explicit delimiters; system
and tool policy never enter that channel.

The shipped deterministic planner implements ``source_discovery`` mode as a
fixed search -> fetch -> import -> finish program that is a pure function of
the run's trusted inputs (goal + tool set + config): untrusted tool output
cannot change its decisions. A run whose tool set lacks ``source.import``
finishes honestly after a successful fetch instead of proposing a call the
executor would deny. Model-driven planning for ``deep_research`` is an
explicitly experimental capability and is refused honestly until its adapter
exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from milpbooklm_domain.research import RESEARCH_TOOL_SURFACE, ResearchTool

UNTRUSTED_OPEN = "<untrusted-tool-output"
UNTRUSTED_CLOSE = "</untrusted-tool-output>"

# Control pseudo-action ending a run (not a tool; never part of the surface).
FINISH_ACTION = "finish"


class ActionParseError(ValueError):
    """A proposed action does not match the constrained tool-selection schema."""


def render_untrusted(tool: str, body: str) -> str:
    """Delimit one tool output as untrusted data (never policy-bearing text)."""
    return f"{UNTRUSTED_OPEN} tool={tool!r}>\n{body}\n{UNTRUSTED_CLOSE}"


@dataclass(frozen=True, slots=True)
class SearchAction:
    """web.search: one discovery query (untrusted results come back later)."""

    query: str


@dataclass(frozen=True, slots=True)
class FetchAction:
    """web.fetch: one static fetch of a discovered URL."""

    url: str


@dataclass(frozen=True, slots=True)
class BrowserOpenAction:
    """browser.open: navigate the run's disposable browser context to a URL."""

    url: str


@dataclass(frozen=True, slots=True)
class BrowserObserveAction:
    """browser.observe: read a structured observation of the current page."""

    focus: str | None = None


class BrowserGesture:
    """The constrained interaction vocabulary (no arbitrary script injection)."""

    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    PRESS = "press"
    ALL = frozenset({CLICK, TYPE, SCROLL, PRESS})


@dataclass(frozen=True, slots=True)
class BrowserInteractAction:
    """browser.interact: one constrained gesture on a selector (side effect)."""

    gesture: str
    selector: str
    value: str | None = None


@dataclass(frozen=True, slots=True)
class ImportAction:
    """source.import: promote one prior fetch's evidence via normal ingestion."""

    evidence_id: str
    title: str


@dataclass(frozen=True, slots=True)
class RetrieveAction:
    """read-only notebook retrieval over the run's notebook."""

    query: str


@dataclass(frozen=True, slots=True)
class FinishAction:
    """End the run with a summary and the candidate import references."""

    summary: str


PlannerAction = (
    SearchAction
    | FetchAction
    | BrowserOpenAction
    | BrowserObserveAction
    | BrowserInteractAction
    | ImportAction
    | RetrieveAction
    | FinishAction
)

_TOOL_FIELDS: dict[str, tuple[str, ...]] = {
    "web.search": ("query",),
    "web.fetch": ("url",),
    "browser.open": ("url",),
    "browser.observe": ("focus",),
    "browser.interact": ("gesture", "selector", "value"),
    "source.import": ("evidence_id", "title"),
    "notebook.retrieve": ("query",),
}


def _reject_extra_args(tool: str, args: Mapping[str, object]) -> None:
    """Refuse unknown argument names (injected fields must not slip through)."""
    extra = set(args) - set(_TOOL_FIELDS[tool])
    if extra:
        raise ActionParseError(f"unexpected args for {tool}: {sorted(extra)}")


def parse_action(  # noqa: C901, PLR0911, PLR0912 - one branch per surface tool
    payload: Mapping[str, object]
) -> PlannerAction:
    """
    Parse one proposed tool call at the structured-selection boundary.

    Only the seven constrained tools, only their exact argument shapes, only
    string values - anything else (``browser.eval``, injected instructions,
    missing/extra/mistyped fields) raises :class:`ActionParseError`.
    """
    if not isinstance(payload, Mapping):
        raise ActionParseError("action must be a mapping")
    tool = payload.get("tool")
    if tool == FINISH_ACTION:
        return FinishAction(summary=_string_arg(_args(payload), "summary"))
    if not isinstance(tool, str) or tool not in RESEARCH_TOOL_SURFACE:
        raise ActionParseError(f"tool outside the constrained surface: {tool!r}")
    args = _args(payload)
    _reject_extra_args(tool, args)
    match tool:
        case ResearchTool.WEB_SEARCH.value:
            return SearchAction(query=_string_arg(args, "query"))
        case ResearchTool.WEB_FETCH.value:
            return FetchAction(url=_string_arg(args, "url"))
        case ResearchTool.BROWSER_OPEN.value:
            return BrowserOpenAction(url=_string_arg(args, "url"))
        case ResearchTool.BROWSER_OBSERVE.value:
            focus = args.get("focus")
            if focus is not None and not isinstance(focus, str):
                raise ActionParseError("browser.observe focus must be a string")
            return BrowserObserveAction(focus=focus)
        case ResearchTool.BROWSER_INTERACT.value:
            gesture = _string_arg(args, "gesture")
            if gesture not in BrowserGesture.ALL:
                raise ActionParseError(f"unknown browser gesture: {gesture!r}")
            value = args.get("value")
            if value is not None and not isinstance(value, str):
                raise ActionParseError("browser.interact value must be a string")
            return BrowserInteractAction(
                gesture=gesture,
                selector=_string_arg(args, "selector"),
                value=value,
            )
        case ResearchTool.SOURCE_IMPORT.value:
            return ImportAction(
                evidence_id=_string_arg(args, "evidence_id"),
                title=_string_arg(args, "title"),
            )
        case ResearchTool.NOTEBOOK_RETRIEVE.value:
            return RetrieveAction(query=_string_arg(args, "query"))
        case _:
            raise ActionParseError(f"unhandled tool: {tool!r}")


def _args(payload: Mapping[str, object]) -> Mapping[str, object]:
    args = payload.get("args")
    if not isinstance(args, Mapping):
        raise ActionParseError("action args must be a mapping")
    return args


def _string_arg(args: Mapping[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ActionParseError(f"arg {name!r} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class ToolTurn:
    """One prior tool outcome as seen by the planner (untrusted data)."""

    tool: str
    ok: bool
    refusal_code: str | None
    summary: str
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlannerContext:
    """Trusted run inputs plus the untrusted tool-output history."""

    run_id: str
    notebook_id: str
    goal: str
    mode: str
    tools: frozenset[str]
    turns: tuple[ToolTurn, ...] = ()

    def untrusted_history(self) -> str:
        """Render the tool history as delimited untrusted data blocks."""
        return "\n".join(render_untrusted(turn.tool, turn.summary) for turn in self.turns)


class ResearchPlanner(Protocol):
    """Decides the run's next action from trusted inputs + untrusted history."""

    async def next_action(self, context: PlannerContext) -> Mapping[str, object]:
        """Propose the next action as a raw mapping (parsed by parse_action)."""
        ...


def _fetchable_url(turn: ToolTurn) -> str | None:
    """Extract the first fetchable URL from a web.search turn's summary."""
    if turn.tool != ResearchTool.WEB_SEARCH.value or not turn.ok:
        return None
    for line in turn.summary.splitlines():
        marker = line.find("url=")
        if marker >= 0:
            candidate = line[marker + len("url=") :].strip().split()[0]
            if candidate.startswith(("http://", "https://")):
                return candidate
    return None


class SourceDiscoveryPlanner:
    """
    Deterministic source_discovery program: search, fetch, import, finish.

    The program only proposes tools the run was created with: when
    ``source.import`` is absent from the run's tool set, a successful fetch
    finishes the run honestly instead of proposing an action the executor's
    authorization would deny every turn.
    """

    async def next_action(self, context: PlannerContext) -> Mapping[str, object]:
        """Return the next action purely from the trusted run inputs."""
        searched = any(turn.tool == ResearchTool.WEB_SEARCH.value for turn in context.turns)
        if not searched:
            return {"tool": ResearchTool.WEB_SEARCH.value, "args": {"query": context.goal}}
        fetched_id = _fetched_evidence(context.turns)
        if fetched_id is None:
            url = next(
                (
                    _fetchable_url(turn)
                    for turn in reversed(context.turns)
                    if _fetchable_url(turn) is not None
                ),
                None,
            )
            if url is None:
                return {
                    "tool": FINISH_ACTION,
                    "args": {"summary": "no fetchable discovery result; stopping"},
                }
            return {"tool": ResearchTool.WEB_FETCH.value, "args": {"url": url}}
        if ResearchTool.SOURCE_IMPORT.value not in context.tools:
            return {
                "tool": FINISH_ACTION,
                "args": {
                    "summary": "web source retrieved; source.import tool not "
                    "available in this run; finishing"
                },
            }
        imported = any(turn.tool == ResearchTool.SOURCE_IMPORT.value for turn in context.turns)
        if not imported:
            return {
                "tool": ResearchTool.SOURCE_IMPORT.value,
                "args": {
                    "evidence_id": fetched_id,
                    "title": f"Research import: {context.goal[:120]}",
                },
            }
        return {
            "tool": FINISH_ACTION,
            "args": {
                "summary": "source_discovery complete: one curated result imported "
                "through normal ingestion"
            },
        }


def _fetched_evidence(turns: Sequence[ToolTurn]) -> str | None:
    """Return the evidence id of the last successful web.fetch turn, if any."""
    for turn in reversed(turns):
        if turn.tool == ResearchTool.WEB_FETCH.value and turn.ok and turn.evidence_id:
            return turn.evidence_id
    return None
