# 16 — FastAPI and React Interface

## REST contract

Expose `/api/v1` resources for session, capabilities, notebooks, memberships, sources/versions, conversations/messages, notes/revisions, artifacts/versions, research runs, jobs, shares and admin diagnostics. Generate OpenAPI 3.1 in CI and fail on unreviewed breaking changes.

The minimum route families are:

| Route family | Required semantics |
| --- | --- |
| `/session`, `/auth/*` | login/logout/current actor, CSRF bootstrap, local recovery/bootstrap boundaries |
| `/capabilities` | actor/notebook-effective state plus disabled/degraded reason |
| `/notebooks`, `/{id}/members` | CRUD, ETag, custody-safe ownership/membership commands |
| `/sources`, `/{id}/versions` | streaming import, status, refresh, select/remove, metadata-only rename, purge preview/confirm |
| `/conversations`, `/messages` | private history, new/reset/delete, ordinary generation/cancel and final citations |
| `/notes`, `/{id}/revisions` | immutable revisions, transforms, promotion to source and editability rules |
| `/artifacts`, `/{id}/versions` | generate/revise/status/view/export/share and per-user study state |
| `/research-runs` | explicit mode, budget/tools, pause/resume/cancel, evidence and source promotion |
| `/jobs`, `/events` | status/cancel and authorized SSE resume |
| `/shares` | scoped creation/resolution/revocation with live restriction checks |
| `/admin/*` | users/providers/policy/diagnostics/custody metadata without implicit notebook-content access |

OpenAPI security declarations do not replace enforcement. Every route declares action/resource policy, idempotency and ETag behavior, stable problem codes, audit category and content classification in route metadata; a meta-test rejects omissions.

Mutations use JSON, CSRF protection, `Idempotency-Key` for retryable commands and `If-Match` for mutable resources. Errors use RFC 9457 problem details with stable machine codes and correlation ID. Uploads stream via multipart with server-side limits.

## Streaming

Use SSE for job and generation presentation. Tokens are best-effort; authoritative state is obtained from REST after reconnect. The final persisted response includes citations and manifest before the terminal event.

## Frontend

Use strict TypeScript generated API types, TanStack Query cache keyed by resource/version, route-level code splitting and an explicit job store. Optimistic UI is limited to reversible metadata changes and rolls back on ETag conflict.

Cache keys include actor plus notebook/resource/version and are cleared on logout, role change and share-context change. Private conversation/research responses never enter a notebook-shared cache key. Service workers/offline caching are not enabled in the baseline.

## Source viewer

Resolve citations through a server-authorized locator endpoint. Render untrusted source HTML in a sandboxed iframe or safe structured viewer with scripts disabled. PDF/media viewers seek to validated page/region/time locators.

## Responsiveness and accessibility

Implement keyboard-first notebook/source/chat/Studio flows, visible focus, semantic landmarks, live-region job updates, reduced motion and narrow-screen layouts. Chromium and Firefox on GNU/Linux are the support baseline.
