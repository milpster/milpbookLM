# 14 — Media, Audio, Video and Realtime Interaction

## 1. Media capability layer

Media generation should use provider-neutral capability interfaces for:

- speech-to-text;
- text-to-speech;
- speaker/voice selection;
- image generation/editing;
- video generation where available;
- audio/video composition and transcoding.

FFmpeg or equivalent backend tooling is an implementation detail of rendering, not an LLM tool requirement.

## 2. Audio Overview pipeline

```text
source/evidence selection
 -> discussion outline
 -> speaker-role planning
 -> grounded script/dialogue generation
 -> citation/evidence validation
 -> TTS per segment/speaker
 -> mastering/composition
 -> artifact version
```

The structured script SHOULD retain evidence references even when citations are not spoken aloud.

## 3. Audio modes

The current parity baseline includes **Deep Dive**, **Brief**, **Critique**, and **Debate** audio formats, configurable language/length/steering instructions, and interactive voice participation. The reference product currently documents narrower availability for some interactive Audio Overview capabilities (including language/plan constraints), but we do not need to preserve those restrictions; provider capability metadata determines what our installation can offer.

## 4. Realtime interactive audio

Interactive mode is a separate low-latency path:

```text
microphone -> streaming STT -> conversation state -> retrieval -> streaming LLM -> low-latency TTS -> audio
```

It requires interruption/barge-in handling, turn detection, latency budgets and persistent notebook grounding. For parity and privacy, microphone audio and the ephemeral voice/STT exchange SHOULD NOT be persisted by default. If the product later offers an explicit “save interaction” action, that action must create an ordinary versioned note/conversation artifact under normal retention/provenance rules rather than silently changing the realtime retention policy.

Two product experiences may reuse this transport but MUST remain distinct in state and UX:

- **Interactive Audio Overview** joins and temporarily interrupts an already generated overview, answers from notebook sources, then resumes that overview.
- **Realtime notebook voice chat** is the newly announced general source-grounded voice conversation with step-by-step follow-up and interruption; it has no prerequisite generated Audio Overview and remains provisional until stable reference documentation lands.

Both use the ordinary selected-source authorization/grounding contract unless an explicitly separate agentic voice mode is later designed. A native mobile client is not required: a capable browser may provide microphone capture/duplex transport, while unsupported browsers fall back to text chat.

## 4.1 Recorded-audio source capture

The announced mobile lecture/thought recorder is acquisition UX over the audio ingestion pipeline, not a new source model. The responsive web client MAY record microphone audio with explicit permission, upload the completed recording as an ordinary immutable audio source, then run the normal STT/canonicalization job. Recording must show a clear active-state indicator, allow cancellation before commit and never begin in the background. Native share-sheet and offline-app integration remain out of scope.


## 5. Video Overview pipeline

```text
sources
 -> storyboard
 -> narration/script
 -> visual plan
 -> source imagery / charts / generated imagery
 -> timing
 -> TTS
 -> composition/render
 -> final video
```

## 6. Video modes and Cinematic mode

The current parity baseline includes **Explainer**, **Short**, and **Cinematic** formats. In the documented reference UI, predefined/custom visual-style controls apply to **Explainer** and explicitly exclude Short and Cinematic; steering prompts remain a separate customization mechanism. Short is approximately 60 seconds. Current reference help documents broad multilingual Video Overview support but currently limits Cinematic to English. This project does not hard-code that vendor limitation: exact per-mode language coverage is provider/capability metadata, and the UI MUST not offer an unsupported combination. Higher-production Cinematic video may require external generative-video providers because local capability may lag. It remains an optional provider role; absence of such a provider should not prevent ordinary video-overview generation from source imagery, generated stills, motion graphics and narration. Any external media-generation API use follows the same external-provider disclosure policy as LLM calls.

## 7. Media provenance

Generated assets store provider/model metadata and source/evidence linkage. Source-derived images must retain source-version and location metadata where possible.

## 7.1 Provider-supplied media provenance

If a media provider returns provenance/watermark metadata, the platform SHOULD preserve it with the generated asset. Building a separate watermarking subsystem is not required for baseline parity.

## 7.2 Generated-media validation and renditions

Local or provider-produced media is untrusted binary input. Before publication, a media worker MUST independently identify and validate container/MIME type, codecs/tracks, duration, dimensions/resolution, frame/sample rates and configured size/resource limits rather than trusting filename or provider headers. Malformed, polyglot, active-content or limit-violating output fails safely. Validation/transcoding/rendering processes run outside the main application process with no ambient application/provider secrets, controlled input/output paths, bounded resources and no network unless a separately authorized provider step requires it.

The stored `ArtifactVersion` distinguishes original provider output from derived playback/download renditions. Browser-compatible transcodes, thumbnails/poster frames, waveforms, captions/transcripts and other derivatives record parent asset, tool/version/settings, size/hash and validation result. Regenerating a rendition never mutates the retained original or its generation manifest. Garbage collection and purge traverse both originals and every derivative.

## 7.3 Safety, refusals and rights metadata

The installation MUST have an explicit policy surface for media generation rather than inheriting inconsistent provider defaults invisibly. Provider safety/refusal results are normalized as structured terminal outcomes with provider/reason metadata safe to show to the user; automatic fallback MUST NOT be used to evade an installation policy or deliberately route around a safety refusal. An administrator may configure allowed providers/capabilities and age/sensitive-content restrictions appropriate to the installation. Provider-returned safety labels, content credentials, watermarks and rights/usage metadata are preserved where available. The platform does not claim that generated media is factually correct, rights-cleared or safe merely because a provider returned it.

## 8. Storage and lifecycle

Media outputs can be large. Object storage must support streaming upload/download, checksums, garbage collection of obsolete renders and retention policies while preserving artifact metadata.

Audio/video viewers SHOULD provide the ordinary playback controls documented by the reference product (seek, playback speed where meaningful, full screen for video, background audio playback within the web app, feedback, download and sharing subject to policy). These are viewer capabilities over the same `ArtifactVersion`; they do not justify separate domain types.

The technical specification MUST select browser-supported baseline containers/codecs and a fallback transcoding policy. Video/audio delivery supports HTTP byte ranges or an equivalent seekable streaming mechanism, correct content length/type/range metadata and authorization on every rendition request. Adaptive streaming is optional unless required by the selected size/network profile. A missing optional high-end video provider degrades Cinematic or provider-specific generation only; existing artifacts, ordinary composed Video Overviews and unrelated notebook functions remain usable.
