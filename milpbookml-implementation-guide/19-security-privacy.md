# 19 — Security and Privacy Controls

## Data classification and dispatch

Classify public, notebook-private, restricted connector, secret and audit metadata. Every external dispatch passes policy, actor authorization, credential ownership and visible disclosure checks. Log metadata, not content.

## Prompt injection

Treat source/tool/web content as untrusted data, clearly delimit it, keep system/tool policy outside retrieved text and require structured tool selection. Tool authorization is server-side; model output cannot grant capability. Research results never become trusted instructions.

## SSRF and web safety

Allow only HTTP(S); canonicalize hosts; resolve DNS and reject loopback/private/link-local/multicast/metadata ranges before connection and after every redirect; pin the validated address for the connection; cap redirects, bytes and time; block embedded credentials and unsafe ports. Apply equivalent checks to provider endpoints/callbacks with explicit administrator exceptions.

## Upload/browser isolation

Quarantine uploads, inspect type/archive expansion and parse out of process. Disable document external references. Playwright runs non-root in a dedicated worker/network policy with a version-matched browser image; startup tests prove the Chromium sandbox/isolation posture rather than adding `--no-sandbox` silently. Downloads return through quarantine. Source HTML is never injected into the application origin: use a separate opaque/sandboxed origin or structured renderer, deny scripts/forms/top navigation, apply restrictive CSP, and mediate downloads/citation navigation through authorized API endpoints.

## Secrets and audit

Never place secrets in job payloads, logs or manifests; resolve secret references at dispatch. Audit login, membership/share, provider/credential, custody/break-glass, purge, export and consequential tool actions with append-only integrity controls and bounded retention.

The application origin sends a restrictive CSP (`default-src 'self'` with narrowly enumerated script/style/media/connect targets), frame-ancestors policy, MIME sniffing protection, referrer policy and permissions policy. CORS is off by default; enabling a separate origin requires an explicit allowlist and credentials-safe configuration. User/source Markdown, SVG and HTML pass type-specific sanitization and are never granted application-origin script capability.

## Purge

Build a traversal over provenance, manifests, indexes, caches, jobs, artifacts, traces and blob references. Mark primary rows/tombstones transactionally, block new access immediately, then asynchronously erase unreferenced controlled copies. Produce a purge report with unresolved external transmissions/manual-copy caveat. Backups expire under the documented finite retention schedule.

## Blob integrity

Write temporary, hash/size validate and fsync, atomically finalize, then commit the database reference. Reconciliation identifies orphan temporaries, unreferenced finals and missing referenced blobs; missing data is an integrity incident, never empty content.
