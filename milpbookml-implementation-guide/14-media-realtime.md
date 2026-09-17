# 14 — Audio, Video and Realtime Implementation

## Audio Overview

Generate an evidence-backed script with speaker turns, validate citations/language/safety, synthesize segments, normalize/concatenate, validate duration/container and publish canonical audio plus transcript/timeline. Segment-level provenance links transcript spans to evidence and final media time ranges.

## Realtime audio

Use a capability-gated WebSocket session with ephemeral provider credentials where supported. Persist consent/disclosure and content-free connection/audit metadata before connection. Microphone audio, transcripts and realtime turn content are ephemeral by default and are not appended to conversation history; sequence state needed for interruption/reconnect expires with the session. A future explicit save action creates an ordinary authorized, versioned note/conversation artifact. Absence of realtime infrastructure disables only interactive audio.

## Recorded capture

Browser recording is provisional. If enabled, show recording state and consent, stream only to bounded temporary storage, then ingest the finalized recording through the normal audio-source pipeline. No native/offline recorder is implied.

## Video Overview

Plan a structured storyboard containing scenes, narration, evidence, on-screen text and asset rights metadata. Generate or render assets asynchronously, synthesize narration, compose with FFmpeg in the isolated media worker, validate A/V duration/codecs/captions and publish renditions only after safety and provenance checks. Provider-generated video remains a replaceable scene/render capability, not the product data model.

## Rights and safety

Record origin, license/usage assertion, provider safety outcome and user-supplied status per asset. Refusal is a terminal explainable artifact state. Never silently substitute disallowed content.

## Manual tests

Human runbooks assess intelligibility, pacing, slide/video legibility, synchronization, caption accuracy, responsive playback and realtime interruption on declared hardware/browser profiles.
