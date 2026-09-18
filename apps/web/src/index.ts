import { createNotebook } from "@milpbooklm/web-application";
import type { Notebook } from "@milpbooklm/web-domain";

/**
 * Composition root for the web app (skeleton).
 *
 * Wires use cases to presentation. The React 19 surface (Vite, TanStack
 * Query/Router) is added by the web capability tasks; this file keeps the
 * project-reference chain `web -> application -> domain` live and tested.
 */
export interface NotebookService {
  readonly createNotebook: (id: string, title: string) => Notebook;
}

export function buildNotebookService(): NotebookService {
  return { createNotebook };
}
