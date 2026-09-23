import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent, ReactNode } from "react";
import { useState } from "react";
import {
  createNote,
  editNote,
  getNote,
  isApiError,
  listNoteRevisions,
  listNotes,
} from "../api/client";
import { queryKeys } from "../api/query-keys";

type Props = { readonly actorId: string; readonly notebookId: string };

function paragraphContent(text: string): Record<string, unknown> {
  return { blocks: [{ type: "paragraph", text }] };
}

function toParagraphText(content: Record<string, unknown>): string | null {
  const blocks = content["blocks"];
  if (!Array.isArray(blocks)) return null;
  for (const block of blocks) {
    if (
      typeof block === "object" &&
      block !== null &&
      (block as { readonly type?: unknown }).type === "paragraph" &&
      typeof (block as { readonly text?: unknown }).text === "string"
    )
      return (block as { readonly text: string }).text;
  }
  return null;
}

function replaceParagraphText(content: Record<string, unknown>, text: string): Record<string, unknown> {
  const blocks = content["blocks"];
  if (!Array.isArray(blocks)) return paragraphContent(text);
  let replaced = false;
  return {
    ...content,
    blocks: blocks.map((block) => {
      if (
        !replaced &&
        typeof block === "object" &&
        block !== null &&
        (block as { readonly type?: unknown }).type === "paragraph" &&
        typeof (block as { readonly text?: unknown }).text === "string"
      ) {
        replaced = true;
        return { ...(block as Record<string, unknown>), text };
      }
      return block;
    }),
  };
}

function stringItems(block: Record<string, unknown>): readonly string[] | null {
  const items = block["items"];
  return Array.isArray(items) && items.every((item) => typeof item === "string")
    ? (items as readonly string[])
    : null;
}

// Only known, text-safe block types render as text; anything else renders as
// deterministic JSON so untrusted content can never be injected as markup.
function BlockView({ block }: { readonly block: unknown }): ReactNode {
  if (typeof block !== "object" || block === null)
    return <pre className="note-json">{JSON.stringify(block, null, 2)}</pre>;
  const record = block as Record<string, unknown>;
  const text = record["text"];
  if (record["type"] === "paragraph" && typeof text === "string") return <p>{text}</p>;
  if (
    record["type"] === "heading" &&
    typeof text === "string" &&
    typeof record["level"] === "number" &&
    Number.isInteger(record["level"]) &&
    record["level"] >= 1 &&
    record["level"] <= 3
  ) {
    const Heading = `h${record["level"]}` as "h1" | "h2" | "h3";
    return <Heading>{text}</Heading>;
  }
  const items = stringItems(record);
  if (record["type"] === "ordered_list" && items !== null)
    return <ol className="note-list">{items.map((item) => <li key={item}>{item}</li>)}</ol>;
  if (record["type"] === "unordered_list" && items !== null)
    return <ul className="note-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
  return <pre className="note-json">{JSON.stringify(block, null, 2)}</pre>;
}

function ContentView({ content }: { readonly content: Record<string, unknown> }): ReactNode {
  const blocks = content["blocks"];
  if (!Array.isArray(blocks))
    return <pre className="note-json">{JSON.stringify(content, null, 2)}</pre>;
  return (
    <div className="note-content">
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </div>
  );
}

export function NotesPanel({ actorId, notebookId }: Props): ReactNode {
  const queryClient = useQueryClient();
  const notesKey = queryKeys.notes(actorId, notebookId);
  const notesQuery = useQuery({ queryKey: notesKey, queryFn: () => listNotes(notebookId) });
  const noteList = notesQuery.data?.notes ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createError, setCreateError] = useState("");
  const firstId = noteList[0]?.note_id ?? null;
  const effectiveId =
    selectedId !== null && noteList.some((note) => note.note_id === selectedId)
      ? selectedId
      : firstId;
  const create = useMutation({
    mutationFn: (input: { readonly title: string; readonly text: string }) =>
      createNote(notebookId, input.title, paragraphContent(input.text)),
    onMutate: () => setCreateError(""),
    onSuccess: (snapshot) => {
      setSelectedId(snapshot.note.note_id);
      void queryClient.invalidateQueries({ queryKey: notesKey });
    },
    onError: () => setCreateError("Creating the note failed. Please try again."),
  });
  const submitCreate = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    create.mutate({
      title: String(data.get("title") ?? ""),
      text: String(data.get("text") ?? ""),
    });
    event.currentTarget.reset();
  };
  return (
    <div className="split-content">
      <section className="panel-stack" aria-labelledby="notes-list-title">
        <div>
          <h2 id="notes-list-title">Notes</h2>
          <p className="muted">
            Every edit is saved as a new revision, so earlier versions stay intact.
          </p>
        </div>
        <form className="form-stack compact" onSubmit={submitCreate}>
          <label>
            Title
            <input name="title" required maxLength={300} />
          </label>
          <label>
            Text
            <textarea name="text" required rows={4} />
          </label>
          <button className="primary" disabled={create.isPending} type="submit">
            {create.isPending ? "Creating..." : "Create note"}
          </button>
        </form>
        {createError === "" ? null : (
          <p className="notice error" role="alert">
            {createError}
          </p>
        )}
        {notesQuery.isPending ? (
          <p className="muted" role="status">
            Loading notes...
          </p>
        ) : null}
        {notesQuery.isError ? (
          <p className="notice error" role="alert">
            Notes could not be loaded. Please try again.
          </p>
        ) : null}
        {!notesQuery.isPending && !notesQuery.isError && noteList.length === 0 ? (
          <div className="empty-state">
            <h3>No notes yet</h3>
            <p>Create a note to capture your thinking.</p>
          </div>
        ) : null}
        <div className="resource-list">
          {noteList.map((note) => (
            <button
              key={note.note_id}
              type="button"
              className="note-list-item"
              aria-pressed={note.note_id === effectiveId}
              onClick={() => setSelectedId(note.note_id)}
            >
              <span>{note.title}</span>
              <span className="resource-meta">
                {note.kind} | revision {note.revision} | {note.etag}
              </span>
            </button>
          ))}
        </div>
      </section>
      <section className="panel-stack" aria-labelledby="note-detail-title">
        <h2 id="note-detail-title">Note</h2>
        {effectiveId === null ? (
          <div className="empty-state">
            <h3>No note selected</h3>
            <p>Select a note on the left to read and edit it.</p>
          </div>
        ) : (
          <NoteDetail actorId={actorId} notebookId={notebookId} noteId={effectiveId} />
        )}
      </section>
    </div>
  );
}

function NoteDetail({
  actorId,
  notebookId,
  noteId,
}: {
  readonly actorId: string;
  readonly notebookId: string;
  readonly noteId: string;
}): ReactNode {
  const queryClient = useQueryClient();
  const noteKey = queryKeys.note(actorId, notebookId, noteId);
  const revisionsKey = queryKeys.noteRevisions(actorId, notebookId, noteId);
  const noteQuery = useQuery({ queryKey: noteKey, queryFn: () => getNote(noteId) });
  const revisionsQuery = useQuery({
    queryKey: revisionsKey,
    queryFn: () => listNoteRevisions(noteId),
  });
  const note = noteQuery.data;
  const revisions = revisionsQuery.data?.revisions ?? [];
  const currentRevision =
    revisions.find((revision) => revision.revision_id === note?.current_revision_id) ?? null;
  const [viewingId, setViewingId] = useState<string | null>(null);
  const displayedRevision =
    viewingId !== null
      ? (revisions.find((revision) => revision.revision_id === viewingId) ?? currentRevision)
      : currentRevision;
  const viewingHistory =
    viewingId !== null && displayedRevision !== null && viewingId !== currentRevision?.revision_id;
  const currentText =
    currentRevision === null ? "" : (toParagraphText(currentRevision.content) ?? "");
  // The draft resets whenever the server's current revision text changes (initial
  // load, refetch after save, conflict reload) — the baseline detects that shift.
  const [draft, setDraft] = useState(() => ({ baseline: currentText, text: currentText }));
  if (draft.baseline !== currentText) {
    setDraft({ baseline: currentText, text: currentText });
  }
  const hasDraftChanges = draft.text.trim() !== currentText.trim();
  const refetchAll = (): void => {
    void queryClient.invalidateQueries({ queryKey: noteKey });
    void queryClient.invalidateQueries({ queryKey: revisionsKey });
    void queryClient.invalidateQueries({ queryKey: queryKeys.notes(actorId, notebookId) });
  };
  const edit = useMutation({
    mutationFn: (text: string) =>
      editNote(
        noteId,
        note?.etag ?? "",
        currentRevision === null
          ? paragraphContent(text)
          : replaceParagraphText(currentRevision.content, text),
      ),
    onSuccess: () => {
      setViewingId(null);
      refetchAll();
    },
    onError: () => {
      refetchAll();
    },
  });
  const conflictMessage =
    edit.isError && isApiError(edit.error) && edit.error.response.status === 409
      ? "This note was changed since you started editing. The latest revision was reloaded — try your edit again."
      : edit.isError
        ? "Saving the new revision failed. Please try again."
        : "";
  const submitEdit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    edit.mutate(draft.text);
  };
  if (noteQuery.isPending && note === undefined)
    return (
      <p className="muted" role="status">
        Loading note...
      </p>
    );
  return (
    <div className="form-stack compact">
      {note === undefined ? (
        <p className="notice error" role="alert">
          Note could not be loaded. Please try again.
        </p>
      ) : (
        <>
          <div className="row-main">
            <h3>{note.title}</h3>
            <p className="resource-meta">
              {note.kind} | {note.editable ? "editable" : "read-only"} | etag {note.etag}
            </p>
          </div>
          {conflictMessage === "" ? null : (
            <p className="notice error" role="alert">
              {conflictMessage}
            </p>
          )}
          <div className="note-detail">
            {viewingHistory && displayedRevision !== null ? (
              <div className="revision-banner" role="status">
                <p className="muted">
                  Viewing revision {displayedRevision.revision_number} (read-only)
                </p>
                <button type="button" onClick={() => setViewingId(null)}>
                  Return to current revision
                </button>
              </div>
            ) : (
              <p className="muted">Current revision</p>
            )}
            {displayedRevision === null ? (
              <p className="muted">This note has no content yet.</p>
            ) : (
              <ContentView content={displayedRevision.content} />
            )}
          </div>
          {note.editable && !viewingHistory ? (
            <form className="form-stack compact" onSubmit={submitEdit}>
              <label>
                Text
                <textarea
                  name="text"
                  value={draft.text}
                  onChange={(event) =>
                    setDraft({ baseline: draft.baseline, text: event.target.value })
                  }
                  rows={6}
                  required
                />
              </label>
              <button
                className="primary"
                disabled={edit.isPending || !hasDraftChanges}
                type="submit"
              >
                {edit.isPending ? "Saving..." : "Save new revision"}
              </button>
              {hasDraftChanges ? null : <p className="muted">No changes yet.</p>}
            </form>
          ) : null}
          <div className="form-stack compact">
            <p className="muted">Revisions</p>
            <ol className="plain-list">
              {revisions.map((revision) => (
                <li key={revision.revision_id}>
                  <span>
                    Revision {revision.revision_number} | {revision.created_at}
                  </span>
                  {revision.revision_id === note.current_revision_id ? (
                    <span className="muted">(current)</span>
                  ) : (
                    <button
                      type="button"
                      aria-pressed={revision.revision_id === viewingId}
                      onClick={() =>
                        setViewingId(
                          revision.revision_id === viewingId ? null : revision.revision_id,
                        )
                      }
                    >
                      {revision.revision_id === viewingId ? "Hide" : "View"}
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </div>
  );
}
