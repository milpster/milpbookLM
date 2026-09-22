"""Source route composition with static imports registered before UUID paths."""

from fastapi import APIRouter
from milpbooklm_application.source_acquisition import AcquireSource, SourceCatalog
from milpbooklm_application.web_fetch import AcquireWebSource

from .deps import ApiDeps, PrincipalDependency
from .source_import_routes import build_source_import_router
from .source_lifecycle_routes import build_source_lifecycle_router


def build_source_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    acquire: AcquireSource,
    catalog: SourceCatalog,
    acquire_web: AcquireWebSource | None = None,
) -> APIRouter:
    """Build the complete ING-01a source route family."""
    router = APIRouter(prefix="/api/v1/sources", tags=["sources"])
    router.include_router(
        build_source_import_router(deps, principal_dependency, acquire, acquire_web)
    )
    router.include_router(build_source_lifecycle_router(deps, principal_dependency, catalog))
    return router
