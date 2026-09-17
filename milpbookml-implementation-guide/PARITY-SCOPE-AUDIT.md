# Gemini Notebook Parity and Scope Audit

Reference date: 16 September 2026. “Gemini Notebook” is the current product name; “NotebookLM” is the former name and remains a useful search/reference term. This project is independent and uses Google documentation only to define observable task classes.

## Current parity disposition

| Reference behavior | Local disposition | Scope judgment |
| --- | --- | --- |
| heterogeneous sources, source selection, Source Guide and labels | required through provider-neutral files/snapshots | direct parity |
| source-grounded ordinary chat with exact text/image citations | required; ordinary mode has no silent web/tools | direct parity and safety clarification |
| configurable chat style/length and private history | required | direct parity |
| experimental agentic chat with web, code and generated files | required Phase 3 capability, explicitly separated and supervised | documented parity; reference maturity remains experimental |
| Fast/Deep Research and candidate-source import | required Phase 3 | direct task equivalence; SearXNG/Playwright are local implementation choices |
| notes, saved-response immutability, transformations, collaborative edits and note-to-source | required Phase 4 | direct parity |
| document reports and Interactive Learning Overview with embedded/suggested Studio artifacts | required Phase 4 | direct parity; Learning Overview was promoted after stable help documentation appeared |
| data tables, mind maps, flashcards and quizzes with study progress | required Phase 4 | direct parity |
| slide generation/revision/delete/restore/reorder and PDF/PPTX export | required Phase 5 | direct parity; source-aware revision is an intentional quality improvement |
| infographic controls, zoom/share and PNG download | required Phase 5 | direct parity |
| Audio Overview formats and background generation | required Phase 6 | direct parity |
| interactive Audio Overview | provider-dependent Phase 6 | documented advanced parity; English-only reference limitation need not constrain a capable local provider |
| Video Explainer and Short | required Phase 6 when the media profile is enabled | direct parity |
| Cinematic Video | advanced/provider-dependent Phase 6 | documented parity without pretending every provider can supply it |
| private sharing, chat-view links and notebook copying | required Phase 7 | direct parity with stricter live authorization checks |
| public/featured notebooks and analytics | late optional | documented reference behavior, intentionally excluded from the baseline critical path |
| general realtime notebook voice, browser recording, evolving note-context semantics and new editable quiz/performance features | provisional | announcement-level or incompletely documented behavior; no stable-parity claim |

## Vendor-specific mappings

| Google-specific behavior | Provider-neutral equivalent | Result |
| --- | --- | --- |
| Google Docs/Slides/Sheets imports | DOCX/PPTX/XLSX plus optional generic connector snapshots | no Google dependency |
| Drive auto-sync and access revocation | connector revision polling, immutable snapshot activation and access-revoked state | optional connector behavior |
| Play Books sources/restrictions | EPUB/connector source plus derived-export restriction hook | no Play Books integration or license emulation |
| Gemini Chats as sources; Notebooks in Gemini/Search | portable text/document import or future generic connector | deliberate ecosystem non-target |
| Google Docs/Sheets export | DOCX/XLSX/CSV/PDF/PPTX and other portable snapshots | equivalent user outcome, no bidirectional sync claim |
| Google-account public sharing | local share-link policy | optional; no Google identity; anonymous tokens are an intentional local policy choice, not a claimed reference behavior |
| native mobile recorder/share sheet/offline app | responsive browser capture/upload where enabled | native packaging remains a non-target |
| plan tiers, quotas and consumer/Workspace distinctions | administrator capability/resource policy | vendor commercial policy excluded |

## Intentional improvements, not accidental scope creep

The following exist because self-hosting, security or reproducibility requires them: provider transparency and local defaults; immutable source/artifact versions; full provenance and manifests; stronger export/share restriction propagation; purge closure; deterministic evaluation; observable durable jobs; backup/restore; isolated parsing/browser/code execution; and source-aware artifact revision. They improve the implementation without creating unrelated product families.

## Scope-creep exclusions

The baseline does not include Kubernetes, Kafka, Redis, Elasticsearch/OpenSearch, a standalone vector database, MinIO, a knowledge graph, a public plugin marketplace/SDK, arbitrary runtime extension loading, enterprise connector catalog, SaaS billing/organization tenancy, native mobile applications, PWA/offline synchronization, proprietary Google integration or pixel-perfect UI cloning.

Internal ports, S3-compatible storage support and scale-out substitutions are boundaries, not backlog commitments. A planning task for any excluded item requires measured need plus a new ADR and cannot be smuggled in as “future-proofing.”

## Factual caveats the plan must preserve

- Web URL imports in the reference primarily use page text; public-video URL imports are transcript-backed. Richer local capture is allowed but may not be described as required reference behavior.
- Agentic chat is officially documented as experimental and requiring supervision even though it is a parity target.
- Interactive Audio is distinct from the separately announced general realtime notebook voice experience.
- Interactive Audio microphone audio and transcribed exchanges are ephemeral by default, matching the documented reference privacy behavior; only content-free consent/audit/session metadata is retained unless the user explicitly saves an ordinary artifact.
- Cinematic video has narrower reference availability than Explainer/Short; local availability is capability-driven.
- Public notebook/chat view is presentation scoping, not proof that hidden sources are authorization-revoked. The local system enforces actual policy rather than copying that ambiguity.
- Current official public-notebook documentation requires viewers to have a Google account. It does not establish signed-out artifact viewing; the specification makes no such parity claim.
- Exported files are detached snapshots. Once independently distributed, later local ACL changes cannot revoke them.
- Reference limits, language lists, age gates and plan quotas are not universal architectural limits. A local release advertises only what its selected providers and policy profile actually support.

## Official sources checked

- [Sources, Source Guide, source discovery and Deep Research](https://support.google.com/gemininotebook/answer/16215270)
- [Grounded and agentic chat](https://support.google.com/gemininotebook/answer/16179559)
- [Notes](https://support.google.com/gemininotebook/answer/16262519)
- [Document and interactive reports](https://support.google.com/gemininotebook/answer/18323649)
- [Audio Overviews and interactive mode](https://support.google.com/gemininotebook/answer/16212820)
- [Video Overviews](https://support.google.com/gemininotebook/answer/16454555)
- [Flashcards and quizzes](https://support.google.com/gemininotebook/answer/16958963)
- [Infographics](https://support.google.com/gemininotebook/answer/16758265)
- [Slide decks](https://support.google.com/gemininotebook/answer/16757456)
- [Public and featured notebooks](https://support.google.com/gemininotebook/answer/16322204)
- [September 2026 study-tools announcement](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)
