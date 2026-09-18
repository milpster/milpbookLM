import { describe, expect, it } from "vitest";
import { archive, type Notebook, NotebookStatus } from "./notebook.js";

const active: Notebook = { id: "1", title: "Atlas", status: NotebookStatus.Active };

describe("notebook state machine", () => {
  it("archives an active notebook", () => {
    expect(archive(active).status).toBe(NotebookStatus.Archived);
  });

  it("is idempotent on an already-archived notebook", () => {
    const once = archive(active);
    expect(archive(once)).toBe(once);
  });

  it("preserves identity fields on transition", () => {
    expect(archive(active)).toMatchObject({ id: "1", title: "Atlas" });
  });
});
