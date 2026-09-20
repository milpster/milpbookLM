"""Local inference process lifecycle, GPU policy, serial queues, and preemption."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import anyio
from anyio.abc import Process
from milpbooklm_application.job_ports import JobRepository
from milpbooklm_domain.jobs import JobRecord, JobState


class ModelWorkload(StrEnum):
    """GPU residency groups from the D10 local inference policy."""

    EMBEDDING = "embedding"
    RERANKER = "reranker"
    CHAT = "chat"
    MEDIA = "media"


HOT_WORKLOADS = frozenset(
    {ModelWorkload.EMBEDDING, ModelWorkload.RERANKER, ModelWorkload.CHAT}
)


@dataclass(frozen=True, slots=True)
class LocalModelSpec:
    """One administrator-configured local process command."""

    model_id: str
    workload: ModelWorkload
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelHealth:
    """Capability health projection consumed by the capability registry."""

    model_id: str
    available: bool
    loaded: bool
    reason: str | None = None


class ProcessController(Protocol):
    """Process operations isolated for deterministic orchestration fakes."""

    async def start(self, spec: LocalModelSpec) -> None:
        """Start one model process."""
        ...

    async def stop(self, model_id: str) -> None:
        """Stop one model process."""
        ...

    def running(self, model_id: str) -> bool:
        """Return whether one model process is live."""
        ...


class AnyioProcessController:
    """AnyIO-backed local subprocess controller."""

    def __init__(self) -> None:
        """Create an empty mutable process table owned by this controller."""
        self._processes: dict[str, Process] = {}

    async def start(self, spec: LocalModelSpec) -> None:
        """Start one configured model process."""
        self._processes[spec.model_id] = await anyio.open_process(spec.command)

    async def stop(self, model_id: str) -> None:
        """Terminate and reap one configured model process."""
        process = self._processes.pop(model_id)
        process.terminate()
        await process.wait()

    def running(self, model_id: str) -> bool:
        """Report whether the process is still live."""
        process = self._processes.get(model_id)
        return process is not None and process.returncode is None


class FakeProcessController:
    """Deterministic in-process lifecycle fake for offline prototype operation."""

    def __init__(self) -> None:
        """Initialize empty running/start/stop state."""
        self.running_models: set[str] = set()
        self.start_count: dict[str, int] = {}
        self.stop_count: dict[str, int] = {}

    async def start(self, spec: LocalModelSpec) -> None:
        """Record a deterministic process start."""
        await anyio.sleep(0)
        self.running_models.add(spec.model_id)
        self.start_count[spec.model_id] = self.start_count.get(spec.model_id, 0) + 1

    async def stop(self, model_id: str) -> None:
        """Record a deterministic process stop."""
        await anyio.sleep(0)
        self.running_models.remove(model_id)
        self.stop_count[model_id] = self.stop_count.get(model_id, 0) + 1

    def running(self, model_id: str) -> bool:
        """Return deterministic process state."""
        return model_id in self.running_models


@dataclass(slots=True)
class _ModelState:
    """Mutable lifecycle state protected by the model-specific lock."""

    lock: anyio.Lock
    serial: anyio.Lock
    references: int = 0


class InferenceProcessManager:
    """Single-flight, refcounted lifecycle with one serial execution queue per model."""

    def __init__(
        self, specs: Sequence[LocalModelSpec], controller: ProcessController
    ) -> None:
        """Wire model specs and allocate synchronization state."""
        self._specs: Mapping[str, LocalModelSpec] = {spec.model_id: spec for spec in specs}
        self._controller = controller
        self._states = {
            model_id: _ModelState(lock=anyio.Lock(), serial=anyio.Lock())
            for model_id in self._specs
        }
        self._gpu_changed = anyio.Condition()

    async def load(self, model_id: str) -> None:
        """Acquire a model reference, starting it exactly once under concurrent loads."""
        spec = self._specs[model_id]
        state = self._states[model_id]
        async with self._gpu_changed:
            while self._has_active_conflict(spec):
                await self._gpu_changed.wait()
            if spec.workload is ModelWorkload.MEDIA:
                await self._evict_idle_hot_models()
            # Reserve BEFORE the (slow) start: the reference must be visible while the
            # process boots, otherwise a conflicting workload would slip in and the
            # gate would only wake up after the fact.
            state.references += 1
        if not self._controller.running(model_id):
            async with state.lock:
                if not self._controller.running(model_id):
                    await self._controller.start(spec)

    async def unload(self, model_id: str) -> None:
        """Release a model and stop cold models after their final reference."""
        state = self._states[model_id]
        async with state.lock:
            if state.references == 0:
                return
            state.references -= 1
            spec = self._specs[model_id]
            if state.references == 0 and spec.workload not in HOT_WORKLOADS:
                await self._controller.stop(model_id)
        async with self._gpu_changed:
            self._gpu_changed.notify_all()

    @asynccontextmanager
    async def serial_session(self, model_id: str) -> AsyncIterator[None]:
        """Load, serialize one inference operation, then release its reference."""
        await self.load(model_id)
        try:
            async with self._states[model_id].serial:
                yield
        finally:
            await self.unload(model_id)

    def health(self, model_id: str) -> ModelHealth:
        """Expose model-load state for capability degradation reporting."""
        loaded = self._controller.running(model_id)
        return ModelHealth(
            model_id=model_id,
            available=model_id in self._specs,
            loaded=loaded,
            reason=None if loaded else "model_not_loaded",
        )

    def _has_active_conflict(self, requested: LocalModelSpec) -> bool:
        if requested.workload is ModelWorkload.MEDIA:
            return any(
                self._states[model_id].references > 0
                for model_id, spec in self._specs.items()
                if spec.workload in HOT_WORKLOADS
            )
        return any(
            self._states[model_id].references > 0
            for model_id, spec in self._specs.items()
            if spec.workload is ModelWorkload.MEDIA
        )

    async def _evict_idle_hot_models(self) -> None:
        for model_id, spec in self._specs.items():
            if (
                spec.workload in HOT_WORKLOADS
                and self._states[model_id].references == 0
                and self._controller.running(model_id)
            ):
                await self._controller.stop(model_id)


class InteractivePreemptor:
    """Checkpoint and durably park running batch media for interactive work."""

    def __init__(self, repo: JobRepository) -> None:
        """Wire the existing job repository state machine."""
        self._repo = repo

    def preempt_media(self, job: JobRecord, manifest_checkpoint: dict[str, object]) -> JobRecord:
        """Move running media to waiting_capacity without introducing a new job state."""
        checkpointed = self._repo.record_progress(
            job,
            checkpoint=manifest_checkpoint,
            lease_seconds=1,
        )
        if checkpointed is None:
            return job
        return self._repo.transition(
            checkpointed,
            JobState.WAITING_CAPACITY,
            checkpoint=manifest_checkpoint,
            lease_owner=None,
            lease_expires_at=None,
        )
