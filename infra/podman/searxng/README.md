# SearXNG — pinned private discovery service (RSR-01a)

SearXNG is the self-hosted DISCOVERY engine for the research runtime (guide/11).
It is version-pinned, isolated on the private compose networks, and queried only
by the adapter (`packages/adapters/src/milpbooklm_adapters/searxng/`), which
implements the application `WebSearchPort`. Results are untrusted: discovered
URLs may only be acted on through the hardened fetch service and normal
ingestion controls — never trusted or imported directly.

## Pinning

`infra/podman/versions.lock` pins the exact image:

```
SEARXNG_VERSION=2026.9.20-2e624bed4
SEARXNG_IMAGE=docker.io/searxng/searxng:2026.9.20-2e624bed4@sha256:76f9ec5b38…
```

`compose.yaml` references the digest form directly. The adapter's default cache
config revision (`SearxngSearchService.config_revision` =
`searxng:2026.9.20-2e624bed4`, constant `SEARXNG_VERSION` in
`searxng/service.py`) must be bumped TOGETHER with `versions.lock` so cached
search answers are invalidated by deployment/config changes.

## settings.yml — two verified facts encoded here

1. **JSON output is NOT a SearXNG default** (docs.searxng.org search API): the
   search API's `format=json` works only when `json` is listed in
   `search.formats`. This file enables `formats: [html, json]` explicitly. A
   misconfigured instance answers JSON queries with a `403` HTML page — the
   adapter surfaces that as a typed `http_status` refusal, and a `200` with a
   non-JSON content type as `unexpected_content_type`.
2. **The built-in bot limiter depends on Valkey** (docs.searxng.org limiter):
   `server.limiter: false` per decision D7 / guide/04 — SearXNG is
   internal-only and application quotas apply before it, so the minimal profile
   runs without the limiter and therefore without any Valkey service. Enabling
   the limiter later adds Valkey as an optional deployment component.

## Network isolation

The compose service attaches to `backend` (`internal: true` — no egress, no
ingress except from application services) plus the unpublished `research-egress`
network for upstream engine traffic. Only Caddy publishes host ports. The
application reaches SearXNG at `http://searxng:8080` (compose sets
`MILPBOOKLM_SEARXNG_URL` for research services); nothing outside the project
network can reach it.

## Deployment status and deferred real-instance smoke

This host currently has no container runtime for the pinned image (no podman;
the snap docker CLI exists but its daemon is unavailable), and a user-space
`searx` checkout would drag a dependency tree outside the REFERENCE-DEPENDENCIES
matrix. The real-instance smoke is therefore **deployment-deferred with the T8
wave-2 rootless-podman stack** — same deferral class as the rest of the compose
project. The adapter itself is fully verified against the in-process fake
(`tests/unit/test_searxng_search.py`).

When the stack lands, record the smoke (non-CI, recording mode):

1. `GET /healthz` → 200.
2. `GET 'http://searxng:8080/search?q=test&format=json'` → HTTP 200 with
   `Content-Type: application/json` and a `results` array (proves the settings
   gate above).
3. One adapter call (budget defaults) → `outcome=complete` with hits; one with
   `engines=(<a throttled engine>,)` → verify `unresponsive_hosts` mapping into
   the explicit partial semantics.
