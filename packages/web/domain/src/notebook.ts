/**
 * Frontend domain: pure types and state machines.
 *
 * This package imports nothing beyond itself. It mirrors the Python
 * `milpbooklm_domain` entity so the web app never drifts from the backend
 * model (ARCH-01-001 scope: the domain is the shared boundary).
 */

/** Lifecycle states of a notebook. */
export const NotebookStatus = {
  Active: "active",
  Archived: "archived",
} as const;

export type NotebookStatus = (typeof NotebookStatus)[keyof typeof NotebookStatus];

/** A research notebook (immutable value object). */
export interface Notebook {
  readonly id: string;
  readonly title: string;
  readonly status: NotebookStatus;
}

/** Pure state transition: returns a new archived notebook (idempotent). */
export function archive(notebook: Notebook): Notebook {
  if (notebook.status === NotebookStatus.Archived) {
    return notebook;
  }
  return { ...notebook, status: NotebookStatus.Archived };
}
