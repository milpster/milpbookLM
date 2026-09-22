"""Shared typed HTTP boundary helpers for source routes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi.responses import JSONResponse
from milpbooklm_application.policy_engine import NotebookAccess
from milpbooklm_application.source_acquisition import SourceView
from milpbooklm_domain.policy import PolicyAction
from pydantic import BaseModel, ConfigDict, Field

from .deps import ApiDeps
from .security import Principal

type JsonScalar = str | int | float | bool | None


class PasteTextRequest(BaseModel):
    """Paste-text acquisition boundary."""

    model_config = ConfigDict(frozen=True)

    notebook_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    text: str


class WebUrlRequest(BaseModel):
    """Web URL snapshot acquisition boundary."""

    model_config = ConfigDict(frozen=True)

    notebook_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)


class RenameSourceRequest(BaseModel):
    """Metadata-only source rename boundary."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=300)


def source_payload(view: SourceView, job_id: uuid.UUID | None = None) -> dict[str, JsonScalar]:
    """Serialize an acquisition-stage source without exposing storage paths."""
    payload: dict[str, JsonScalar] = {
        "source_id": str(view.source_id),
        "source_version_id": str(view.source_version_id),
        "notebook_id": str(view.notebook_id),
        "source_type": view.source_type.value,
        "display_title": view.display_title,
        "availability": view.availability.value,
        "content_sha256": view.content_sha256,
        "content_size_bytes": view.content_size_bytes,
        "status": "quarantined_identified",
        "pipeline_status": view.version_status,
        "etag": view.etag,
    }
    if job_id is not None:
        payload["job_id"] = str(job_id)
    return payload


def problem(code: str, detail: str, http_status: int) -> JSONResponse:
    """Return RFC 9457-shaped source errors with a stable machine code."""
    return JSONResponse(
        status_code=http_status,
        media_type="application/problem+json",
        content={
            "type": f"urn:milpbooklm:problem:{code}",
            "title": "Source acquisition rejected",
            "status": http_status,
            "code": code,
            "detail": detail,
        },
    )


def authorize_notebook(
    deps: ApiDeps,
    principal: Principal,
    notebook_id: uuid.UUID,
    action: PolicyAction,
) -> JSONResponse | None:
    """Apply membership-filtered lookup and the shared policy engine."""
    notebook = deps.notebooks.notebook_with_membership(principal.user.id, notebook_id)
    if notebook is None:
        return JSONResponse(status_code=404, content={"detail": "notebook not found"})
    decision = deps.engine.decide_notebook(
        principal.user,
        NotebookAccess(notebook_id=notebook_id, role=notebook.membership),
        action,
    )
    if decision.allowed:
        return None
    return JSONResponse(status_code=403, content={"detail": {"reason": decision.reason.value}})


async def single_chunk(data: bytes) -> AsyncIterator[bytes]:
    """Adapt paste text to the same streaming acquisition port as uploads."""
    yield data
