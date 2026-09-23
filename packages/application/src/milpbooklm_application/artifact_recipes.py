"""
Typed internal recipe registry + the deterministic composite demo recipe (STD-01).

Recipes register internally at startup through this typed registry - no runtime
code loading, no plugin surface (guide/13 Extension boundary, ARCH-13-013). The
real recipe families (reports/tables/mind-maps/flashcards/quizzes) are later
tasks (32-34); this task ships the contract + exactly one minimal concrete
recipe so the full pipeline (freeze -> plan -> generate -> validate -> render
-> publish) is exercised end to end.

The demo recipe (``composite_echo``) is honest, not a stub: it genuinely plans
and generates a versioned structured payload derived from the FROZEN manifest
inputs (deterministic, no model calls, no network) and validates it before
publication.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from milpbooklm_domain.artifacts import (
    CURRENT_PAYLOAD_SCHEMA_VERSION,
    ArtifactRecipe,
    ArtifactRequest,
    ArtifactType,
    FrozenInputs,
    Rendition,
)

COMPOSITE_ECHO_RECIPE_ID = "composite_echo"
COMPOSITE_ECHO_RECIPE_VERSION = "1.0.0"


class CompositeEchoRecipe:
    """
    Deterministic composite-echo recipe over frozen inputs (no model calls).

    Canonical payload (schema v2): a section per frozen input item, plus the
    echo of the request instructions. Every section records the source refs it
    derives from, so provenance is carried in the payload itself.
    """

    recipe_id = COMPOSITE_ECHO_RECIPE_ID
    recipe_version = COMPOSITE_ECHO_RECIPE_VERSION
    artifact_type = ArtifactType.COMPOSITE

    def validate_request(self, request: ArtifactRequest) -> None:
        """Validate that the composite substrate has at least one frozen input."""
        if request.artifact_type is not ArtifactType.COMPOSITE:
            raise ValueError(
                f"composite_echo serves composite artifacts, not {request.artifact_type.value}"
            )
        if not request.source_version_ids and not request.note_revision_ids:
            raise ValueError("a composite artifact needs at least one frozen input")

    def plan(self, request: ArtifactRequest, inputs: FrozenInputs) -> dict[str, object]:
        """Plan: one section per frozen input, in manifest order (deterministic)."""
        sections = [
            {
                "kind": "input_ref",
                "text": f"{item.kind.value}:{item.item_id}",
                "source_refs": [str(item.item_id)],
            }
            for item in inputs.items
        ]
        return {"sections": sections, "echo_instructions": request.instructions}

    def generate(
        self, request: ArtifactRequest, inputs: FrozenInputs, plan: dict[str, object]
    ) -> dict[str, object]:
        """Generate the versioned canonical payload from the frozen plan."""
        sections: list[dict[str, object]] = []
        instructions = plan.get("echo_instructions")
        if instructions:
            sections.append({"kind": "instructions", "text": instructions, "source_refs": []})
        sections.extend(
            dict(section) for section in plan.get("sections", ())  # type: ignore[attr-defined]
        )
        fingerprint = _payload_fingerprint(sections, request.title)
        return {
            "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
            "title": request.title,
            "recipe": self.recipe_id,
            "sections": sections,
            "content_sha256": fingerprint,
        }

    def validate_content(
        self, content: dict[str, object], inputs: FrozenInputs
    ) -> tuple[str, ...]:
        """Validate the payload: current schema version, non-empty, self-consistent."""
        problems: list[str] = []
        if content.get("schema_version") != CURRENT_PAYLOAD_SCHEMA_VERSION:
            problems.append(f"payload schema_version must be {CURRENT_PAYLOAD_SCHEMA_VERSION}")
        sections = content.get("sections")
        if not isinstance(sections, list) or not sections:
            problems.append("payload must carry a non-empty section list")
            return tuple(problems)
        for index, section in enumerate(sections):
            if not isinstance(section, dict) or not section.get("text"):
                problems.append(f"section {index} has no text")
        expected = _payload_fingerprint(sections, content.get("title", ""))
        if content.get("content_sha256") != expected:
            problems.append("payload content_sha256 does not match its sections")
        if not inputs.items:
            problems.append("payload was generated without any frozen input")
        return tuple(problems)

    def render(self, content: dict[str, object]) -> tuple[Rendition, ...]:
        """Render the canonical JSON rendition (separately referenceable)."""
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return (Rendition(format="json", content=canonical.encode("utf-8")),)


@dataclass(frozen=True, slots=True)
class RecipeRegistry:
    """The typed startup-registered recipe surface (artifact type -> recipe)."""

    _recipes: dict[ArtifactType, ArtifactRecipe]

    def get(self, artifact_type: ArtifactType) -> ArtifactRecipe | None:
        """Return the registered recipe for a type, or None (type not yet built)."""
        return self._recipes.get(artifact_type)

    def registered_types(self) -> frozenset[ArtifactType]:
        """Return the artifact types with a registered recipe."""
        return frozenset(self._recipes)


def build_recipe_registry() -> RecipeRegistry:
    """
    Register the internal recipes at startup (typed, no runtime loading).

    Only the composite demo recipe ships with the framework (task 31); the real
    families land in tasks 32-34 and register here without touching the
    pipeline.
    """
    return RecipeRegistry({CompositeEchoRecipe().artifact_type: CompositeEchoRecipe()})


def _payload_fingerprint(sections: object, title: object) -> str:
    """Stable digest of the payload body (canonical JSON, key-sorted)."""
    payload = {"title": title, "sections": sections}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
