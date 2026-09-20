"""Model provider adapters and deterministic prototype fakes."""

from milpbooklm_adapters.models.fakes import FakeProvider, FakeScenario
from milpbooklm_adapters.models.openai_compat import (
    BIG_PICKLE_NAME,
    LLAMA_CPP_LOCAL_NAME,
    MUSE_SPARK_STANDARD_NAME,
    LlamaCppAdapter,
    OpenAICompatibleAdapter,
    OpenAIProviderConfig,
)
from milpbooklm_adapters.models.pg_registry import PgProviderRegistry

__all__ = [
    "BIG_PICKLE_NAME",
    "LLAMA_CPP_LOCAL_NAME",
    "MUSE_SPARK_STANDARD_NAME",
    "FakeProvider",
    "FakeScenario",
    "LlamaCppAdapter",
    "OpenAICompatibleAdapter",
    "OpenAIProviderConfig",
    "PgProviderRegistry",
]
