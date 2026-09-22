// RSR-01c browser worker (Node side) — the user-space Playwright subprocess.
//
// Driven by milpbooklm_adapters.research.browser_worker over line-delimited
// JSON on stdin/stdout. Security posture (guide/11 "Playwright" + guide/19
// "Upload/browser isolation"):
//
//   * Chromium is the normative research browser, launched with
//     `chromiumSandbox: true` and the full `chromium` channel binary. The
//     startup_check op PROVES the sandbox posture: no `--no-sandbox` argument
//     anywhere in the browser process tree and at least one renderer with
//     NoNewPrivs=1 + Seccomp=2 (kernel seccomp-bpf filter active). Playwright's
//     DEFAULT is an unsandboxed launch (chromiumSandbox defaults to false and
//     silently injects --no-sandbox) — this worker never does that, and if the
//     environment cannot provide a sandboxed launch it fails honestly instead.
//   * One disposable context per worker process (= per research session):
//     no storage state, no inherited credentials, closed (with the browser)
//     on the close op.
//   * Every context request passes a route guard that refuses private /
//     loopback / link-local / metadata destinations BEFORE the connection,
//     using the address tables handed over by the Python side (the same
//     tables the SSRF-hardened static fetch uses — single source of truth).
//     Hostnames are resolved and refused when ANY candidate address is
//     non-public (DNS-rebinding defense). Explicitly allowed origins (a
//     per-deployment configuration, empty by default) are the only exemption.
//   * Downloads are accepted only into a quarantine directory with a size
//     limit, never auto-trusted, and are reported back for the normal
//     ingestion controls. The size cap is enforced post-completion (Playwright
//     exposes no transfer-progress hook): oversized artifacts are deleted and
//     refused.
//
// There is deliberately no evaluate-style op in the protocol surface: open /
// observe / interact are structured operations. The two internal evaluate
// calls use fixed expressions (text extraction) and never touch model input.

import { createRequire } from "node:module";
import {
  existsSync,
  mkdirSync,
  copyFileSync,
  unlinkSync,
  readdirSync,
  readFileSync,
  statSync,
} from "node:fs";
import { createInterface } from "node:readline";
import { lookup } from "node:dns/promises";
import path from "node:path";

const MAX_TEXT_EXCERPT = 4000;
const MAX_FOCUS_EXCERPT = 400;
const MAX_TITLE = 500;
const MAX_SELECTOR_CHARS = 512;
const GESTURES = new Set(["click", "type", "scroll", "press"]);
const GESTURE_TIMEOUT_MS = 10_000;
const V4_MAPPED_LOW = 0xffff00000000n; // ::ffff:0:0/96 low — embedded IPv4
const V4_MAPPED_HIGH = 0xffffffffffffn; // ::ffff:255.255.255.255

class WorkerFailure extends Error {
  constructor(code, detail) {
    super(detail);
    this.code = code;
    this.detail = detail;
  }
}

function clip(text, limit) {
  const value = String(text ?? "");
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

function sanitizeFilename(name) {
  const base = path.basename(String(name ?? "download"));
  const safe = base.replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 128);
  return safe.length > 0 ? safe : "download";
}

function normalizeOrigin(candidate) {
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    const host = parsed.hostname.toLowerCase();
    const port =
      parsed.port === "" ? (parsed.protocol === "https:" ? "443" : "80") : parsed.port;
    return `${parsed.protocol}//${host}:${port}`;
  } catch {
    return null;
  }
}

// ---------- playwright resolution (no hardcoded machine paths) -------------

function resolvePlaywright() {
  const candidates = [];
  if (process.env.MILPBOOKLM_PLAYWRIGHT_ROOT) {
    candidates.push(process.env.MILPBOOKLM_PLAYWRIGHT_ROOT);
  }
  for (const root of [path.dirname(new URL(import.meta.url).pathname), process.cwd()]) {
    let dir = root;
    for (let i = 0; i < 12; i += 1) {
      candidates.push(dir);
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  for (const dir of candidates) {
    const manifest = path.join(dir, "node_modules", "playwright", "package.json");
    if (existsSync(manifest)) {
      const require = createRequire(path.join(dir, "package.json"));
      return require("playwright");
    }
  }
  throw new WorkerFailure(
    "playwright_unresolvable",
    "no node_modules/playwright under MILPBOOKLM_PLAYWRIGHT_ROOT or any worker-script ancestor",
  );
}

// ---------- address tables (Python-owned policy, JS-side matching) ---------

function parseIpv6(text) {
  // Standard expansion (RFC 4291) incl. embedded IPv4 tails; BigInt or null.
  const bare = text.replace(/^\[|\]$/g, "");
  const first = bare.indexOf("::");
  let head = bare;
  let tail = "";
  if (first >= 0) {
    if (bare.indexOf("::", first + 1) >= 0) return null;
    head = bare.slice(0, first);
    tail = bare.slice(first + 2);
  }
  const expand = (chunk) => {
    if (chunk === "") return [];
    const groups = chunk.split(":");
    const last = groups[groups.length - 1];
    if (last.includes(".")) {
      const parts = last.split(".");
      if (parts.length !== 4 || !parts.every((p) => /^\d{1,3}$/.test(p) && Number(p) <= 255)) {
        return null;
      }
      groups.pop();
      groups.push(String((Number(parts[0]) << 8) | Number(parts[1])));
      groups.push(String((Number(parts[2]) << 8) | Number(parts[3])));
    }
    const values = [];
    for (const group of groups) {
      if (!/^[0-9a-fA-F]{1,4}$/.test(group)) return null;
      values.push(parseInt(group, 16));
    }
    return values;
  };
  const headGroups = expand(head);
  const tailGroups = expand(tail);
  if (headGroups === null || tailGroups === null) return null;
  const missing = 8 - headGroups.length - tailGroups.length;
  if (first < 0 && missing !== 0) return null;
  if (first >= 0 && missing < 0) return null;
  const groups = [
    ...headGroups,
    ...new Array(Math.max(missing, 0)).fill(0),
    ...tailGroups,
  ];
  let value = 0n;
  for (const group of groups) value = (value << 16n) | BigInt(group);
  return value;
}

function parseIpv4(text) {
  const parts = text.split(".");
  if (parts.length !== 4 || !parts.every((p) => /^\d{1,3}$/.test(p) && Number(p) <= 255)) {
    return null;
  }
  return parts.reduce((acc, part) => acc * 256 + Number(part), 0);
}

class AddressTables {
  constructor(v4Ranges, v6Ranges) {
    // v4 ranges arrive as JSON numbers (< 2^32); v6 as decimal strings
    // because IPv6 integers exceed Number.MAX_SAFE_INTEGER.
    this.v4 = v4Ranges.map((r) => ({ start: r[0], end: r[1], reason: r[2] }));
    this.v6 = v6Ranges.map((r) => ({ start: BigInt(r[0]), end: BigInt(r[1]), reason: r[2] }));
  }

  classifyLiteral(host) {
    const bare = host.replace(/^\[|\]$/g, "");
    if (bare.includes(":")) {
      const value = parseIpv6(bare);
      if (value === null) return "unparseable_address";
      if (value >= V4_MAPPED_LOW && value <= V4_MAPPED_HIGH) {
        // IPv4-mapped form: classify the embedded v4 (T22 parity).
        return this.classifyV4Number(Number(value & 0xffffffffn));
      }
      for (const range of this.v6) {
        if (value >= range.start && value <= range.end) return range.reason;
      }
      return null;
    }
    const value = parseIpv4(bare);
    if (value === null) return "unparseable_address";
    return this.classifyV4Number(value);
  }

  classifyV4Number(value) {
    for (const range of this.v4) {
      if (value >= range.start && value <= range.end) return range.reason;
    }
    return null;
  }

  async classifyHost(host) {
    const bare = host.replace(/^\[|\]$/g, "");
    const literalShape = /^[\d.]+$/.test(bare) || bare.includes(":");
    if (literalShape) return this.classifyLiteral(bare) ?? "unparseable_address"; // fail closed
    let answers;
    try {
      answers = await lookup(host, { all: true });
    } catch {
      return "no_address";
    }
    if (answers.length === 0) return "no_address";
    for (const answer of answers) {
      const reason = this.classifyLiteral(answer.address);
      if (reason !== null) return reason;
    }
    return null;
  }
}

// ---------- process-tree sandbox probe --------------------------------------

function processTree(rootPid) {
  const byParent = new Map();
  for (const entry of readdirSync("/proc")) {
    if (!/^\d+$/.test(entry)) continue;
    try {
      const stat = readFileSync(`/proc/${entry}/stat`, "utf8");
      const after = stat.slice(stat.lastIndexOf(")") + 2);
      const ppid = Number(after.split(" ")[1]);
      if (!byParent.has(ppid)) byParent.set(ppid, []);
      byParent.get(ppid).push(Number(entry));
    } catch {}
  }
  const rows = [];
  const stack = [rootPid];
  while (stack.length) {
    const current = stack.pop();
    for (const child of byParent.get(current) ?? []) {
      rows.push(child);
      stack.push(child);
    }
  }
  return rows;
}

function chromeProcessRows() {
  const rows = [];
  for (const pid of processTree(process.pid)) {
    try {
      const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").filter(Boolean);
      if (cmdline.length === 0) continue;
      const args = cmdline.slice(1);
      const isChrome = /chrome|headless_shell/i.test(cmdline[0]) || args.includes("--headless");
      if (!isChrome) continue;
      const status = readFileSync(`/proc/${pid}/status`, "utf8");
      rows.push({
        pid,
        type: args.find((a) => a.startsWith("--type="))?.slice(7) ?? "browser",
        noSandbox: args.includes("--no-sandbox"),
        noNewPrivs: Number(status.match(/^NoNewPrivs:\s+(\d+)/m)?.[1] ?? 0),
        seccomp: Number(status.match(/^Seccomp:\s+(\d+)/m)?.[1] ?? 0),
      });
    } catch {}
  }
  return rows;
}

// ---------- session ----------------------------------------------------------

class Session {
  constructor(config) {
    this.config = config;
    this.tables = new AddressTables(config.v4Ranges, config.v6Ranges);
    this.allowedOrigins = new Set(
      config.allowedOrigins.map(normalizeOrigin).filter((origin) => origin !== null),
    );
    this.denials = [];
    this.downloads = [];
    this.capturedDownloads = new WeakSet();
    this.browser = null;
    this.context = null;
    this.page = null;
    this.quarantineCounter = 0;
  }

  async start() {
    this.playwright = resolvePlaywright();
    // chromiumSandbox: true is the whole point — the launch REFUSES to fall
    // back to --no-sandbox; an environment that cannot sandbox fails honestly.
    this.browser = await this.playwright.chromium.launch({
      headless: true,
      chromiumSandbox: true,
      channel: "chromium",
    });
  }

  async startupCheck() {
    if (!this.browser) throw new WorkerFailure("worker_not_started", "browser not launched");
    const probeContext = await this.browser.newContext();
    const probePage = await probeContext.newPage();
    await probePage.goto("data:text/html,<h1>sandbox-probe</h1>");
    await probePage.evaluate(() => 1); // force a live renderer
    const rows = chromeProcessRows();
    await probeContext.close();
    const noSandboxAnywhere = rows.some((row) => row.noSandbox);
    // Chromium rewrites child argv (--type is consumed), so the kernel proof is
    // the discriminator: NoNewPrivs=1 + Seccomp=2 exists ONLY on sandboxed
    // renderers — an unsandboxed (--no-sandbox) launch shows Seccomp=0 on
    // every process (verified empirically against both launch modes).
    const sandboxedRenderers = rows.filter((row) => row.noNewPrivs === 1 && row.seccomp === 2);
    const posture = {
      chromiumVersion: this.browser.version(),
      processCount: rows.length,
      noSandboxArgs: noSandboxAnywhere,
      sandboxedRenderers: sandboxedRenderers.length,
      probe: rows.slice(0, 6).map((row) => ({
        type: row.type,
        noNewPrivs: row.noNewPrivs,
        seccomp: row.seccomp,
      })),
    };
    if (noSandboxAnywhere || sandboxedRenderers.length === 0) {
      throw new WorkerFailure("sandbox_posture_violated", JSON.stringify(posture));
    }
    return posture;
  }

  originAllowed(url) {
    return this.allowedOrigins.has(normalizeOrigin(url));
  }

  async routeGuard(route) {
    const url = route.request().url();
    let host = "unknown";
    try {
      const parsed = new URL(url);
      host = parsed.hostname;
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        await route.continue();
        return;
      }
      if (this.originAllowed(url)) {
        await route.continue();
        return;
      }
      const reason = await this.tables.classifyHost(parsed.hostname);
      if (reason !== null) {
        this.denials.push({ host, reason, url, phase: "route" });
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    } catch (error) {
      // Never let a guard bug open a hole: abort on unexpected failure.
      this.denials.push({
        host,
        reason: `guard_error:${clip(String(error), 80)}`,
        url,
        phase: "route",
      });
      try {
        await route.abort("blockedbyclient");
      } catch {}
    }
  }

  async ensureContext() {
    if (this.context) return;
    // One disposable context per worker process: clean profile, no storage
    // state, no inherited credentials. Downloads accepted (into quarantine).
    this.context = await this.browser.newContext({ acceptDownloads: true });
    this.context.setDefaultNavigationTimeout(this.config.navigationTimeoutMs);
    this.context.setDefaultTimeout(this.config.navigationTimeoutMs);
    await this.context.route("**/*", (route) => this.routeGuard(route));
    this.context.on("download", (download) => this.captureDownload(download));
    this.page = await this.context.newPage();
  }

  async captureDownload(download) {
    if (this.capturedDownloads.has(download)) return;
    this.capturedDownloads.add(download);
    try {
      const name = sanitizeFilename(download.suggestedFilename());
      // download.path() resolves when the artifact is complete; the size cap
      // is enforced post-completion (no transfer-progress hook exists).
      const staged = await download.path();
      const size = staged ? statSync(staged).size : 0;
      if (size > this.config.downloadLimitBytes) {
        if (staged) unlinkSync(staged);
        this.downloads.push({
          state: "refused",
          reason: "download_limit_exceeded",
          name,
          sizeBytes: size,
          limitBytes: this.config.downloadLimitBytes,
        });
        await download.cancel().catch(() => {});
        return;
      }
      mkdirSync(this.config.quarantineDir, { recursive: true });
      this.quarantineCounter += 1;
      const target = path.join(
        this.config.quarantineDir,
        `${Date.now()}-${this.quarantineCounter}-${name}`,
      );
      if (staged) {
        copyFileSync(staged, target);
        unlinkSync(staged);
      }
      this.downloads.push({ state: "quarantined", name, path: target, sizeBytes: size });
    } catch (error) {
      this.downloads.push({
        state: "refused",
        reason: "download_capture_failed",
        name: sanitizeFilename(download.suggestedFilename()),
        detail: clip(String(error), 160),
      });
    }
  }

  async open(url) {
    await this.ensureContext();
    // Main-frame downloads need a concurrent page-level waiter (empirically
    // the context "download" event alone never fires for them); the waiter
    // times out silently for normal navigations.
    const downloadWaiter = this.page
      .waitForEvent("download", { timeout: this.config.navigationTimeoutMs + 5000 })
      .then((download) => this.captureDownload(download))
      .catch(() => {});
    try {
      const response = await this.page.goto(url, { waitUntil: "load" });
      // The waiter is intentionally NOT awaited here: normal navigations
      // must not pay its timeout.
      return {
        url: this.page.url(),
        title: clip(await this.page.title(), MAX_TITLE),
        textExcerpt: clip(await visibleText(this.page), MAX_TEXT_EXCERPT),
        httpStatus: response ? response.status() : null,
      };
    } catch (error) {
      const message = String(error);
      if (message.includes("Download is starting")) {
        // Navigation became a download: the waiter quarantines it; report
        // the capture instead of a navigation result.
        await this.downloadSettles();
        await downloadWaiter;
        const captured = this.downloads[this.downloads.length - 1] ?? null;
        if (captured && captured.state === "quarantined") {
          return {
            url,
            title: `download:${captured.name}`,
            textExcerpt: `download captured to quarantine (${captured.sizeBytes} bytes)`,
            httpStatus: null,
          };
        }
        throw new WorkerFailure(
          captured
            ? (captured.reason ?? `download_${captured.state}`)
            : "download_capture_failed",
          captured ? JSON.stringify(captured) : "download never completed",
        );
      }
      if (message.includes("Timeout") || message.includes("timeout")) {
        throw new WorkerFailure(
          "navigation_timeout",
          `navigation to ${url} exceeded ${this.config.navigationTimeoutMs}ms`,
        );
      }
      throw new WorkerFailure("navigation_failed", clip(message, 200));
    }
  }

  async downloadSettles() {
    for (let i = 0; i < 200; i += 1) {
      if (this.downloads.length > 0) return;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }

  async observe(focus) {
    await this.ensureContext();
    const text = await visibleText(this.page);
    let focused = null;
    if (focus) {
      const index = text.toLowerCase().indexOf(focus.toLowerCase());
      if (index >= 0) {
        const start = Math.max(0, index - Math.floor(MAX_FOCUS_EXCERPT / 2));
        focused = clip(text.slice(start, start + MAX_FOCUS_EXCERPT), MAX_FOCUS_EXCERPT);
      }
    }
    return {
      url: this.page.url(),
      title: clip(await this.page.title(), MAX_TITLE),
      visibleTextExcerpt: clip(text, MAX_TEXT_EXCERPT),
      focused,
    };
  }

  async interact(gesture, selector, value) {
    if (!GESTURES.has(gesture)) throw new WorkerFailure("unknown_gesture", gesture);
    if (
      typeof selector !== "string" ||
      selector.length === 0 ||
      selector.length > MAX_SELECTOR_CHARS
    ) {
      throw new WorkerFailure("invalid_selector", "selector must be 1..512 chars");
    }
    if (gesture === "type" && typeof value !== "string") {
      throw new WorkerFailure("missing_value", "type gesture requires a value");
    }
    await this.ensureContext();
    const locator = this.page.locator(selector);
    try {
      if (gesture === "click") await locator.click({ timeout: GESTURE_TIMEOUT_MS });
      else if (gesture === "type") await locator.fill(value, { timeout: GESTURE_TIMEOUT_MS });
      else if (gesture === "scroll")
        await locator.scrollIntoViewIfNeeded({ timeout: GESTURE_TIMEOUT_MS });
      else await locator.press(value ?? "Enter", { timeout: GESTURE_TIMEOUT_MS });
    } catch (error) {
      throw new WorkerFailure("gesture_failed", clip(String(error), 200));
    }
    const text = await visibleText(this.page);
    return {
      url: this.page.url(),
      title: clip(await this.page.title(), MAX_TITLE),
      visibleTextExcerpt: clip(text, MAX_TEXT_EXCERPT),
      focused: null,
    };
  }

  async close() {
    if (this.context) {
      await this.context.close().catch(() => {});
      this.context = null;
      this.page = null;
    }
    if (this.browser) {
      await this.browser.close().catch(() => {});
      this.browser = null;
    }
  }
}

async function visibleText(page) {
  // Fixed extraction expression (never model-controllable input).
  return page.evaluate(() => (document.body ? document.body.innerText : ""));
}

// ---------- stdio protocol --------------------------------------------------

let session = null;

function writeMessage(message) {
  // Denials and download events ride along on every response so nothing is
  // lost between ops; Python drains and logs them.
  if (session) {
    message.denials = session.denials;
    session.denials = [];
    message.downloads = session.downloads;
    session.downloads = [];
  }
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

async function handleMessage(message) {
  if (message.init) {
    if (session) throw new WorkerFailure("already_initialized", "init received twice");
    session = new Session(message.init);
    await session.start();
    writeMessage({ id: message.id ?? 0, ok: true });
    return;
  }
  if (!session) throw new WorkerFailure("not_initialized", "init message missing");
  const { id, op } = message;
  if (op === "startup_check") {
    writeMessage({ id, ok: true, result: await session.startupCheck() });
  } else if (op === "open") {
    writeMessage({ id, ok: true, result: await session.open(message.url) });
  } else if (op === "observe") {
    writeMessage({ id, ok: true, result: await session.observe(message.focus ?? null) });
  } else if (op === "interact") {
    writeMessage({
      id,
      ok: true,
      result: await session.interact(message.gesture, message.selector, message.value ?? null),
    });
  } else if (op === "close") {
    await session.close();
    writeMessage({ id, ok: true });
    process.exit(0);
  } else {
    throw new WorkerFailure("unknown_op", String(op));
  }
}

const lines = createInterface({ input: process.stdin });
lines.on("line", (line) => {
  const trimmed = line.trim();
  if (trimmed === "") return;
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    writeMessage({ id: -1, ok: false, code: "protocol_error", detail: "unparseable line" });
    return;
  }
  handleMessage(message).catch((error) => {
    const code = error instanceof WorkerFailure ? error.code : "worker_error";
    writeMessage({
      id: message?.id ?? -1,
      ok: false,
      code,
      detail: clip(error instanceof WorkerFailure ? error.detail : String(error), 300),
    });
    if (code === "sandbox_posture_violated" || code === "playwright_unresolvable") {
      process.exit(3);
    }
  });
});

process.stdin.on("close", () => {
  // Python went away: dispose and exit (only our own tree is torn down).
  if (session) session.close().catch(() => process.exit(0));
  else process.exit(0);
});
