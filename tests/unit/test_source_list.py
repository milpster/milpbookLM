from __future__ import annotations

import uuid
from unittest.mock import Mock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from milpbooklm_adapters.security.fakes import InMemoryNotebookReader
from milpbooklm_api.deps import ApiDeps
from milpbooklm_api.security import Principal
from milpbooklm_api.source_routes import build_source_router
from milpbooklm_application.policy_engine import PolicyEngine
from milpbooklm_application.ports import NotebookView
from milpbooklm_application.source_acquisition import AcquireSource, SourceView
from milpbooklm_domain.identity import User
from milpbooklm_domain.ownership import MembershipRole
from milpbooklm_domain.sources import Availability, SourceType
from starlette import status

ROOT_NODE_ID = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")


class SourceListCatalog:
    def __init__(self, sources: list[SourceView]) -> None:
        self.sources = sources
        self.calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def list(self, notebook_id: uuid.UUID, actor_id: uuid.UUID) -> list[SourceView]:
        self.calls.append((notebook_id, actor_id))
        return self.sources


def _client(member: bool) -> tuple[TestClient, SourceListCatalog, uuid.UUID, uuid.UUID]:
    actor_id = uuid.uuid4()
    notebook_id = uuid.uuid4()
    user = User(actor_id, "reader@example.com", "Reader")
    principal = Principal(user, uuid.uuid4(), "token", "csrf")
    readers = InMemoryNotebookReader()
    if member:
        readers.add_view(
            actor_id,
            NotebookView(notebook_id, "Sources", "none", MembershipRole.OWNER),
        )
    source = SourceView(
        uuid.uuid4(),
        uuid.uuid4(),
        notebook_id,
        SourceType.PLAIN_TEXT,
        "Persisted source",
        Availability.ACTIVE,
        "a" * 64,
        42,
        "active",
        "0",
        uuid.uuid4(),
        ROOT_NODE_ID,
    )
    catalog = SourceListCatalog([source])
    deps = Mock(spec=ApiDeps)
    deps.notebooks = readers
    deps.engine = PolicyEngine()

    async def resolve_principal(_request: Request) -> Principal:
        return principal

    app = FastAPI()
    app.include_router(
        build_source_router(
            deps,
            resolve_principal,
            Mock(spec=AcquireSource),
            catalog,
        )
    )
    return TestClient(app), catalog, notebook_id, actor_id


def test_list_sources_returns_persisted_versions_for_member() -> None:
    # Given
    client, catalog, notebook_id, actor_id = _client(member=True)

    # When
    response = client.get("/api/v1/sources", params={"notebook_id": str(notebook_id)})

    # Then
    assert response.status_code == status.HTTP_200_OK
    assert response.json()[0]["display_title"] == "Persisted source"
    assert response.json()[0]["canonical_root_node_id"] == str(ROOT_NODE_ID)
    assert catalog.calls == [(notebook_id, actor_id)]


def test_list_sources_hides_notebook_from_non_member() -> None:
    # Given
    client, catalog, notebook_id, _actor_id = _client(member=False)

    # When
    response = client.get("/api/v1/sources", params={"notebook_id": str(notebook_id)})

    # Then
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert catalog.calls == []
