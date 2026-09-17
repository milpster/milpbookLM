# 13 — Studio Artifact Framework

## Common lifecycle

All artifact types implement `ArtifactRecipe`: validate request, freeze inputs, plan, generate structured content, validate, render optional renditions, publish an immutable version. Status transitions are `draft -> generating -> validating -> ready|failed|cancelled`; prior ready versions remain available.

## Storage

Store canonical structured payload as versioned JSON plus separately referenced renditions. Each artifact version records recipe/version, manifest, provider calls, provenance edges, safety status and effective restrictions. User study state is separate so collaboration does not overwrite another user's progress.

## Initial recipes

Implement reports, data tables, mind maps, flashcards, quizzes, slide decks, infographics, Audio Overviews and Video Overviews through typed schemas. Report recipes include FAQ, briefing, study guide and custom/suggested formats plus the generic composite substrate. Preserve the architecture's required controls: per-user flashcard/quiz progress; mind-map navigation and node-to-chat; slide modes/length/reorder/delete/restore/per-slide revision and PDF/PPTX export; infographic language/detail/orientation/style/PNG/share; audio Deep Dive/Brief/Critique/Debate; and video Explainer/Short/Cinematic where capability permits. Validate quiz answers/distractors, flashcard fronts/backs, slide hierarchy and all evidence references before publication.

Interactive Learning Overview is a required Phase 4 recipe over the composite-report substrate. Newly announced editable study-aid variants remain provisional; their reusable schemas may exist behind disabled feature flags, but the UI and conformance profile cannot advertise those variants as stable parity until the architecture's promotion criteria are met.

## Editing

Edits create a new artifact version using optimistic concurrency. Regeneration pins the selected base version and inputs. Export is a renderer concern and must revalidate authorization/restrictions at request and final download.

## Extension

Recipes register internally at startup through a typed registry; no third-party plugin marketplace or runtime code loading is implemented. Schema evolution requires migration/upcaster and golden compatibility tests.
