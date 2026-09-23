import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useState } from "react";
import type { RouteProps } from "../App";
import { getNotebook } from "../api/client";
import { queryKeys } from "../api/query-keys";
import { ChatPanel } from "../components/ChatPanel";
import { NotesPanel } from "../components/NotesPanel";
import { SourcePanel } from "../components/SourcePanel";
import { useAuth } from "../state/auth";
import type { NotebookTab } from "../state/conversations";
import { getNotebookTab, rememberNotebookTab } from "../state/conversations";

export function NotebookRoute({ navigate, params }: RouteProps): ReactNode {
  const notebookId = params["notebookId"] ?? "";
  const { actor } = useAuth();
  const [tab, setTabState] = useState<NotebookTab>(() => getNotebookTab(notebookId));
  const setTab = (next: NotebookTab): void => {
    rememberNotebookTab(notebookId, next);
    setTabState(next);
  };
  const notebook = useQuery({
    queryKey: queryKeys.notebook(actor?.user_id ?? "anonymous", notebookId ?? ""),
    queryFn: () => getNotebook(notebookId ?? ""),
    enabled: actor !== null && notebookId !== undefined,
  });
  if (actor === null || notebookId === undefined)
    return <p className="notice error">This notebook link is not valid.</p>;
  return (
    <section className="notebook-view" aria-labelledby="notebook-title">
      <header className="page-heading">
        <div>
          <p className="kicker">Notebook</p>
          <h1 id="notebook-title">{notebook.data?.title ?? "Loading..."}</h1>
        </div>
        <fieldset className="segmented" aria-label="Notebook view">
          <button type="button" aria-pressed={tab === "sources"} onClick={() => setTab("sources")}>
            Sources
          </button>
          <button type="button" aria-pressed={tab === "chat"} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button type="button" aria-pressed={tab === "notes"} onClick={() => setTab("notes")}>
            Notes
          </button>
        </fieldset>
      </header>
      {notebook.isError ? (
        <p className="notice error" role="alert">
          Notebook could not be loaded. Please try again.
        </p>
      ) : null}
      {tab === "sources" ? (
        <SourcePanel actorId={actor.user_id} notebookId={notebookId} />
      ) : tab === "chat" ? (
        <ChatPanel actorId={actor.user_id} notebookId={notebookId} navigate={navigate} />
      ) : (
        <NotesPanel actorId={actor.user_id} notebookId={notebookId} />
      )}
    </section>
  );
}
