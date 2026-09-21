"""
Synchronous llama.cpp embedding client (IDX-01, D14).

Talks the OpenAI-compatible ``/v1/embeddings`` endpoint of a local
llama-server in embedding mode (bge-m3, 1024-dim, L2-normalized). Batches are
deterministic: the request preserves chunk order, the response is reordered by
``index`` back into input order, and the dimension is verified against the
generation's recorded dimension - a mismatch raises
:class:`EmbeddingDimensionMismatchError` (a dimension change is a NEW parallel
generation, never an in-place reinterpretation).

Prototype deviation (recorded in the task report): direct synchronous calls to
the local server instead of the async streaming ``EmbeddingProvider`` port;
orchestrator (T10) integration is later work.
"""

from __future__ import annotations

import logging
import time

import httpx
from milpbooklm_application.indexing import EmbeddingDimensionMismatchError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5
_SERVER_ERROR_MIN_STATUS = 500


class EmbeddingProviderError(RuntimeError):
    """The embedding endpoint failed permanently (transport or protocol)."""


class LlamaCppEmbeddingClient:
    """One local llama-server embedding endpoint behind the indexing port."""

    def __init__(self, base_url: str, model: str, *, timeout_seconds: float = 120.0) -> None:
        """Bind the server root, model name, and a generous batch timeout."""
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=timeout_seconds)

    @property
    def model(self) -> str:
        """The served model name (recorded on the generation)."""
        return self._model

    def embed(
        self, texts: tuple[str, ...], expected_dimension: int
    ) -> tuple[tuple[float, ...], ...]:
        """Embed one batch in deterministic order; verify the recorded dimension."""
        if not texts:
            return ()
        url = f"{self._base_url}/v1/embeddings"
        payload = {"model": self._model, "input": list(texts)}
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                started = time.monotonic()
                response = self._client.post(url, json=payload)
                if response.status_code >= _SERVER_ERROR_MIN_STATUS:
                    raise EmbeddingProviderError(
                        f"embedding endpoint returned HTTP {response.status_code}"
                    )
                response.raise_for_status()
                data = response.json()
                items = sorted(
                    data.get("data", []), key=lambda item: int(item.get("index", 0))
                )
                vectors = tuple(
                    tuple(float(component) for component in item["embedding"])
                    for item in items
                )
                elapsed_ms = (time.monotonic() - started) * 1000
                logger.info(
                    "embedding batch: %d texts, %.1f ms, model=%s",
                    len(texts),
                    elapsed_ms,
                    self._model,
                )
                self._verify(texts, vectors, expected_dimension)
                return vectors
            except EmbeddingDimensionMismatchError:
                raise
            except (
                EmbeddingProviderError,
                httpx.HTTPError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                if attempt < MAX_ATTEMPTS:
                    time.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
        raise EmbeddingProviderError(
            f"embedding batch failed after {MAX_ATTEMPTS} attempts"
        ) from last_error

    @staticmethod
    def _verify(
        texts: tuple[str, ...], vectors: tuple[tuple[float, ...], ...], expected_dimension: int
    ) -> None:
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                f"embedding endpoint returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        for vector in vectors:
            if len(vector) != expected_dimension:
                raise EmbeddingDimensionMismatchError(
                    f"model returned dimension {len(vector)}, "
                    f"generation records {expected_dimension}; "
                    "create a new parallel generation instead of reinterpreting"
                )
