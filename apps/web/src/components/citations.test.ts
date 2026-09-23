import { describe, expect, it } from "vitest";
import type { Citation } from "../api/schemas";
import { citationKey, dedupeCitations } from "./citations";

const sourceVersionId = "a4f6c1e2-1111-4222-8333-444455556666";
const nodeId = "b5e7d2f3-2222-4333-9444-555566667777";

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    evidence_id: "evidence-1",
    label: "Section 2.1, p. 12",
    source_version_id: sourceVersionId,
    node_id: nodeId,
    locator_kind: "section",
    char_start: 0,
    char_end: 42,
    url: "/viewer/placeholder",
    ...overrides,
  };
}

describe("citationKey", () => {
  it("builds a stable composite key from source version and node", () => {
    expect(citationKey(citation())).toBe(`${sourceVersionId}:${nodeId}`);
  });
});

describe("dedupeCitations", () => {
  it("keeps the first occurrence of duplicate source version + node pairs", () => {
    const a = citation();
    const duplicate = citation({ evidence_id: "evidence-2", label: "Section 2.1 (dup)" });
    const b = citation({ node_id: "c6f8e3a4-3333-4444-8555-666677778888" });
    expect(dedupeCitations([a, duplicate, b, a])).toEqual([a, b]);
  });

  it("returns an empty list unchanged", () => {
    expect(dedupeCitations([])).toEqual([]);
  });

  it("yields a unique key per chip in a deduplicated list", () => {
    const a = citation();
    const duplicate = citation({ evidence_id: "evidence-2" });
    const b = citation({ source_version_id: "d7a9f4b5-4444-4555-9666-777788889999" });
    const keys = dedupeCitations([a, duplicate, b]).map(citationKey);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
