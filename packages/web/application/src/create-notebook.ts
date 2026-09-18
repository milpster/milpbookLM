import { type Notebook, NotebookStatus } from "@milpbooklm/web-domain";

/**
 * Use case: materialize a new active notebook.
 *
 * Pure (no I/O): the caller supplies the id so the function stays
 * deterministic and testable. Depends on the domain only (import rule
 * mirrored by the TS project reference to `../domain`).
 */
export function createNotebook(id: string, title: string): Notebook {
  const trimmed = title.trim();
  if (trimmed.length === 0) {
    throw new Error("notebook title must be non-empty");
  }
  return { id, title: trimmed, status: NotebookStatus.Active };
}
