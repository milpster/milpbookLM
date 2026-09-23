"""Composition router for the STD-02a note HTTP surface."""

from fastapi import APIRouter

from .deps import ApiDeps, NoteDeps, PrincipalDependency
from .note_mutation_routes import build_note_mutation_router
from .note_read_routes import build_note_read_router


def build_note_router(
    deps: ApiDeps, principal_dependency: PrincipalDependency, note_deps: NoteDeps
) -> APIRouter:
    """Compose read and mutation routes under `/api/v1`."""
    router = APIRouter(prefix="/api/v1", tags=["notes"])
    router.include_router(build_note_read_router(deps, principal_dependency, note_deps))
    router.include_router(build_note_mutation_router(deps, principal_dependency, note_deps))
    return router
