"""
RSR-01c browser worker integration suite (guide/11 + guide/19).

Spawns the REAL worker subprocess (Node + Playwright + Chromium) against the
deterministic local web fixtures on loopback. The fixture origin is passed
explicitly in ``allowed_origins`` — proving the blocklist is configurable
per deployment while staying ON by default (loopback blocked, private
ranges ALWAYS blocked).

These tests prove the acceptance criteria: sandbox-posture startup, private
network refusals with a denial log, JS rendering where static fetch fails,
disposable contexts, download quarantine, bounded navigation, and the
executor-driven browser journey (E2E-008 research legs with the browser
tool). They are skipped with an explicit reason when node/playwright are
not resolvable — an environment that cannot run them cannot prove the
posture, and silently passing would be a fabrication.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest
from milpbooklm_adapters.research.browser_worker import (
    BrowserWorkerConfig,
    PlaywrightBrowserSession,
)
from milpbooklm_application.research_browser import (
    BrowserErrorCode,
    BrowserGestureCommand,
    BrowserUnavailableError,
)

from tests.fixtures.web import localweb


def _playwright_resolvable() -> bool:
    """Mirror the worker's resolution walk (env root, then ancestors)."""
    candidates: list[Path] = []
    env_root = os.environ.get("MILPBOOKLM_PLAYWRIGHT_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    for base in (Path(__file__), Path.cwd()):
        candidates.extend(base.resolve().parents)
    return any(
        (directory / "node_modules" / "playwright" / "package.json").is_file()
        for directory in candidates
    )


SECCOMP_FILTER_MODE = 2  # /proc/<pid>/status Seccomp: 2 = filter active
HTTP_OK = 200
HTTP_FORBIDDEN = 403

requires_worker = pytest.mark.skipif(
    shutil.which("node") is None or not _playwright_resolvable(),
    reason="node + playwright must be resolvable to prove the browser sandbox posture",
)


@pytest.fixture
def web() -> Any:
    """Serve the deterministic local web fixtures on an ephemeral port."""
    fixture = localweb.start_local_web()
    yield fixture
    fixture.close()


def _session(
    web: localweb.LocalWebFixture, quarantine: Path, **overrides: Any
) -> PlaywrightBrowserSession:
    config = BrowserWorkerConfig(
        quarantine_dir=quarantine,
        allowed_origins=(web.origin,),
        **overrides,
    )
    return PlaywrightBrowserSession(config)


def _drive(
    work: Callable[[PlaywrightBrowserSession], Any], session: PlaywrightBrowserSession
) -> Any:
    async def run() -> Any:
        await session.start()
        try:
            return await work(session)
        finally:
            await session.aclose()

    return anyio.run(run)


@requires_worker
def test_startup_proves_sandbox_posture(web: Any, tmp_path: Path) -> None:
    """Startup check PROVES sandbox-on: never --no-sandbox, seccomp live."""

    async def work(session: PlaywrightBrowserSession) -> None:
        posture = await session.start()
        assert posture.proven()
        assert posture.no_sandbox_args is False
        assert posture.sandboxed_renderers >= 1
        assert any(
            entry["seccomp"] == SECCOMP_FILTER_MODE and entry["noNewPrivs"] == 1
            for entry in posture.probe
        )
        assert posture.chromium_version
        assert session.posture is posture

    _drive(work, _session(web, tmp_path / "quarantine"))


@requires_worker
@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://10.0.0.1/x", "private_range"),
        ("http://192.168.0.5/", "private_range"),
        ("http://169.254.169.254/latest/meta-data/", "link_local_metadata"),
        ("http://127.0.0.1:1/loopback-without-allowance", "loopback"),
        ("http://[::1]/", "loopback"),
    ],
)
def test_navigation_to_private_targets_refused_pre_connect(
    web: Any, tmp_path: Path, url: str, reason: str
) -> None:
    """Private/link-local/metadata/loopback navigation is refused + logged."""

    async def work(session: PlaywrightBrowserSession) -> None:
        with pytest.raises(BrowserUnavailableError) as raised:
            await session.open(url)
        assert raised.value.code == BrowserErrorCode.ADDRESS_BLOCKED
        assert reason in raised.value.detail
        denials = session.denials()
        assert denials, "the refusal must be recorded in the denial log"
        assert denials[-1].phase == "navigate"
        assert denials[-1].reason == reason

    _drive(work, _session(web, tmp_path / "quarantine"))


@requires_worker
def test_private_subresources_blocked_from_context_with_denial_log(
    web: Any, tmp_path: Path
) -> None:
    """Page JS probing 10.0.0.0/8 + metadata is blocked pre-connect (QA case)."""

    async def work(session: PlaywrightBrowserSession) -> None:
        await session.open(web.url("/private-links"))
        observation = await session.observe()
        # Every probe target must be blocked: the page records one marker per
        # target and NONE may report "unexpectedly-open".
        assert "unexpectedly-open" not in observation.visible_text_excerpt
        for target in ("10.0.0.1", "169.254.169.254", "192.168.0.10"):
            assert f"{target}=blocked" in observation.visible_text_excerpt
        denials = {(entry.host, entry.reason) for entry in session.denials()}
        assert ("10.0.0.1", "private_range") in denials
        assert ("169.254.169.254", "link_local_metadata") in denials
        assert ("192.168.0.10", "private_range") in denials
        assert all(entry.phase == "route" for entry in session.denials())

    _drive(work, _session(web, tmp_path / "quarantine"))


@requires_worker
def test_js_rendering_succeeds_where_static_fetch_fails(web: Any, tmp_path: Path) -> None:
    """Static fetch sees only the stub; the worker materializes the content."""

    async def static_control() -> httpx.Response:
        async with httpx.AsyncClient() as client:
            return await client.get(web.url("/js-render"))

    static = anyio.run(static_control)
    assert static.status_code == HTTP_OK
    assert localweb.JS_RENDERED_MARKER not in static.text
    assert "js-stub-loading" in static.text

    async def work(session: PlaywrightBrowserSession) -> None:
        page = await session.open(web.url("/js-render"))
        assert localweb.JS_RENDERED_MARKER in page.text_excerpt
        observation = await session.observe(focus=localweb.JS_LATE_SECTION)
        assert localweb.JS_RENDERED_MARKER in observation.visible_text_excerpt
        assert observation.focused_excerpt is not None
        assert localweb.JS_LATE_SECTION in observation.focused_excerpt

    _drive(work, _session(web, tmp_path / "quarantine"))


@requires_worker
def test_disposable_contexts_do_not_leak_storage(web: Any, tmp_path: Path) -> None:
    """Session A's localStorage never carries into session B (clean contexts)."""

    async def work(session: PlaywrightBrowserSession) -> None:
        await session.open(web.url("/storage"))
        await session.interact(BrowserGestureCommand(gesture="click", selector="#set"))
        observation = await session.observe()
        assert "set-by-session" in observation.visible_text_excerpt

    _drive(work, _session(web, tmp_path / "quarantine-a"))

    async def control(session: PlaywrightBrowserSession) -> None:
        page = await session.open(web.url("/storage"))
        assert "set-by-session" not in page.text_excerpt
        assert "EMPTY" in page.text_excerpt

    _drive(control, _session(web, tmp_path / "quarantine-b"))


@requires_worker
def test_downloads_return_via_quarantine_and_respect_size_cap(
    web: Any, tmp_path: Path
) -> None:
    """Downloads land in quarantine (never auto-trusted); oversized refused."""
    quarantine = tmp_path / "quarantine"

    async def work(session: PlaywrightBrowserSession) -> None:
        page = await session.open(web.url("/download"))
        assert page.title.startswith("download:t28-report.txt")
        quarantined = session.quarantined_downloads()
        assert len(quarantined) == 1
        assert quarantined[0].name == "t28-report.txt"
        assert quarantined[0].size_bytes == len(localweb.DOWNLOAD_BYTES)
        landed = Path(quarantined[0].path)
        assert landed.parent == quarantine
        assert landed.read_bytes() == localweb.DOWNLOAD_BYTES

        with pytest.raises(BrowserUnavailableError) as raised:
            await session.open(web.url("/huge-download"))
        assert raised.value.code == BrowserErrorCode.DOWNLOAD_LIMIT_EXCEEDED
        assert any(event.name == "t28-huge.bin" for event in session.refused_downloads())
        assert list(quarantine.glob("*t28-huge.bin")) == []

    _drive(work, _session(web, quarantine, download_limit_bytes=512))


@requires_worker
def test_slow_pages_fail_with_bounded_navigation_timeout(web: Any, tmp_path: Path) -> None:
    """A page slower than the navigation budget fails with a typed refusal."""

    async def work(session: PlaywrightBrowserSession) -> None:
        with pytest.raises(BrowserUnavailableError) as raised:
            await session.open(web.url("/slow?delay_ms=8000"))
        assert raised.value.code == BrowserErrorCode.NAVIGATION_TIMEOUT

    _drive(work, _session(web, tmp_path / "quarantine", navigation_timeout_ms=1000))


@requires_worker
def test_fixture_scenarios_redirects_policy_and_injection_as_data(
    web: Any, tmp_path: Path
) -> None:
    """Redirect chains resolve to the final URL; policy/injection are data."""

    async def work(session: PlaywrightBrowserSession) -> None:
        final = await session.open(web.url("/redirect/a"))
        assert final.url.endswith("/redirect/final")
        assert localweb.REDIRECT_FINAL_MARKER in final.text_excerpt

        denied = await session.open(web.url("/policy-denied"))
        assert denied.http_status == HTTP_FORBIDDEN
        assert localweb.FORBIDDEN_MARKER in denied.text_excerpt

        robots = await session.open(web.url("/robots.txt"))
        assert "Disallow: /private/" in robots.text_excerpt
        private = await session.open(web.url("/private/page"))
        assert localweb.PRIVATE_AREA_MARKER in private.text_excerpt

        await session.open(web.url("/injection"))
        observation = await session.observe(focus="SYSTEM OVERRIDE")
        # Hostile content is observed as DATA inside the excerpt - there is
        # no eval surface it could reach even if it granted itself one. (The
        # literal <system> tag is consumed by the HTML parser; the rendered
        # sentence is the payload that survives as data.)
        payload_sentence = localweb.INJECTION_PAYLOAD.split("SYSTEM OVERRIDE", 1)[1][:60]
        assert f"SYSTEM OVERRIDE{payload_sentence}" in observation.visible_text_excerpt

    _drive(work, _session(web, tmp_path / "quarantine"))


@requires_worker
def test_executor_journey_renders_js_content_after_static_fetch_fails(
    web: Any, tmp_path: Path
) -> None:
    """E2E-008 research leg: fetch fails -> authorized browser fallback -> finish."""
    from milpbooklm_application.research_executor import ResearchRunExecutor
    from milpbooklm_application.retrieval import RetrieveChunks
    from milpbooklm_application.web_fetch import FetchedWebContent, WebFetchCommand
    from milpbooklm_domain.research import ResearchRunStatus, RunMode

    from tests.unit.test_research_executor import (
        FakeImport,
        FakeRetrieval,
        FakeSearch,
        MemoryRunStore,
        RecordingAudit,
        ScriptedPlanner,
        _running_run,
    )

    js_url = web.url("/js-render")

    class StaticFetchInsufficient:
        """The static transport cannot retrieve the JS-rendered content."""

        async def fetch(self, command: WebFetchCommand) -> FetchedWebContent:
            raise RuntimeError(f"static fetch insufficient: {command.url}")

    store = MemoryRunStore()
    planner = ScriptedPlanner(
        [
            {"tool": "web.fetch", "args": {"url": js_url}},
            {"tool": "browser.open", "args": {"url": js_url}},
            {"tool": "browser.observe", "args": {"focus": localweb.JS_RENDERED_MARKER}},
            {"tool": "finish", "args": {"summary": "rendered the JS fixture"}},
        ]
    )
    audit = RecordingAudit()
    session = _session(web, tmp_path / "quarantine")
    executor = ResearchRunExecutor(
        store=store,
        planners={RunMode.SOURCE_DISCOVERY: planner},
        search=FakeSearch(),
        fetch=StaticFetchInsufficient(),
        browser=session,
        imports=FakeImport(),
        retrieval=RetrieveChunks(
            retrieval=FakeRetrieval(), embeddings=None, expected_dimension=None
        ),
        audit=audit,
    )
    run_id = _running_run(store, approved=frozenset({"browser.interact"}))

    async def run() -> None:
        await session.start()
        try:
            outcome = await executor.execute(
                run_id,
                should_stop=lambda: False,
                checkpoint=lambda data: None,
                progress=lambda phase, fraction, status: None,
            )
            assert outcome.run_status is ResearchRunStatus.SUCCEEDED, store.extra_fields[run_id]
            tools = [step.tool_name for step in store.list_steps(run_id) if step.tool_name]
            assert tools == ["web.fetch", "browser.open", "browser.observe"]
            assert len(
                [row for row in store.list_evidence(run_id) if row.origin_tool == "browser.open"]
            ) == 1
            observe_rows = [
                row for row in store.list_evidence(run_id) if row.origin_tool == "browser.observe"
            ]
            assert observe_rows, "the observation must be immutable evidence"
            assert audit.records == []
            assert session.denials() == ()
        finally:
            await session.aclose()

    anyio.run(run)
