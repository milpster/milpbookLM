const lastNotebookKey = (actorId: string): string => `milpbookLM:last-notebook:${actorId}`;

/** Remember the last notebook the actor successfully opened (per browser session). */
export function rememberLastNotebook(actorId: string, notebookId: string): void {
  sessionStorage.setItem(lastNotebookKey(actorId), notebookId);
}

/** Return the actor's last opened notebook id, if this session recorded one. */
export function getLastNotebook(actorId: string): string | null {
  return sessionStorage.getItem(lastNotebookKey(actorId));
}

/**
 * Where a "/notebooks" navigation should land: arriving from outside the
 * notebooks area reopens the last opened notebook; navigating from inside
 * (e.g. an explicit back-to-list) keeps the list, so the list stays reachable.
 */
export function resolveNotebooksPath(
  next: string,
  current: string,
  actorId: string | null,
): string {
  if (next !== "/notebooks" || current.startsWith("/notebooks") || actorId === null) return next;
  const last = getLastNotebook(actorId);
  return last === null ? next : `/notebooks/${last}`;
}
