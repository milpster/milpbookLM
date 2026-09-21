# ADR 0003 — Local chat selection: Swift-Qwen3.8-27B-Q6_K

- Status: accepted for the reference installation
- Date: 2026-09-21
- Task: 19 (MOD-01b), ARCH-23-001..004

## Context

The original task text named Muse Glimmer-30B as a candidate. D16 supersedes
that text after the operator directed the project to use the already deployed
production configuration and prohibited all model acquisitions. The selected
deployment is Swift-Qwen3.8-27B-Q6_K at `127.0.0.1:8009`, launched by
`/home/srcds/dev/uf3_rocm6.1_llama.cpp/swift_llama_start-q6_f16_f16.sh`.
No model was downloaded or loaded for this decision, and the running service
was not restarted or reconfigured.

## Decision

Select Swift-Qwen3.8-27B-Q6_K as the local ordinary-chat reference. Keep the
provider-neutral chat port and route identifier `llama_cpp_local`; the model
name does not enter notebook domain data. The Glimmer candidate is rejected
for this installation because it would require an unapproved acquisition and
has no on-host evidence here.

## Alternatives

1. Muse Glimmer-30B: rejected by D16 and lacks on-host evidence.
2. A new downloaded Qwen-family quant: rejected by the no-acquisition order.
3. External-only chat: rejected because local-first is the frozen policy.

## Selection record

1. **License and supply chain**: llama.cpp is MIT-licensed. The local GGUF is
   immutable for this selection at SHA-256
   `7f4de8abd5446c08b0f975a1b38e43d02639f4ae9ecdd2ddfd5c5b0f612bda59`.
   The artifact's embedded/local inventory does not establish the derivative
   model's redistribution license, so this ADR authorizes on-host use only;
   redistribution remains blocked pending a provenance/license manifest.
2. **Version/digest and capability/quality benchmark**: Q6_K model digest
   above; llama.cpp tree `969bce4d2fc5b14faed90f047b05adac8f41ef86`;
   server fingerprint `b11380-969bce4d2`. After one discarded warmup, 15
   sequential short DE/EN calls produced 1,172 completion tokens at mean
   32.22 tokens/s (range 16.06–67.92) and mean total latency 3.798 s. A
   streaming probe observed first response bytes at 0.141 s. The six-case
   grounding rubric scored factuality-with-citation 5/6, language quality
   5/6, and refusal/abstention 1/2. The failed case was German unanswerability:
   reasoning consumed the 128-token cap before visible output. The weakness is
   retained, not hidden. Full values are in
   `tests/evaluation/model-selection-benchmark-v1.json`.
3. **Hardware/resource envelope and privacy class**: local/private processing;
   two Radeon VII cards (gfx906 silicon, exposed as gfx900 by the configured
   HSA override), ROCm userspace path 6.1.0, 227k context, DFlash2 plus
   ngram-mod speculative decoding, f16 K/V. During probes the two cards used
   17,052,934,144 and 17,116,512,256 bytes of VRAM. The launcher journal adds
   its E82/E83 production lane: PP16384 ~369, fill120k ~327, TG ~13.3 t/s,
   canonical SHA gate passing. Those values are supporting operator evidence,
   not compared with this short-call regime.
4. **Deterministic fake**: the existing fake chat provider and normalized
   provider-event fixtures remain the CI oracle. Live outputs are not golden
   prose; temperature zero, response hashes, model/build identity, and rubric
   judgments make the hardware run auditable.
5. **Fallback/degraded behavior**: route local first. If local chat is
   unhealthy and external disclosure/policy/credentials permit, try Big
   Pickle then Muse Spark Standard. With the current external probe outcomes,
   effective operation is local-only. A German no-visible-answer result is a
   failed generation, never an empty successful answer.
6. **Rollback**: restore the prior operator-approved launcher/build/model
   tuple and update this ADR plus the routing record after rerunning corpora
   v1. Notebook data and canonical sources are unchanged.

## Compatibility, security and privacy consequences

The decision preserves the existing provider contract, disclosure controls,
and local content boundary. Prompt logs configured by the production launcher
are operationally sensitive and remain host-local. The model may not decide
authorization or citation validity.

## Migration / rollback

No schema migration. Rollback is a routing/configuration change to another
benchmarked local provider; generated metadata retains the actual provider,
model digest, build fingerprint, and recipe.

## Affected requirement IDs and tests

ARCH-23-001..004, ARCH-10 local-provider subset, ARCH-18-003..004, AD-011,
D16, EVAL-GATE-001 v1, and the DE/EN live rubric in the benchmark report.

## Reconsideration trigger

Reconsider after a reviewed license/provenance change, model/build digest
change, material EVAL-GATE regression, repeated German abstention failure, or
a hardware/topology change. A replacement requires new on-host evidence.
