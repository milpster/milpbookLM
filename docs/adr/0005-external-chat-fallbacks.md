# ADR 0005 — External chat fallbacks: Big Pickle then Muse Spark Standard

- Status: accepted routing policy; runtime degraded to local-only
- Date: 2026-09-21
- Task: 19 (MOD-01b), ARCH-23-001..004

## Context

AD-011 allows external fallback only after policy filtering and visible
disclosure. D2 fixes the order local, Big Pickle, Muse Spark. External
availability is not a phase blocker, and provider credentials were absent from
the task-19 environment.

## Decision

Lock the configured order `llama_cpp_local`, `big_pickle`,
`muse_spark_standard`. Big Pickle is attempted only while available and
permitted; a lapse, free-tier restriction, or failed health/auth probe skips
directly to Muse Spark Standard. Muse Spark is Standard tier only. Every
content-bearing external attempt requires authorization revalidation, policy
approval, credential ownership, and visible disclosure before dispatch.

## Alternatives

1. External-first: rejected by local-first policy.
2. Big Pickle as a dependency: rejected because availability is limited and
   direct use can lapse.
3. Silent fallback: rejected because it violates disclosure and privacy rules.

## Selection record

1. **License and supply chain**: both services are external proprietary
   dependencies configured only by endpoint/model identifiers and credentials;
   no vendor SDK is introduced. Big Pickle remains replaceable and carries
   provider-side limited-availability risk. Muse Spark Standard terms and
   account entitlement must be reviewed by the operator before enabling it.
2. **Version/digest and capability/quality benchmark**: endpoint/config
   identity is versioned by `model-routing-v1.json`; no stable server digest is
   exposed. On 2026-09-21 `https://opencode.ai/zen/v1/models` returned HTTP 200
   and advertised `big-pickle`, while direct chat returned HTTP 403 stating the
   free tier can only be used within OpenCode. `https://api.meta.ai/v1/models`
   and `/chat/completions` both returned HTTP 401 `invalid_api_key`. No external
   quality score is claimed without successful credentialed corpus execution.
3. **Hardware/resource envelope and privacy class**: provider hardware and
   region are unknown. Big Pickle is external/restricted-unknown because the
   documented free-period data may be used for improvement. Muse Spark
   Standard is external/non-training-tier per the selected service policy.
   Public, notebook-private, restricted, secret, and audit classes remain
   subject to installation/notebook policy; unknown properties never inherit
   local trust.
4. **Deterministic fake**: the existing OpenAI-compatible fake covers accepted,
   delta, usage, completion, refusal, timeout, quota, malformed response,
   cancellation, and disclosure-before-dispatch. Live external prose is never
   a CI dependency.
5. **Fallback/degraded behavior**: effective route is currently local-only.
   Big Pickle 403/lapse skips directly to Muse Spark Standard; Muse 401 or
   missing credential leaves local-only service. Fallback never crosses a
   local-only policy, never borrows another user's credential, and never joins
   two providers in one visible stream.
6. **Rollback**: disable either external route in installation policy/config
   and retain local operation. Removing Big Pickle leaves local then Muse
   Standard; removing all external routes leaves local-only. No notebook data
   migration is required.

## Compatibility, security and privacy consequences

The checked-in record is app-loadable through typed startup configuration.
External content dispatch remains disclosure-gated, metadata-audited, and
filtered by privacy policy. Credentials are references resolved only at
dispatch and are never committed to this routing file or evidence.

## Migration / rollback

No schema migration. Provider endpoint, credential, and availability changes
are configuration changes followed by compatibility and corpus probes.

## Affected requirement IDs and tests

ARCH-23-001..004, ARCH-10-012..016, ARCH-19 external-provider policy,
AD-004, AD-011, D2, the single routing-order unit test, and the recorded live
reachability probes.

## Reconsideration trigger

Reconsider on provider terms, retention/training policy, endpoint/auth changes,
Big Pickle lapse, a credentialed quality run, or a disclosure/policy failure.
