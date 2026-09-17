# Reference Dependency and Adapter Selections

This file makes the first implementation buildable without turning replaceable libraries into domain dependencies. Commit exact patch versions and hashes in `uv.lock`, `pnpm-lock.yaml`, container digests and the SBOM; prose fixes supported major lines and roles only.

## Application toolchain

| Area | Reference selection | Binding rule |
| --- | --- | --- |
| Python | CPython 3.13, managed by `uv` | `requires-python` is `>=3.13,<3.14` for v1; `uv.lock` is committed and CI uses `uv sync --frozen` |
| API | FastAPI, Pydantic v2, Uvicorn | Framework types stop at route/composition boundaries |
| Persistence | SQLAlchemy 2, Alembic, psycopg 3 | Async application access; migrations use a separate privileged DB role |
| Frontend | Node.js 24 LTS, pnpm, React 19, TypeScript, Vite | Exact Node image digest and `pnpm-lock.yaml`; strict TypeScript |
| Client data/router | TanStack Query and TanStack Router | Server resources remain authoritative; no domain logic in cache hooks |
| API typing | OpenAPI 3.1 plus generated TypeScript client/types | Generation runs in CI; handwritten divergence fails the contract check |
| Database | PostgreSQL 18 plus pgvector | Required extensions and versions checked by readiness/migrations |
| Packaging | Rootless Podman and pinned `podman-compose` provider | Compose-provider path/version is verified before deploy |

## Security and platform libraries

| Concern | Reference selection/approach |
| --- | --- |
| Passwords | `argon2-cffi`; parameters calibrated at install/upgrade and stored with each hash |
| Session tokens | 256-bit CSPRNG opaque tokens; only a keyed hash is stored server-side |
| Credential encryption | libsodium XChaCha20-Poly1305 through a maintained binding; per-record nonce, associated owner/scope/provider data, versioned key ID |
| Structured logs/traces | standard logging plus OpenTelemetry-compatible adapters; content redaction before export |
| HTTP | `httpx`/`httpcore` only behind the dedicated fetch/provider transports; ordinary URL fetching may not use an unmodified convenience client because DNS rebinding protection requires validated-address connection control |
| HTML | structured extraction plus an allowlist sanitizer; raw source pages render only on a separate opaque/sandboxed origin with scripts disabled and strict CSP |

## Parser and renderer reference matrix

| Family | Acquisition/parser reference | Important behavior |
| --- | --- | --- |
| Plain text/Markdown/CSV | Python streaming decoders and CSV parser | BOM/encoding detection is bounded; never execute embedded markup |
| PDF | `pypdf` plus `pdfplumber`/`pdfminer.six`; optional `qpdf` repair in isolation | Preserve page and bounding-box locators; OCR only when needed; encrypted files fail explicitly |
| DOCX | `python-docx` plus isolated LibreOffice/PDF rendition where layout evidence is needed | Disable external-reference retrieval and macros |
| PPTX | `python-pptx` plus isolated LibreOffice/PDF rendition | Preserve slide/shape locators and speaker notes separately |
| XLSX | `openpyxl` read-only/data-only plus isolated LibreOffice only for explicit recalculation/render | Preserve formulas and cached values distinctly; never execute macros |
| EPUB | EbookLib plus hardened XML/HTML extraction | Reject unsafe archive expansion and external fetches |
| HTML/web | selectolax/lxml-compatible parser plus readability extraction | Preserve captured DOM/heading locator and canonical/final URL |
| Images/OCR | Pillow for bounded metadata/normalization; Tesseract as isolated CLI | Enforce pixel/dimension/decompression limits before decode/OCR |
| Audio/video | `ffprobe`/FFmpeg as isolated CLI; STT provider port | Enforce duration/track/container limits; retain millisecond locators |
| Office/PDF exports | Pandoc/LibreOffice and a selected PDF renderer in isolated renderer workers | Rendered files are validated and provenance-linked before publication |
| Media composition | FFmpeg in the media worker | No shell interpolation; explicit argv and codec/container allowlists |

Every native tool is version-pinned in its container/runtime image, included in the SBOM and tested against hostile fixtures. Licensing is reviewed before redistribution; a library whose license conflicts with the intended distribution is replaced behind the same port rather than silently accepted.

## Model selections

The guide deliberately does not freeze one embedding, reranker, chat, OCR, TTS, STT, image or video model because available hardware, licensing and language requirements vary. Phase acceptance nevertheless requires a recorded reference selection, capability descriptor, deterministic fake, quality benchmark, privacy classification and fallback behavior. A missing selection blocks that capability's phase gate, not the platform skeleton.

## Primary references checked

These links are factual anchors, not permission to float versions. Lockfiles, image digests and the SBOM remain the build authority.

- [Python 3.13 `uuid` module](https://docs.python.org/3.13/library/uuid.html): the standard library documents UUID versions 1, 3, 4 and 5; application-generated v7 therefore requires an explicitly selected dependency or a later Python line.
- [PostgreSQL 18 UUID functions](https://www.postgresql.org/docs/18/functions-uuid.html): PostgreSQL 18 supplies `uuidv4()` and time-ordered `uuidv7()`.
- [Node.js release schedule](https://nodejs.org/en/about/previous-releases): Node 24 is the v1 LTS line selected by this guide.
- [`uv` project structure and lockfile](https://docs.astral.sh/uv/concepts/projects/layout/): `uv.lock` is the committed cross-platform resolution used by frozen CI installs.
- [`podman compose` manual](https://docs.podman.io/en/latest/markdown/podman-compose.1.html): the command delegates to an external Compose provider, so the provider and version are pinned explicitly.
- [Playwright browser management](https://playwright.dev/docs/browsers): browser binaries are installed and versioned with the Playwright release; CI names Chromium/Firefox projects rather than claiming arbitrary branded-browser coverage.
- [SearXNG search API](https://docs.searxng.org/dev/search_api.html) and [limiter](https://docs.searxng.org/admin/searx.limiter.html): JSON must be enabled, and the built-in limiter depends on Valkey.
- [pgvector reference implementation](https://github.com/pgvector/pgvector): PostgreSQL vector search and HNSW support remain behind the indexing port and are measured with filtered-recall fixtures.
