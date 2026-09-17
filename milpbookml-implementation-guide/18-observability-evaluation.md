# 18 — Observability and Evaluation Implementation

## Telemetry

Use OpenTelemetry-compatible internal interfaces. Propagate correlation/trace IDs through HTTP, jobs, provider calls and events. Structured logs redact prompts, source content, tokens, cookies and credentials by default.

## Metrics

Publish request/job latency and failure, queue age, lease recovery, parser failures, blob integrity, provider latency/usage/fallback, retrieval candidate counts/latency, citation validation failure, cache hit rate and capability health. Labels must be bounded and contain no user/content identifiers.

## Evaluation harness

Version corpora, judgments, prompts, provider/model configs and scorer versions. Store per-run results plus aggregate confidence intervals where applicable. Compare retrieval, citation, grounding, abstention, instruction following and media/artifact schema validity separately.

## Release oracle

Quality gates use predetermined metrics/thresholds and a locked holdout set. A model-graded rubric is supplementary and records grader identity/configuration; it cannot override deterministic security, policy or provenance failures.

## Privacy

Production evaluation requires opt-in or administrator-approved sanitized datasets. Raw traces are private, access-controlled and retained for a finite configured period.
