export type NotebookTab = "sources" | "chat" | "notes";

const activeConversations = new Map<string, string>();

/** Remember the active conversation for a notebook. */
export function rememberActiveConversation(notebookId: string, conversationId: string): void {
  activeConversations.set(notebookId, conversationId);
}

/** Return the remembered active conversation id for a notebook, if any. */
export function getActiveConversation(notebookId: string): string | null {
  return activeConversations.get(notebookId) ?? null;
}
