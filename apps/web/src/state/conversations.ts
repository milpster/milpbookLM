export type NotebookTab = "sources" | "chat";

// Module-level (route-external) notebook UI state. It survives SPA route
// unmounts within a tab, so a citation-chip -> viewer -> browser-back
// round-trip restores the active conversation id (and the open tab) when
// ChatPanel remounts and refetches the conversation via getConversation().
const activeConversations = new Map<string, string>();
const notebookTabs = new Map<string, NotebookTab>();

/** Remember the active conversation for a notebook. */
export function rememberActiveConversation(notebookId: string, conversationId: string): void {
  activeConversations.set(notebookId, conversationId);
}

/** Return the remembered active conversation id for a notebook, if any. */
export function getActiveConversation(notebookId: string): string | null {
  return activeConversations.get(notebookId) ?? null;
}

/** Remember the last opened notebook view tab. */
export function rememberNotebookTab(notebookId: string, tab: NotebookTab): void {
  notebookTabs.set(notebookId, tab);
}

/** Return the last opened notebook view tab, defaulting to "sources". */
export function getNotebookTab(notebookId: string): NotebookTab {
  return notebookTabs.get(notebookId) ?? "sources";
}
