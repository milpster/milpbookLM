import { describe, expect, it } from "vitest";
import type { Source } from "../api/schemas";
import { mergeSources } from "./source-list";

const source = (sourceId: string, versionId: string, title: string): Source => ({
  source_id: sourceId,
  source_version_id: versionId,
  notebook_id: "1b671a6e-400d-4e5f-8f8e-9d0f1a2b3c4d",
  source_type: "plain_text",
  display_title: title,
  availability: "active",
  content_sha256: "a".repeat(64),
  content_size_bytes: 42,
  status: "quarantined_identified",
  pipeline_status: "active",
  etag: "0",
  canonical_root_node_id: null,
});

describe("mergeSources", () => {
  it("deduplicates server and optimistic rows by source-version identity", () => {
    const sourceId = "2c5a3a1d-93b8-4a11-9db4-2817e88a5c40";
    const versionId = "735ed65a-c69e-48b3-940f-aceb99cd0bf3";

    const result = mergeSources(
      [source(sourceId, versionId, "Persisted")],
      [source(sourceId, versionId, "Optimistic")],
    );

    expect(result).toHaveLength(1);
    expect(result[0]?.display_title).toBe("Optimistic");
  });

  it("retains distinct persisted versions", () => {
    const sourceId = "2c5a3a1d-93b8-4a11-9db4-2817e88a5c40";

    const result = mergeSources(
      [source(sourceId, "735ed65a-c69e-48b3-940f-aceb99cd0bf3", "Version one")],
      [source(sourceId, "846fe76b-d7af-4e08-a773-bdf9ad074c04", "Version two")],
    );

    expect(result).toHaveLength(2);
  });
});
