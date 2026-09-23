export const queryKeys = {
  capabilities: () => ["public", "capabilities"] as const,
  actor: (actorId: string) => ["actor", actorId, "profile"] as const,
  notebooks: (actorId: string) => ["actor", actorId, "notebooks"] as const,
  notebook: (actorId: string, notebookId: string) =>
    ["actor", actorId, "notebook", notebookId] as const,
  sources: (actorId: string, notebookId: string) =>
    ["actor", actorId, "notebook", notebookId, "sources"] as const,
  notes: (actorId: string, notebookId: string) =>
    ["actor", actorId, "notebook", notebookId, "notes"] as const,
  note: (actorId: string, notebookId: string, noteId: string) =>
    ["actor", actorId, "notebook", notebookId, "note", noteId] as const,
  noteRevisions: (actorId: string, notebookId: string, noteId: string) =>
    ["actor", actorId, "notebook", notebookId, "note", noteId, "revisions"] as const,
  source: (actorId: string, notebookId: string, sourceId: string, versionId: string) =>
    ["actor", actorId, "notebook", notebookId, "source", sourceId, versionId] as const,
  privateConversation: (actorId: string, conversationId: string) =>
    ["actor", actorId, "private", "conversation", conversationId] as const,
  job: (actorId: string, jobId: string) => ["actor", actorId, "private", "job", jobId] as const,
} as const;
