# 24 — Glossary

**Artifact** — A generated, versioned notebook output such as a report, quiz, deck, audio overview or video.

**Artifact recipe** — Versioned generation/orchestration definition for an artifact type.

**Agentic Chat** — Explicit chat mode allowed to invoke research, web, execution and other registered tools under agent/runtime policy; distinct from ordinary notebook-grounded chat.

**GenerationInputManifest** — Immutable record of the exact source/canonical representations, selected note revisions, artifact/run-evidence dependencies, conversational message context where applicable, resolved instructions, retrieval/index/prompt/recipe versions and other material inputs pinned for one model-generation step. Static operations usually have one; agentic runs may have an initial snapshot plus multiple child generation manifests as new immutable tool evidence is acquired.

**NoteRevision** — Immutable revision of a mutable/collaborative note, pinned whenever an explicitly selected note context uses or cites that note so the operation remains reproducible.

**Realtime/duplex capability** — Low-latency streaming speech input/output and barge-in capability used by interactive Audio Overview or future realtime features; it is an infrastructure capability, not a separate baseline product surface.

**Capability/conformance profile** — Machine-readable declaration of which product capabilities a phase/build implements and enables, their status/dependencies and therefore which automated/manual requirements are applicable; defined by AD-026.

**Remote provider operation** — Durable identity/state for an asynchronous external generation submitted to a media/model provider and reconciled by polling and/or authenticated callbacks.

**Media rendition** — Validated derivative of an original generated/imported media asset, such as a browser-compatible transcode, thumbnail, poster frame, waveform or caption track, with explicit parent/tool/version provenance.

**Canonical document** — Immutable provider/parser-neutral structured representation of an immutable source version. Re-canonicalization that changes node/locator identity creates a new representation rather than rewriting one referenced by historical outputs.

**Canonical node** — A structural unit in a canonical document such as a paragraph, page, table, slide or transcript segment.

**Capability descriptor** — Metadata describing what a model/provider can accept and produce and under what operational/privacy constraints.

**Chunk** — A derived retrieval unit created from canonical source nodes. Not a durable citation identity.

**Citation** — User-visible pointer from an answer/artifact claim to evidence resolved through an immutable provenance target such as a canonical `SourceVersion` location, selected `NoteRevision`, or retained `RunEvidenceSnapshot`.

**Connector** — Integration that imports or synchronizes content from an external service/repository.

**Evidence** — An authorized, immutable source/note/artifact/run-snapshot-backed span, node or structured element used to support a generated claim or artifact element.

**ExecutionProvider** — Interface for running model-generated computation. Initial implementation uses Bubblewrap.

**Grounding** — Constraining/connecting generated output to the explicitly selected notebook evidence set and preserving traceability to its immutable inputs.

**Model role** — Logical task assignment such as chat, embedding, reranking, TTS or image generation.

**Notebook** — Primary project/research container containing sources, conversations, notes, artifacts and research runs.

**Provider** — Configured model/media service endpoint, local or remote.

**Provenance** — Trace from derived/generated content back to the precise immutable input location/revision that supports it (for example `SourceVersion` + canonical location, `NoteRevision`, `RunEvidenceSnapshot` or an embedded `ArtifactVersion`).

**ResearchRun** — User-owned inspectable stateful agentic research workflow with an immutable initial input snapshot and append-only tool/evidence history.

**RunEvidenceSnapshot** — Immutable run-scoped capture of external/tool evidence that is not yet a notebook source; private to the initiating run/user unless explicitly retained as a citation dependency of shared output or promoted to a source.

**StudySessionSnapshot** — Immutable, user-private capture of the minimum quiz/flashcard progress and results explicitly selected for one chat/generation request, tied to the exact shared `ArtifactVersion`. It prevents changing mutable study state from altering an in-flight answer and is never notebook-wide source content.

**Source** — Logical imported information source.

**SourceVersion** — Immutable snapshot/revision of a source used for reproducibility.

**Studio** — Artifact-generation subsystem and user-facing surface.
