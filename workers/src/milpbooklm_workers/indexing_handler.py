"""
Source index job handler (IDX-01, ch15): kind ``ingestion.index``.

Executes the resumable generation build (chunk -> persist -> embed -> atomic
swap) through the application pipeline. Idempotent under lease-recovery
re-execution: the generation row and chunk IDs already persisted are detected
and skipped, and a ``ready`` generation returns its count without re-running.
A build failure marks the generation explicitly ``failed`` (visible state,
never a silent partial) before the job itself is failed by the loop.
"""

from __future__ import annotations

import json
import logging
import uuid

from milpbooklm_application.indexing import (
    BuildSourceIndex,
    EmbeddingDimensionMismatchError,
    GenerationIdentity,
    IndexGenerationError,
    ProgressCallback,
    config_from_payload,
)
from milpbooklm_domain.jobs import JobRecord

from milpbooklm_workers.handlers import HandlerCancelledError, JobContext, JobResult

logger = logging.getLogger(__name__)


class SourceIndexHandler:
    """One durable job: build (or resume) the source's index generation."""

    kind = "ingestion.index"

    def __init__(self, build: BuildSourceIndex) -> None:
        """Wire the resumable build pipeline."""
        self._build = build

    def run(self, job: JobRecord, context: JobContext) -> JobResult:
        """Build the generation; mark it failed on an explicit build error."""
        payload = job.payload
        identity = GenerationIdentity(
            generation_id=_payload_uuid(payload, "generation_id"),
            notebook_id=_payload_uuid(payload, "notebook_id"),
            source_id=_payload_uuid(payload, "source_id"),
            source_version_id=_payload_uuid(payload, "source_version_id"),
            canonical_document_id=_payload_uuid(payload, "canonical_document_id"),
        )
        config = config_from_payload(payload)
        if context.should_stop():
            raise HandlerCancelledError()
        try:
            chunk_count = self._build.run(
                identity,
                config,
                progress=self._progress(context),
            )
        except EmbeddingDimensionMismatchError:
            self._build_fail(identity, "embedding_dimension_mismatch")
            raise
        except IndexGenerationError:
            self._build_fail(identity, "index_build_failed")
            raise
        except Exception:
            # Unexpected failures (SQL, network) must also record the state;
            # a generation left "building" would look resumable forever.
            self._build_fail(identity, "index_build_failed")
            raise
        context.progress("ready", 1.0, f"{chunk_count} chunks ready")
        result = {
            "generation_id": str(identity.generation_id),
            "chunks": chunk_count,
        }
        return JobResult(result_ref=json.dumps(result, sort_keys=True))

    @staticmethod
    def _progress(context: JobContext) -> ProgressCallback:
        """Adapt the pipeline's (phase, done, total, status) report to the job context."""

        def report(phase: str, done: int, total: int, status: str | None) -> None:
            context.progress(phase, done / total if total else 1.0, status)

        return report

    def _build_fail(self, identity: GenerationIdentity, error_code: str) -> None:
        logger.error(
            "index generation %s failed: %s", identity.generation_id, error_code
        )
        try:
            self._build.mark_generation_failed(identity.generation_id, error_code)
        except Exception:
            logger.exception("failed to record generation failure state")


def _payload_uuid(payload: dict[str, object], key: str) -> uuid.UUID:
    value = payload.get(key)
    if not isinstance(value, str):
        raise IndexGenerationError(f"missing payload key: {key}")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise IndexGenerationError(f"invalid payload key: {key}") from exc
