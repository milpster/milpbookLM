from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from milpbooklm_adapters.note_transform import LlamaCppNoteTransformProvider
from milpbooklm_application.note_core import NoteRevisionView, NoteTransformKind


@pytest.mark.parametrize("kind", tuple(NoteTransformKind))
def test_transform_returns_validated_content_for_each_supported_kind(
    kind: NoteTransformKind,
) -> None:
    # Given
    expected: dict[str, object] = {
        "blocks": [{"type": "paragraph", "text": kind.value}]
    }

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["user"] == f"note-transform:{kind.value}"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"content": expected})}}
                ]
            },
        )

    provider = LlamaCppNoteTransformProvider(
        base_url="http://test.invalid/v1",
        model="test-model",
        transport=httpx.MockTransport(respond),
    )
    revision = NoteRevisionView(
        revision_id=uuid.uuid4(),
        note_id=uuid.uuid4(),
        revision_number=1,
        content={"blocks": [{"type": "paragraph", "text": "source"}]},
        content_sha256="sha256",
        author_user_id=uuid.uuid4(),
        provenance_refs=(),
        content_dependencies=(),
        created_at=datetime.now(UTC),
    )

    # When
    transformed = provider.transform(kind, (revision,))

    # Then
    assert transformed == expected
