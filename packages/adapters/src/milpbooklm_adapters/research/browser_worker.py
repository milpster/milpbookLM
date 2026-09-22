"""
User-space Playwright browser worker (RSR-01c, guide/11 + guide/19).

The worker form in the plan is a rootless container with a version-matched
Chromium image; containers are not deployable on this host yet (T8 class,
recorded deferral), so this module delivers the USER-SPACE form: a Node
subprocess running :data:`WORKER_SCRIPT` (Playwright is installed for the
product E2E harness) driven over a line-JSON stdio protocol.

Posture, enforced here and asserted by tests:

* sandbox-first startup: :meth:`PlaywrightBrowserSession.start` launches the
  worker and runs the ``startup_check`` op which PROVES the Chromium sandbox
  posture (no ``--no-sandbox`` argument anywhere in the browser process tree
  and renderers running with ``NoNewPrivs=1`` + ``Seccomp=2``). Playwright's
  own default launch silently injects ``--no-sandbox`` — this worker never
  does, and a failed proof refuses the session instead of weakening it;
* disposable contexts: one clean context per session (no storage state, no
  inherited credentials), disposed on close;
* private networks blocked at the worker: the address tables of the
  SSRF-hardened static fetch (:mod:`milpbooklm_adapters.fetch.addressing`)
  are handed to the subprocess and enforced per request BEFORE the
  connection; :meth:`PlaywrightBrowserSession.open` additionally validates
  the navigation target in-process (same tables, resolve-all-candidates
  rebinding defense);
* downloads return via quarantine: a bounded quarantine directory consumed
  by the normal ingestion controls, size-capped, never auto-trusted;
* loopback is BLOCKED in the production posture. Tests that need the local
  fixture origin pass it in ``allowed_origins`` — an explicit per-deployment
  exemption that is empty by default; private ranges stay blocked either way.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import anyio
from anyio.abc import ByteSendStream, Process
from anyio.streams.buffered import BufferedByteReceiveStream
from milpbooklm_application.research_browser import (
    BrowserErrorCode,
    BrowserGestureCommand,
    BrowserObservation,
    BrowserPage,
    BrowserUnavailableError,
)

from milpbooklm_adapters.fetch.addressing import (
    _IPV4_BLOCKED,
    _IPV6_BLOCKED,
    SSRFBlockedError,
    _v4_reason,
    _v6_reason,
    select_pinned_address,
)

logger = logging.getLogger(__name__)

WORKER_SCRIPT = Path(__file__).with_name("browser_worker.mjs")
DEFAULT_DOWNLOAD_LIMIT_BYTES = 10 * 1024 * 1024  # same default cap as acquisition
DEFAULT_NAVIGATION_TIMEOUT_MS = 15_000
STARTUP_TIMEOUT_S = 45.0
OP_MARGIN_S = 15.0  # worker-side navigation timeout plus RPC margin
MAX_SELECTOR_CHARS = 512
_MAX_LINE_BYTES = 8 * 1024 * 1024

_CODE_MAP: dict[str, str] = {
    "sandbox_posture_violated": BrowserErrorCode.SANDBOX_POSTURE_VIOLATED,
    "playwright_unresolvable": BrowserErrorCode.SANDBOX_UNAVAILABLE,
    "navigation_timeout": BrowserErrorCode.NAVIGATION_TIMEOUT,
    "download_limit_exceeded": BrowserErrorCode.DOWNLOAD_LIMIT_EXCEEDED,
    "download_refused": BrowserErrorCode.DOWNLOAD_REFUSED,
    "download_capture_failed": BrowserErrorCode.DOWNLOAD_REFUSED,
    "gesture_failed": BrowserErrorCode.GESTURE_FAILED,
    "invalid_selector": BrowserErrorCode.GESTURE_FAILED,
    "missing_value": BrowserErrorCode.GESTURE_FAILED,
    "unknown_gesture": BrowserErrorCode.UNSUPPORTED,
    "worker_error": BrowserErrorCode.WORKER_FAILURE,
    "protocol_error": BrowserErrorCode.WORKER_FAILURE,
    "not_initialized": BrowserErrorCode.WORKER_FAILURE,
    "worker_not_started": BrowserErrorCode.WORKER_FAILURE,
    "unknown_op": BrowserErrorCode.UNSUPPORTED,
}


@dataclass(frozen=True, slots=True)
class SandboxPosture:
    """Kernel-level proof of the Chromium sandbox posture."""

    chromium_version: str
    no_sandbox_args: bool
    sandboxed_renderers: int
    probe: tuple[dict[str, int], ...]

    def proven(self) -> bool:
        """Return whether the proof holds: never --no-sandbox, seccomp on."""
        return not self.no_sandbox_args and self.sandboxed_renderers > 0


@dataclass(frozen=True, slots=True)
class WorkerDenial:
    """One route-level refusal observed inside the browser context."""

    host: str
    reason: str
    url: str
    phase: str


@dataclass(frozen=True, slots=True)
class QuarantinedDownload:
    """One download captured into the quarantine hand-off."""

    name: str
    path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _DownloadEvent:
    """Raw worker download report (quarantined or refused)."""

    state: str
    name: str
    path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BrowserWorkerConfig:
    """Deployment configuration of one browser worker session."""

    quarantine_dir: Path
    download_limit_bytes: int = DEFAULT_DOWNLOAD_LIMIT_BYTES
    navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS
    allowed_origins: tuple[str, ...] = ()
    node_binary: str = "node"
    playwright_root: str | None = None
    startup_timeout_s: float = STARTUP_TIMEOUT_S


@dataclass
class _WorkerState:
    """Mutable bookkeeping of one live subprocess."""

    process: Process | None = None
    stdin: ByteSendStream | None = None
    stdout: BufferedByteReceiveStream | None = None
    next_id: int = 0
    posture: SandboxPosture | None = None
    denials: list[WorkerDenial] = field(default_factory=list)
    downloads: list[_DownloadEvent] = field(default_factory=list)


class PlaywrightBrowserSession:
    """
    BrowserSessionPort backed by the sandboxed Playwright worker subprocess.

    One instance = one research session = one disposable Chromium context.
    The subprocess launches lazily on first use and its startup proves the
    sandbox posture; every refusal is a typed ``BrowserUnavailableError``
    the executor records as evidence.
    """

    def __init__(self, config: BrowserWorkerConfig) -> None:
        """Bind the worker configuration (nothing is spawned yet)."""
        self._config = config
        self._state = _WorkerState()
        self._allowed = {
            origin
            for origin in (_origin_of(url) for url in config.allowed_origins)
            if origin is not None
        }

    async def start(self) -> SandboxPosture:
        """Spawn the worker, prove the sandbox posture, and return it."""
        if self._state.posture is not None:
            return self._state.posture
        if shutil.which(self._config.node_binary) is None:
            raise BrowserUnavailableError(
                BrowserErrorCode.SANDBOX_UNAVAILABLE,
                "node runtime not found for the browser worker",
            )
        env = dict(os.environ)
        if self._config.playwright_root is not None:
            env["MILPBOOKLM_PLAYWRIGHT_ROOT"] = self._config.playwright_root
        self._config.quarantine_dir.mkdir(parents=True, exist_ok=True)
        process = await anyio.open_process(
            [self._config.node_binary, str(WORKER_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        state = self._state
        if process.stdin is None or process.stdout is None:  # PIPE was requested
            process.kill()
            raise BrowserUnavailableError(
                BrowserErrorCode.WORKER_FAILURE, "browser worker stdio pipes missing"
            )
        state.process = process
        state.stdin = process.stdin
        state.stdout = BufferedByteReceiveStream(process.stdout)
        await self._rpc(
            {
                "init": {
                    "quarantineDir": str(self._config.quarantine_dir),
                    "downloadLimitBytes": self._config.download_limit_bytes,
                    "navigationTimeoutMs": self._config.navigation_timeout_ms,
                    "allowedOrigins": list(self._config.allowed_origins),
                    "v4Ranges": _v4_ranges(),
                    "v6Ranges": _v6_ranges(),
                }
            },
            timeout=self._config.startup_timeout_s,
        )
        posture_body = await self._rpc(
            {"id": self._next_id(), "op": "startup_check"},
            timeout=self._config.startup_timeout_s,
        )
        posture = _parse_posture(posture_body)
        if not posture.proven():
            await self.aclose()
            raise BrowserUnavailableError(
                BrowserErrorCode.SANDBOX_POSTURE_VIOLATED,
                f"sandbox posture proof failed: {posture_body.get('result')}",
            )
        self._state.posture = posture
        logger.info(
            "browser worker started: chromium=%s sandboxed_renderers=%d no_sandbox_args=%s",
            posture.chromium_version,
            posture.sandboxed_renderers,
            posture.no_sandbox_args,
        )
        return posture

    @property
    def posture(self) -> SandboxPosture | None:
        """The proven startup posture (None until the worker started)."""
        return self._state.posture

    def denials(self) -> tuple[WorkerDenial, ...]:
        """Route-level refusals observed so far (the denial log)."""
        return tuple(self._state.denials)

    def quarantined_downloads(self) -> tuple[QuarantinedDownload, ...]:
        """Return downloads captured into quarantine (never auto-trusted)."""
        return tuple(
            QuarantinedDownload(name=event.name, path=event.path, size_bytes=event.size_bytes)
            for event in self._state.downloads
            if event.state == "quarantined"
        )

    def refused_downloads(self) -> tuple[_DownloadEvent, ...]:
        """Download attempts the worker refused (size cap, capture failure)."""
        return tuple(event for event in self._state.downloads if event.state != "quarantined")

    async def open(self, url: str) -> BrowserPage:
        """Navigate the session's disposable context to one validated URL."""
        self._validate_navigation_target(url)
        body = await self._op(
            {"op": "open", "url": url},
            timeout=self._config.navigation_timeout_ms / 1000 + OP_MARGIN_S,
        )
        status = body.get("httpStatus")
        return BrowserPage(
            url=str(body["url"]),
            title=str(body["title"]),
            text_excerpt=str(body["textExcerpt"]),
            http_status=status if isinstance(status, int) else None,
        )

    async def observe(self, focus: str | None = None) -> BrowserObservation:
        """Read a structured observation of the current page."""
        body = await self._op({"op": "observe", "focus": focus}, timeout=OP_MARGIN_S)
        focused = body.get("focused")
        return BrowserObservation(
            url=str(body["url"]),
            title=str(body["title"]),
            visible_text_excerpt=str(body["visibleTextExcerpt"]),
            focused_excerpt=str(focused) if focused is not None else None,
        )

    async def interact(self, command: BrowserGestureCommand) -> BrowserObservation:
        """Apply one constrained gesture on the current page."""
        if not command.selector.strip() or len(command.selector) > MAX_SELECTOR_CHARS:
            raise BrowserUnavailableError(
                BrowserErrorCode.GESTURE_FAILED, "selector must be 1..512 chars"
            )
        body = await self._op(
            {
                "op": "interact",
                "gesture": command.gesture,
                "selector": command.selector,
                "value": command.value,
            },
            timeout=OP_MARGIN_S,
        )
        return BrowserObservation(
            url=str(body["url"]),
            title=str(body["title"]),
            visible_text_excerpt=str(body["visibleTextExcerpt"]),
        )

    async def aclose(self) -> None:
        """Dispose the context, stop the subprocess, and reap it."""
        state = self._state
        process = state.process
        if process is None:
            return
        if process.returncode is None and state.stdin is not None:
            # Teardown must never raise: the worker may already be gone.
            with contextlib.suppress(Exception):
                await self._rpc(
                    {"id": self._next_id(), "op": "close"},
                    timeout=10.0,
                    drain=False,
                )
        if state.stdin is not None:
            await state.stdin.aclose()
        if process.returncode is None:
            process.terminate()
            with anyio.move_on_after(5):
                await process.wait()
        if process.returncode is None:
            process.kill()
            await process.wait()
        state.process = None
        state.stdin = None
        state.stdout = None

    # -- internals ----------------------------------------------------------

    def _validate_navigation_target(self, url: str) -> None:
        """Pre-connect validation of the navigation target (T22 tables)."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise BrowserUnavailableError(
                BrowserErrorCode.ADDRESS_BLOCKED, f"only http(s) navigation is allowed: {url!r}"
            )
        host = parts.hostname
        if not host:
            raise BrowserUnavailableError(
                BrowserErrorCode.ADDRESS_BLOCKED, f"navigation target has no host: {url!r}"
            )
        if _origin_of(url) in self._allowed:
            return
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            select_pinned_address(host, port)
        except SSRFBlockedError as exc:
            self._state.denials.append(
                WorkerDenial(host=host, reason=exc.reason, url=url, phase="navigate")
            )
            logger.warning(
                "browser navigation denied: host=%s reason=%s url=%s", host, exc.reason, url
            )
            raise BrowserUnavailableError(
                BrowserErrorCode.ADDRESS_BLOCKED, f"{host}: {exc.reason}"
            ) from exc

    async def _op(self, payload: dict[str, object], *, timeout: float) -> dict[str, object]:
        """Run one op on a started worker and return its result body."""
        if self._state.posture is None or self._state.process is None:
            raise BrowserUnavailableError(
                BrowserErrorCode.WORKER_FAILURE, "browser worker not started"
            )
        message = dict(payload, id=self._next_id())
        body = await self._rpc(message, timeout=timeout)
        result = body.get("result")
        return dict(result) if isinstance(result, dict) else {}

    def _next_id(self) -> int:
        self._state.next_id += 1
        return self._state.next_id

    async def _rpc(
        self,
        message: dict[str, object],
        *,
        timeout: float,
        drain: bool = True,
    ) -> dict[str, object]:
        """Write one line, read one response, drain events, map failures."""
        state = self._state
        if state.stdin is None or state.stdout is None or state.process is None:
            raise BrowserUnavailableError(
                BrowserErrorCode.WORKER_FAILURE, "browser worker not running"
            )
        line = json.dumps(message, ensure_ascii=True) + "\n"
        try:
            with anyio.fail_after(timeout):
                await state.stdin.send(line.encode())
                raw = await state.stdout.receive_until(b"\n", max_bytes=_MAX_LINE_BYTES)
        except TimeoutError as exc:
            raise BrowserUnavailableError(
                BrowserErrorCode.WORKER_FAILURE,
                f"browser worker timed out on {message.get('op') or 'init'}",
            ) from exc
        except (BrokenPipeError, anyio.BrokenResourceError) as exc:
            detail = await _stderr_tail(state.process)
            raise BrowserUnavailableError(BrowserErrorCode.WORKER_FAILURE, detail) from exc
        try:
            response: dict[str, object] = dict(json.loads(raw.decode()))
        except ValueError as exc:
            raise BrowserUnavailableError(
                BrowserErrorCode.WORKER_FAILURE, "browser worker sent unparseable output"
            ) from exc
        if drain:
            _drain_events(state, response)
        if not response.get("ok"):
            code = _CODE_MAP.get(str(response.get("code")), BrowserErrorCode.WORKER_FAILURE)
            raise BrowserUnavailableError(code, str(response.get("detail", "worker failure")))
        return response


def _drain_events(state: _WorkerState, response: dict[str, object]) -> None:
    """Record route denials and download events carried by a response."""
    denials = response.get("denials")
    if isinstance(denials, list):
        for denial in denials:
            if isinstance(denial, dict):
                entry = WorkerDenial(
                    host=str(denial.get("host", "unknown")),
                    reason=str(denial.get("reason", "unknown")),
                    url=str(denial.get("url", "")),
                    phase=str(denial.get("phase", "route")),
                )
                state.denials.append(entry)
                logger.warning(
                    "browser worker denied request: host=%s reason=%s url=%s",
                    entry.host,
                    entry.reason,
                    entry.url,
                )
    downloads = response.get("downloads")
    if isinstance(downloads, list):
        for download in downloads:
            if isinstance(download, dict):
                event = _DownloadEvent(
                    state=str(download.get("state", "refused")),
                    name=str(download.get("name", "download")),
                    path=str(download.get("path", "")),
                    size_bytes=int(download.get("sizeBytes", 0)),
                )
                state.downloads.append(event)
                logger.info(
                    "browser download %s: name=%s size=%s",
                    event.state,
                    event.name,
                    event.size_bytes,
                )


def _parse_posture(body: dict[str, object]) -> SandboxPosture:
    result = body.get("result")
    if not isinstance(result, dict):
        return SandboxPosture("unknown", no_sandbox_args=True, sandboxed_renderers=0, probe=())
    probe_raw = result.get("probe")
    probe = tuple(
        {"noNewPrivs": int(item.get("noNewPrivs", 0)), "seccomp": int(item.get("seccomp", 0))}
        for item in (probe_raw if isinstance(probe_raw, list) else [])
        if isinstance(item, dict)
    )
    return SandboxPosture(
        chromium_version=str(result.get("chromiumVersion", "unknown")),
        no_sandbox_args=bool(result.get("noSandboxArgs", True)),
        sandboxed_renderers=int(result.get("sandboxedRenderers", 0)),
        probe=probe,
    )


def _v4_ranges() -> list[list[object]]:
    """Export the T22 IPv4 block tables as [start, end, reason] rows."""
    return [
        [
            int(network.network_address),
            int(network.broadcast_address),
            _v4_reason(network.network_address),
        ]
        for network in _IPV4_BLOCKED
    ]


def _v6_ranges() -> list[list[object]]:
    """Export the T22 IPv6 block tables as [start, end, reason] decimal strings."""
    return [
        [
            str(int(network.network_address)),
            str(int(network.broadcast_address)),
            _v6_reason(network.network_address),
        ]
        for network in _IPV6_BLOCKED
    ]


def _origin_of(url: str) -> str | None:
    """Normalize an http(s) URL to its origin (host lowercased, port filled)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return f"{parts.scheme}://{host}:{port}"


async def _stderr_tail(process: Process) -> str:
    """Best-effort stderr read for worker-crash diagnostics."""
    if process.stderr is None:
        return "browser worker exited unexpectedly (stderr not captured)"
    chunks: list[bytes] = []
    with anyio.move_on_after(0.5):
        while sum(len(chunk) for chunk in chunks) < 64 * 1024:
            chunks.append(await process.stderr.receive())
    if not chunks:
        return "browser worker exited unexpectedly (empty stderr)"
    tail = b"".join(chunks).decode(errors="replace").splitlines()[-20:]
    return "browser worker exited unexpectedly: " + " | ".join(tail)
