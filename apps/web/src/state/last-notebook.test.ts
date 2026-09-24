import { afterEach, describe, expect, it } from "vitest";
import { getLastNotebook, rememberLastNotebook, resolveNotebooksPath } from "./last-notebook";

afterEach(() => {
  sessionStorage.clear();
});

describe("last-notebook store", () => {
  it("round-trips the last opened notebook per actor", () => {
    expect(getLastNotebook("actor-1")).toBeNull();
    rememberLastNotebook("actor-1", "notebook-1");
    expect(getLastNotebook("actor-1")).toBe("notebook-1");
    expect(getLastNotebook("actor-2")).toBeNull();
  });

  it("reopens the last notebook when arriving from outside the notebooks area", () => {
    rememberLastNotebook("actor-1", "notebook-1");
    expect(resolveNotebooksPath("/notebooks", "/settings", "actor-1")).toBe(
      "/notebooks/notebook-1",
    );
  });

  it("keeps the list when navigating from inside the notebooks area", () => {
    rememberLastNotebook("actor-1", "notebook-1");
    expect(resolveNotebooksPath("/notebooks", "/notebooks/notebook-1", "actor-1")).toBe(
      "/notebooks",
    );
  });

  it("keeps the list when no notebook was opened this session", () => {
    expect(resolveNotebooksPath("/notebooks", "/settings", "actor-1")).toBe("/notebooks");
  });

  it("keeps the list for anonymous sessions and non-notebook targets", () => {
    rememberLastNotebook("actor-1", "notebook-1");
    expect(resolveNotebooksPath("/notebooks", "/settings", null)).toBe("/notebooks");
    expect(resolveNotebooksPath("/settings", "/notebooks/notebook-1", "actor-1")).toBe("/settings");
  });
});
