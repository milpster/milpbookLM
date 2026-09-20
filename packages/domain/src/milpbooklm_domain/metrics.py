"""
Bounded-label metrics vocabulary (ch18 "Metrics"; pure domain, stdlib only).

The metric *names* and the *label key/value* vocabulary are fixed by explicit
enums/allowlists. Recording a sample validates every label against its allowlist
and raises :class:`MetricLabelError` on an unknown key or an out-of-allowlist value
- unbounded identifiers (user ids, notebook ids, raw routes, prompts, user-supplied
provider strings, exception messages) can never be introduced as labels, so
cardinality cannot explode.

This defines the typed names/records for the plan's metric families (request/job
latency+failure, queue age, lease recovery, blob integrity, provider
latency/usage/fallback, retrieval counts, citation-validation failures, capability
health) without a monitoring stack: there is no exporter here, only validated
samples and an in-process registry.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from milpbooklm_domain.blobs import ReconciliationClass
from milpbooklm_domain.jobs import CapacityClass


class MetricName(StrEnum):
    """The fixed, typed metric names (one per measurement family)."""

    REQUEST_LATENCY_SECONDS = "milpbooklm_request_latency_seconds"
    REQUEST_FAILURES_TOTAL = "milpbooklm_request_failures_total"
    JOB_LATENCY_SECONDS = "milpbooklm_job_latency_seconds"
    JOB_FAILURES_TOTAL = "milpbooklm_job_failures_total"
    JOB_QUEUE_AGE_SECONDS = "milpbooklm_job_queue_age_seconds"
    LEASE_RECOVERIES_TOTAL = "milpbooklm_lease_recoveries_total"
    BLOB_INTEGRITY_FINDINGS_TOTAL = "milpbooklm_blob_integrity_findings_total"
    PROVIDER_LATENCY_SECONDS = "milpbooklm_provider_latency_seconds"
    PROVIDER_USAGE_TOTAL = "milpbooklm_provider_usage_total"
    PROVIDER_FALLBACKS_TOTAL = "milpbooklm_provider_fallbacks_total"
    RETRIEVAL_CANDIDATES_TOTAL = "milpbooklm_retrieval_candidates_total"
    RETRIEVAL_LATENCY_SECONDS = "milpbooklm_retrieval_latency_seconds"
    CITATION_VALIDATION_FAILURES_TOTAL = "milpbooklm_citation_validation_failures_total"
    CAPABILITY_HEALTH = "milpbooklm_capability_health"


class LabelKey(StrEnum):
    """The fixed, allowed label keys."""

    OPERATION = "operation"
    OUTCOME = "outcome"
    CAPACITY_CLASS = "capacity_class"
    PROVIDER_KIND = "provider_kind"
    JOB_KIND = "job_kind"
    FINDING_KIND = "finding_kind"
    CAPABILITY = "capability"


# Bounded value allowlists: the ONLY values a label key may take.
_OPERATION = frozenset(
    {
        "http_request",
        "job",
        "lease_recovery",
        "blob_scan",
        "provider_call",
        "retrieval",
        "citation_validation",
        "capability",
    }
)
_OUTCOME = frozenset({"success", "failure", "timeout", "cancelled", "fallback"})
_PROVIDER_KIND = frozenset({"llama_cpp", "openai_compatible", "fake", "internal"})
_JOB_KIND = frozenset({"demo.echo", "blob.integrity_scan"})
_CAPABILITY = frozenset(
    {"interactive_text", "ingestion_indexing", "research_browser", "execution", "media"}
)

ALLOWED_LABEL_VALUES: Mapping[LabelKey, frozenset[str]] = {
    LabelKey.OPERATION: _OPERATION,
    LabelKey.OUTCOME: _OUTCOME,
    LabelKey.CAPACITY_CLASS: frozenset(c.value for c in CapacityClass),
    LabelKey.PROVIDER_KIND: _PROVIDER_KIND,
    LabelKey.JOB_KIND: _JOB_KIND,
    LabelKey.FINDING_KIND: frozenset(k.value for k in ReconciliationClass),
    LabelKey.CAPABILITY: _CAPABILITY,
}


class MetricLabelError(ValueError):
    """A metric label key is unknown or its value is outside the bounded allowlist."""


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One validated metric observation (name + bounded labels + value + time)."""

    name: MetricName
    labels: Mapping[LabelKey, str]
    value: float
    observed_at: datetime


def validate_labels(labels: Mapping[LabelKey, str]) -> dict[LabelKey, str]:
    """
    Validate labels against the bounded allowlists; return a canonical dict.

    Raises :class:`MetricLabelError` naming the first offending key/value. An empty
    label set is valid.
    """
    canonical: dict[LabelKey, str] = {}
    for key, value in labels.items():
        allowed = ALLOWED_LABEL_VALUES.get(key)
        if allowed is None:
            raise MetricLabelError(f"unknown metric label key: {key!r}")
        if value not in allowed:
            raise MetricLabelError(f"label {key!r} value {value!r} is not in the allowlist")
        canonical[key] = value
    return canonical


class MetricsRegistry:
    """
    In-process, label-validated metric sink (no exporter; the wave-2 surface).

    ``record`` validates labels (rejecting unbounded values) and appends a sample;
    ``collect`` returns a snapshot of every recorded sample.
    """

    def __init__(self) -> None:
        """Start an empty registry."""
        self._lock = threading.Lock()
        self._samples: list[MetricSample] = []

    def record(
        self,
        name: MetricName,
        value: float,
        observed_at: datetime,
        *,
        labels: Mapping[LabelKey, str] | None = None,
    ) -> MetricSample:
        """Validate and store one sample; return the stored sample."""
        sample = MetricSample(
            name=name,
            labels=validate_labels(labels or {}),
            value=value,
            observed_at=observed_at,
        )
        with self._lock:
            self._samples.append(sample)
        return sample

    def collect(self) -> tuple[MetricSample, ...]:
        """Return a snapshot of all recorded samples (insertion order)."""
        with self._lock:
            return tuple(self._samples)

    def __len__(self) -> int:
        """Return the number of recorded samples."""
        with self._lock:
            return len(self._samples)
