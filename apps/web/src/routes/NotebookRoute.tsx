import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useState } from "react";
import type { RouteProps } from "../App";
import { getNotebook } from "../api/client";
import { queryKeys } from "../api/query-keys";
import { ChatPanel } from "../components/ChatPanel";
import { SourcePanel } from "../components/SourcePanel";
import { useAuth } from "../state/auth";

export function NotebookRoute({ navigate, params }: RouteProps): ReactNode {
  const notebookId = params["notebookId"];
  const { actor } = useAuth();
  const [tab, setTab] = useState<"sources" | "chat">("sources");
  const notebook = useQuery({
    queryKey: queryKeys.notebook(actor?.user_id ?? "anonymous", notebookId ?? ""),
    queryFn: () => getNotebook(notebookId ?? ""),
    enabled: actor !== null && notebookId !== undefined,
  });
  if (actor === null || notebookId === undefined)
    return <p className="notice error">Notebook route is invalid.</p>;
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
        </fieldset>
      </header>
      {notebook.isError ? (
        <p className="notice error" role="alert">
          Notebook unavailable.
        </p>
      ) : null}
      {tab === "sources" ? (
        <SourcePanel actorId={actor.user_id} notebookId={notebookId} />
      ) : (
        <ChatPanel actorId={actor.user_id} notebookId={notebookId} navigate={navigate} />
      )}
    </section>
  );
}
