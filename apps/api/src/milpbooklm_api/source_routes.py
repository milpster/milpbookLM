"""Source route composition with static collection paths before UUID paths."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from milpbooklm_application.public_video import AcquirePublicVideo
from milpbooklm_application.source_acquisition import AcquireSource, SourceCatalog
from milpbooklm_application.source_lifecycle import SourcePurge
from milpbooklm_application.web_fetch import AcquireWebSource
from milpbooklm_domain.policy import PolicyAction

from .deps import ApiDeps, PrincipalDependency
from .security import Principal
from .source_http import authorize_notebook, source_payload
from .source_import_routes import build_source_import_router
from .source_lifecycle_routes import build_source_lifecycle_router


def build_source_router(
    deps: ApiDeps,
    principal_dependency: PrincipalDependency,
    acquire: AcquireSource,
    catalog: SourceCatalog,
    *,
    acquire_web: AcquireWebSource | None = None,
    acquire_public_video: AcquirePublicVideo | None = None,
    purge: SourcePurge | None = None,
) -> APIRouter:
    """Build the complete ING-01a source route family."""
    router = APIRouter(prefix="/api/v1/sources", tags=["sources"])

    @router.get("", response_model=None)
    async def list_sources(
        notebook_id: uuid.UUID,
        principal: Principal = Depends(principal_dependency),
    ) -> JSONResponse:
        denied = authorize_notebook(
            deps,
            principal,
            notebook_id,
            PolicyAction.READ_CONTENT,
        )
        if denied is not None:
            return denied
        return JSONResponse(
            content=[
                source_payload(view)
                for view in catalog.list(notebook_id, principal.user.id)
            ]
        )
    router.include_router(
        build_source_import_router(
            deps, principal_dependency, acquire, acquire_web, acquire_public_video
        )
    )
    router.include_router(
        build_source_lifecycle_router(
            deps,
            principal_dependency,
            catalog,
            purge,
            acquire_web,
        )
    )
    return router
