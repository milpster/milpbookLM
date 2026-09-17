# 11 — Research Runtime, SearXNG and Playwright

## Separation

Research runs are durable state machines distinct from ordinary chat. Each planning/model step records a child input manifest; tool outputs append immutable evidence records. Only curated results promoted through normal ingestion become notebook sources.

## Tool surface

Expose constrained tools: `web.search`, `web.fetch`, `browser.open`, `browser.observe`, `browser.interact`, `source.import`, and read-only notebook retrieval. Side effects require explicit capability and approval. Do not expose arbitrary Playwright or browser-evaluate APIs to models.

## SearXNG

Deployment settings explicitly enable SearXNG's JSON search format. The adapter calls that API with engine/category/language/time parameters, deadlines and per-run budgets and rejects unexpected content types. It records returned URL/title/snippet plus contributing engines and degraded/timeout errors. SearXNG has no independent index: coverage, ranking, syntax support and availability depend on responding upstream engines, which may throttle or challenge the shared server address. Therefore responses are explicitly partial when engines fail, engine health is observable, and the product never claims exhaustive or reproducible coverage. SearXNG is discovery only: results are untrusted and must pass fetch/import controls. Cache by normalized query plus SearXNG configuration revision for a short TTL.

## Fetching

Static fetching is preferred. Normalize URLs, resolve and validate all candidate addresses, then connect the dedicated transport to the chosen numeric address while preserving the already validated hostname for HTTP `Host` and TLS SNI/certificate verification; an unmodified convenience client that performs a second uncontrolled DNS lookup is insufficient. Repeat resolution/validation for every redirect, reject scheme/port/credential changes outside policy, cap bytes/time, identify content and extract in isolation. Record retrieval timestamp, redirect chain, final URL, relevant response headers and content hash. Proxy deployments apply the equivalent destination enforcement at the trusted egress proxy and prevent direct bypass.

## Playwright

Run Chromium in a dedicated rootless browser worker with disposable contexts, blocked private networks, download limits and no inherited user credentials. Use Firefox for product E2E tests, but Chromium is the normative research browser. Browser automation is invoked only when static fetch cannot render required public content or an explicit authorized workflow requires interaction.

## Testing

Use a local fake SearXNG plus self-hosted deterministic websites covering redirects, JS rendering, robots/policy outcomes, prompt injection, downloads, timeouts and blocked private addresses. CI never depends on the public web.
