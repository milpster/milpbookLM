"""The typed recipe registry and the deterministic composite-echo demo recipe."""

from __future__ import annotations

import json
import uuid

import pytest
from milpbooklm_application.artifact_recipes import (
    COMPOSITE_ECHO_RECIPE_ID,
    COMPOSITE_ECHO_RECIPE_VERSION,
    CompositeEchoRecipe,
    build_recipe_registry,
)
from milpbooklm_domain.artifacts import (
    ArtifactRequest,
    ArtifactType,
    FrozenInputs,
)
from milpbooklm_domain.manifests import ManifestItem
from milpbooklm_domain.notes import ContentKind


def _inputs(*source_ids: uuid.UUID) -> FrozenInputs:
    items = tuple(
        ManifestItem(ContentKind.SOURCE_VERSION, source_id) for source_id in source_ids
    )
    return FrozenInputs(uuid.uuid4(), items, {"title": "t"})


def _request(*source_ids: uuid.UUID) -> ArtifactRequest:
    return ArtifactRequest(
        notebook_id=uuid.uuid4(),
        artifact_type=ArtifactType.COMPOSITE,
        title="Echo",
        instructions=None,
        source_version_ids=source_ids,
    )


def test_registry_is_typed_and_only_composite_is_registered() -> None:
    registry = build_recipe_registry()
    assert registry.registered_types() == frozenset({ArtifactType.COMPOSITE})
    recipe = registry.get(ArtifactType.COMPOSITE)
    assert recipe is not None
    assert recipe.recipe_id == COMPOSITE_ECHO_RECIPE_ID
    assert recipe.recipe_version == COMPOSITE_ECHO_RECIPE_VERSION
    assert registry.get(ArtifactType.REPORT) is None
    assert registry.get(ArtifactType.QUIZ) is None


def test_validate_request_rejects_empty_inputs() -> None:
    recipe = CompositeEchoRecipe()
    with pytest.raises(ValueError, match="at least one frozen input"):
        recipe.validate_request(_request())


def test_generation_is_deterministic_over_frozen_inputs() -> None:
    recipe = CompositeEchoRecipe()
    source = uuid.uuid4()
    request = _request(source)
    inputs = _inputs(source)
    plan = recipe.plan(request, inputs)
    first = recipe.generate(request, inputs, plan)
    second = recipe.generate(request, inputs, recipe.plan(request, inputs))
    assert first == second
    assert recipe.validate_content(first, inputs) == ()
    assert first["title"] == "Echo"
    sections = first["sections"]
    assert isinstance(sections, list)
    assert len(sections) == 1
    assert sections[0]["source_refs"] == [str(source)]


def test_different_inputs_yield_different_fingerprints() -> None:
    recipe = CompositeEchoRecipe()
    a_request, a_inputs = _request(uuid.uuid4()), _inputs(uuid.uuid4())
    b_request, b_inputs = _request(uuid.uuid4()), _inputs(uuid.uuid4())
    a = recipe.generate(a_request, a_inputs, recipe.plan(a_request, a_inputs))
    b = recipe.generate(b_request, b_inputs, recipe.plan(b_request, b_inputs))
    assert a["content_sha256"] != b["content_sha256"]


def test_render_produces_canonical_json_rendition() -> None:
    recipe = CompositeEchoRecipe()
    source = uuid.uuid4()
    request = _request(source)
    inputs = _inputs(source)
    content = recipe.generate(request, inputs, recipe.plan(request, inputs))
    (rendition,) = recipe.render(content)
    assert rendition.format == "json"
    assert json.loads(rendition.content.decode("utf-8")) == content
    # Canonical: key-sorted, compact.
    assert rendition.content == json.dumps(
        content, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_validate_content_flags_tampered_payload() -> None:
    recipe = CompositeEchoRecipe()
    source = uuid.uuid4()
    request = _request(source)
    inputs = _inputs(source)
    content = recipe.generate(request, inputs, recipe.plan(request, inputs))
    tampered = dict(content)
    sections = [dict(s) for s in content["sections"]]
    sections[0] = {**sections[0], "text": "tampered"}
    tampered["sections"] = sections
    problems = recipe.validate_content(tampered, inputs)
    assert any("content_sha256" in problem for problem in problems)
