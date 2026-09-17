# 02 — Feature-Parity Target

## 1. Reference product

The external behavioral reference is the current **Gemini Notebook** product (formerly NotebookLM), based on publicly documented behavior as of September 2026. The goal is functional parity where useful, not visual pixel parity and not ecosystem/account compatibility. The project is independent and has no Google-account or Google-service dependency.

## 2. User-facing parity matrix

| Area | Target capability | Baseline priority |
|---|---|---|
| Notebook management | Create, rename, delete, duplicate/copy and share notebooks; basic metadata including a user-changeable icon/emoji | Core |
| Notebook instructions | Notebook-wide custom instructions affecting grounded chat and generation behavior | Core/Early |
| Notebook overview | Generated notebook/source summary and suggested starting questions/actions | Core/Early |
| Sources | Upload/import heterogeneous source types; inspect, select/deselect, remove and edit local display title/metadata without mutating retained source bytes | Core |
| Source Guide | Per-source automatic summary/guide plus focused source summarization | Core/Early |
| Source organization | Automatic/manual labels/categories and source selection | Core |
| Grounded chat | Ask questions against selected notebook sources; ordinary Notebook chat stays grounded in selected notebook material and does not silently use the open web/tools. Notes may be included only when explicitly selected, and the exact note revision is pinned for the request. | Core |
| Chat configuration | Standard/learning/custom conversation styles, custom instructions and shorter/default/longer response-length preference | Core/Early |
| Agentic chat | Explicit tool-capable chat mode backed by the agent runtime: web research, code/data analysis, generated files/charts/images and iterative artifact/file revision | Parity |
| Chat lifecycle | Per-user private conversation history in shared notebooks; start/reset/delete history; cancel/continue in-flight generation; preserve source/model/tool metadata | Core/Early |
| Citations | Inline citations linked to exact text/image/source locations with hover/jump context | Core |
| Notes | Editable user notes; save-chat-response-to-note (reference behavior keeps saved-response notes non-editable); rich structure/citations; combine, critique, summarize, outline, study-guide and related-idea transformations; single/all-note→source conversion; export; and collaborative live updates | Core/Early |
| Evolving note integration | Announcement says editable notes will live alongside sources and can be chatted with, cited and built from; stable FAQ still says notes enter prompts only when specifically selected, so automatic inclusion/indexing is not assumed | Provisional / announced |
| Reports | Document reports (FAQ, study guide, briefing, custom/suggested formats) plus a generic interactive/composite-report substrate capable of embedding Studio learning artifacts | Parity |
| Interactive Learning Overview | Interactive report combining a textual learning overview with suggested or embedded Studio learning artifacts such as infographics, quizzes and flashcards | Parity |
| Data tables | Language/custom row-column instructions, structured extraction/analysis with provenance, and spreadsheet export with citations | Parity |
| Mind maps | Navigable concept/relationship view with zoom, expand/collapse, node→chat questioning, download and feedback | Parity |
| Flashcards | Difficulty/count controls, explanations, previous/next/full-screen navigation, persisted study progress, shuffle/restart/delete/retry controls and CSV-style export | Parity |
| Quizzes | Difficulty/count controls, previous/next/full-screen navigation, hints, answers/explanations, progress/results and retry/review flows | Parity |
| Editable study aids and performance follow-up | Announced add/edit-question flows, short-answer/multiple-select/fill-in-the-blank quiz formats, and explicitly asking chat about the current user's completed quiz/flashcard performance | Provisional / announced |
| Audio Overview | Deep Dive, Brief, Critique and Debate-style generated audio | Parity |
| Interactive Audio Overview | Join/interruption/questions with Audio Overview hosts, grounded in notebook sources | Advanced parity |
| Realtime notebook voice chat | Announced general source-grounded voice conversation with interruption and step-by-step follow-up, distinct from joining a generated Audio Overview | Provisional / announced |
| Recorded-audio capture | Announced mobile recorder for lectures/thoughts maps to an optional browser recording/import UX over the existing audio-source ingestion path; native share-sheet/offline-app behavior is not required | Provisional / announced |
| Video Overview | Explainer and ~60-second Short narrated/animated visual overviews, with multilingual output where the selected media pipeline supports it | Parity |
| Cinematic video | Higher-production Cinematic overview | Advanced parity |
| Slide decks | Detailed/presenter formats, short/default/long length, structured deck generation, per-slide revision/delete/restore/reorder, slideshow viewing, feedback and PDF/PPTX export | Parity |
| Infographics | Language/detail/orientation/style controls, custom prompt, zoom/view, PNG-style download and sharing | Parity |
| Artifact lifecycle | Background generation, generate-now/deferred-generate-later scheduling, completion/unread notifications, visible custom prompt/instructions, revision, feedback, share links and downloads/exports. Exported/downloaded files are detached snapshots: later notebook edits do not synchronize into them and application ACLs cannot revoke an independent external copy. | Parity |
| Starter artifacts | Optionally auto-generate selected starter artifacts when sources are first added | Late/optional parity |
| Source discovery | Fast web/connector research for candidate sources | Parity |
| Deep Research | Agentic iterative research, report creation and source import | Parity |
| Code/data analysis | Source-grounded computation | Parity |
| Private sharing | Viewer/editor roles and focused chat-view links | Parity |
| Public notebooks | Public/link sharing, focused chat-view links and artifact-specific share links. Current official documentation says public-notebook viewers use a Google account; our independent deployment MAY optionally allow anonymous share tokens through its own policy, disabled by default, but does not claim that as reference-product parity. | Late/optional parity |
| Notebook copying | Owner-controlled private copies; parity default copies sources/Studio artifacts but not chat history or notes, with source access/restrictions re-evaluated | Parity |
| Featured/published notebooks | Curated/discoverable published notebooks if public sharing is enabled | Late/optional parity |
| Usage analytics | Lightweight notebook usage/query analytics; system health/performance belongs to administrator observability rather than this product feature | Late/optional parity |
| Restricted connector sources | Keep a generic access/restriction hook so an optional connector can enforce upstream access or export rules when needed; no rights-management platform is required | Deferred connector hook |
| Output language | User-level default output language with per-artifact overrides where supported | Core/Early |
| Appearance | Light/dark/system UI preference | Low-cost UI parity |
| Responsive web access | One responsive asynchronous web application across desktop/tablet/phone browsers. No native mobile client or PWA capability is required. | Core client architecture |
| Custom providers | User/admin configured local or remote models through provider-neutral adapters | Core project requirement |

## 3. Supported source families

The architecture MUST be capable of supporting at least the source families documented by Gemini Notebook today:

- PDF;
- plain text and pasted text;
- Markdown;
- DOCX;
- PPTX;
- CSV;
- spreadsheet files/formats;
- images;
- audio;
- EPUB files;
- optional authenticated/restricted repositories through generic connectors;
- web URLs;
- public YouTube URLs/transcript-backed video sources;
- optional cloud document/storage connectors implemented through generic adapters;

The reference product currently treats imported web URLs primarily as webpage text and public-video URL sources as transcript-backed sources, while some remote-document connectors can represent refreshable content. Our implementation MAY preserve richer content, but it MUST retain source type/version semantics explicitly rather than collapsing inputs into anonymous text.

Exact source limits are installation policy, not compatibility requirements.

### 3.1 Parity behaviors that are product-specific rather than architectural constraints

The reference documentation describes source auto-labeling, Source Guide/source summaries, source-grounded ordinary chat, document and interactive reports, artifact sharing/exports, notebook copies, lightweight shared-notebook analytics, realtime collaborative note edits, output-language preferences, restricted connector sources and deferred “Generate later” Studio jobs. We deliberately exclude vendor account coupling, plan tiers, quotas, proprietary cross-product integrations, vendor-only source types and identical UI mechanics. Features seen only in announcements, experiments or staged rollouts are informational references, not normative parity requirements until they are documented as stable product behavior. Interactive Learning Overview now has stable Reports help documentation and is normative Phase 4 parity. General realtime notebook voice chat, mobile audio recorder, notes-alongside-sources presentation, editable/additional quiz formats and study-performance chat follow-up remain provisional. Stable FAQ behavior—notes enter prompts only when specifically selected—remains authoritative until updated documentation defines whether the new presentation changes context semantics. The architecture already supplies reusable primitives without treating the remaining rollout-specific UI as stable.

The native mobile app, operating-system share-sheet integration and offline app downloads are deliberate non-targets. Equivalent core tasks remain reachable through the responsive web application: upload or record supported content, chat against sources, and download generated files where the browser permits it.

Reference-product export destinations such as Google Docs/Sheets are mapped to portable provider-neutral files. The useful parity contract is snapshot export with appropriate content/citations, not Google account coupling or bidirectional synchronization. Export/download authorization and dependency restrictions are checked before release of the file; after a user independently copies or distributes a downloaded file, the application cannot propagate later ACL changes into that external copy and must not claim otherwise.

### 3.2 Ordinary chat versus agentic chat

Current reference-product chat help describes ordinary notebook chat as source-grounded, while its FAQ clarifies that notes participate only when specifically selected. Separate agentic chat capabilities can search the web, execute code, create downloadable files/visualizations/images and conduct research with or without sources. Our architecture MUST preserve this distinction: ordinary chat is grounded in selected sources plus any explicitly selected notes and remains tool-free; **Agentic Chat** delegates tool calls to the inspectable Agent Runtime and `ExecutionProvider`. Explicit note context pins an immutable `NoteRevision`; note→source conversion remains available when a note should become part of the normal indexed corpus.

Agentic outputs should support common portable file classes (for example PDF/DOCX/Markdown/text, CSV/JSON/XLSX, PNG/SVG/JPG/GIF and PPTX) when the installed renderers/providers support them.

## 4. Feature equivalence versus implementation equivalence

Parity means a user can accomplish the same class of task. It does not require the same proprietary model or backend technique. Examples:

- The reference product's secure cloud computer maps to our local isolated `ExecutionProvider`.
- Vendor-native cloud document synchronization maps to a generic connector adapter rather than core database code.
- Audio/Video Overview may use local or third-party STT/TTS/image/video providers.
- Source categorization may use local embeddings/classifiers or an LLM.

## 5. Explicitly superior target behaviors

The system SHOULD exceed the reference product in:

- provider selection transparency;
- local-model support;
- per-role model configuration;
- reproducible artifact metadata;
- full retrieval/evaluation telemetry;
- explicit source snapshot/version management;
- configurable model trust/privacy policies;
- replaceable search/indexing components;
- self-hosted data ownership.

Beyond-parity features such as a public plugin SDK or portable whole-notebook interchange format are intentionally deferred until there is a concrete need; backup/restore and internal adapter boundaries are sufficient for the baseline.

## 6. Reference-documentation caveat

The reference product's current help corpus is not perfectly internally consistent. As of this specification snapshot, its general FAQ still says notebook duplication is unsupported, while the more specific current notebook-management page explicitly documents notebook copying and states that sources/Studio content copy while chat history and notes do not. This specification follows the more specific current feature page for notebook-copy parity and records the discrepancy so it is not mistaken for an unnoticed contradiction.

## 7. Upstream references

- Product rename and secure code-backed analysis: https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/
- Agentic research updates: https://blog.google/innovation-and-ai/products/notebooklm/better-research-notebooklm/
- Interactive and document reports: https://support.google.com/gemininotebook/answer/18323649
- September 2026 study/voice announcement (Interactive Learning Overviews, realtime notebook voice, mobile audio recording, new quiz formats and study-performance follow-up): https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/
- Usage limits / deferred Generate later: https://support.google.com/gemininotebook/answer/17670842
- Public/featured notebooks: https://support.google.com/gemininotebook/answer/16322204
- Current source types: https://support.google.com/gemininotebook/answer/16215270
- Chat grounding/configuration and agentic chat capabilities: https://support.google.com/gemininotebook/answer/16179559
- Mind Maps: https://support.google.com/gemininotebook/answer/16212283
- Notes: https://support.google.com/gemininotebook/answer/16262519
- Infographics: https://support.google.com/gemininotebook/answer/16758265
- Audio Overviews / interactive audio: https://support.google.com/gemininotebook/answer/16212820
- Video Overviews: https://support.google.com/gemininotebook/answer/16454555
- Slide Decks: https://support.google.com/gemininotebook/answer/16757456
- Flashcards/Quizzes: https://support.google.com/gemininotebook/answer/16958963
- Source discovery / Deep Research: https://support.google.com/gemininotebook/answer/16215270
- FAQ (prompt context and known copy-documentation discrepancy): https://support.google.com/gemininotebook/answer/16269187
- Output language: https://support.google.com/gemininotebook/answer/16261963
- Appearance mode: https://support.google.com/gemininotebook/answer/16225229
