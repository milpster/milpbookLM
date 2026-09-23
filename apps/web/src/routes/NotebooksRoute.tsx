import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent, ReactNode } from "react";
import { useState } from "react";
import type { RouteProps } from "../App";
import { createNotebook, getCapabilities, listNotebooks } from "../api/client";
import { queryKeys } from "../api/query-keys";
import type { Notebook } from "../api/schemas";
import { useAuth } from "../state/auth";

export function NotebooksRoute({ navigate }: RouteProps): ReactNode {
  const { actor } = useAuth();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [createError, setCreateError] = useState("");
  const notebooks = useQuery({
    queryKey: queryKeys.notebooks(actor?.user_id ?? "anonymous"),
    queryFn: listNotebooks,
    enabled: actor !== null,
  });
  const capabilities = useQuery({ queryKey: queryKeys.capabilities(), queryFn: getCapabilities });
  const create = useMutation({
    mutationFn: (value: string) => createNotebook({ title: value }),
    onSuccess: (notebook) => {
      if (actor !== null) {
        queryClient.setQueryData<readonly Notebook[]>(
          queryKeys.notebooks(actor.user_id),
          (current = []) => [notebook, ...current],
        );
      }
      setTitle("");
      navigate(`/notebooks/${notebook.notebook_id}`);
    },
    onError: () => setCreateError("Notebook creation failed. Please try again."),
  });
  if (actor === null) return null;
  const management = capabilities.data?.capabilities.find(
    (item) => item.id === "notebook_management",
  );
  const createReady = management?.state === "available";
  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setCreateError("");
    create.mutate(title);
  };
  return (
    <section className="page-stack" aria-labelledby="notebooks-title">
      <header className="page-heading">
        <div>
          <p className="kicker">Workspace</p>
          <h1 id="notebooks-title">Notebooks</h1>
        </div>
        {createReady ? (
          <form className="create-form" onSubmit={submit} aria-describedby="create-status">
            <label htmlFor="notebook-title" className="sr-only">
              Notebook title
            </label>
            <input
              id="notebook-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
              maxLength={300}
              placeholder="Notebook title"
            />
            <button className="primary" type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create notebook"}
            </button>
          </form>
        ) : (
          <button className="primary" type="button" disabled aria-describedby="create-status">
            Create notebook
          </button>
        )}
      </header>
      <p id="create-status" className="muted">
        {createReady
          ? "New notebooks are private and owned by you."
          : `Creating notebooks is not available on this installation${management?.reason ? `: ${management.reason}` : "."}`}
      </p>
      {createError !== "" ? (
        <p className="notice error" role="alert">
          {createError}
        </p>
      ) : null}
      {notebooks.isPending ? <p role="status">Loading notebooks...</p> : null}
      {notebooks.isError ? (
        <p className="notice error" role="alert">
          Notebooks could not be loaded. Please try again.
        </p>
      ) : null}
      {notebooks.data?.length === 0 ? (
        <div className="empty-state">
          <h2>No notebooks yet</h2>
          <p>Create your first notebook above to get started.</p>
        </div>
      ) : null}
      <div className="resource-grid">
        {notebooks.data?.map((notebook) => (
          <article className="resource-card" key={notebook.notebook_id}>
            <p className="resource-meta">{notebook.membership ?? "member"}</p>
            <h2>{notebook.title}</h2>
            <p>Custody: {notebook.custody_state}</p>
            <button
              className="secondary"
              type="button"
              onClick={() => navigate(`/notebooks/${notebook.notebook_id}`)}
            >
              Open notebook
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
