import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import {
  isApiError,
  listSources,
  pasteSource,
  removeSource,
  renameSource,
  selectSource,
  uploadSource,
} from "../api/client";
import { queryKeys } from "../api/query-keys";
import type { Source } from "../api/schemas";
import { terminalJobStates } from "../api/schemas";
import { useJobs } from "../state/jobs";
import { mergeSources } from "../state/source-list";

type Props = { readonly actorId: string; readonly notebookId: string };

export function SourcePanel({ actorId, notebookId }: Props): ReactNode {
  const queryClient = useQueryClient();
  const { jobs, watch } = useJobs();
  const key = queryKeys.sources(actorId, notebookId);
  const persistedSources = useQuery({
    queryKey: key,
    queryFn: async () => {
      const persisted = await listSources(notebookId);
      const session = queryClient.getQueryData<readonly Source[]>(key) ?? [];
      return mergeSources(persisted, session);
    },
  });
  // When a watched job reaches a terminal state, drop the stale creation-response
  // rows for that job (mergeSources prefers session entries) and refetch so the
  // row shows the server's terminal pipeline_status/availability.
  const processedTerminalJobs = useRef<Set<string>>(new Set());
  useEffect(() => {
    const newlyFinished = jobs.filter(
      (job) => terminalJobStates.has(job.state) && !processedTerminalJobs.current.has(job.job_id),
    );
    if (newlyFinished.length === 0) return;
    for (const job of newlyFinished) processedTerminalJobs.current.add(job.job_id);
    const finishedIds = new Set(newlyFinished.map((job) => job.job_id));
    queryClient.setQueryData<readonly Source[]>(key, (current = []) =>
      current.filter((source) => source.job_id === undefined || !finishedIds.has(source.job_id)),
    );
    void queryClient.invalidateQueries({ queryKey: key });
  }, [jobs, queryClient, key]);
  const sources = persistedSources.data ?? [];
  const [error, setError] = useState("");
  const addSource = (source: Source): void => {
    queryClient.setQueryData<readonly Source[]>(key, (current = []) => [
      source,
      ...current.filter((item) => item.source_id !== source.source_id),
    ]);
    if (source.job_id !== undefined) watch(source.job_id);
  };
  const paste = useMutation({
    mutationFn: pasteSource,
    onSuccess: addSource,
    onError: () => setError("Paste import failed."),
  });
  const upload = useMutation({
    mutationFn: ({ file }: { readonly file: File }) => uploadSource(notebookId, file),
    onSuccess: addSource,
    onError: () => setError("Upload failed."),
  });
  const lifecycle = useMutation({
    mutationFn: ({
      source,
      action,
    }: {
      readonly source: Source;
      readonly action: "select" | "remove";
    }) => (action === "select" ? selectSource(source.source_id) : removeSource(source.source_id)),
    onSuccess: addSource,
  });
  const rename = useMutation({
    mutationFn: ({ source, title }: { readonly source: Source; readonly title: string }) =>
      renameSource(source, title),
    onMutate: ({ source, title }) => {
      const previous = queryClient.getQueryData<readonly Source[]>(key) ?? [];
      queryClient.setQueryData<readonly Source[]>(
        key,
        previous.map((item) =>
          item.source_id === source.source_id ? { ...item, display_title: title } : item,
        ),
      );
      return { previous };
    },
    onError: (caught, _variables, context) => {
      if (context !== undefined) queryClient.setQueryData(key, context.previous);
      setError(
        isApiError(caught) && caught.response.status === 412
          ? "Rename conflicted with a newer version. The previous title was restored."
          : "Rename failed. The previous title was restored.",
      );
    },
    onSuccess: addSource,
  });
  const submitPaste = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    paste.mutate({
      notebook_id: notebookId,
      title: String(data.get("title") ?? ""),
      text: String(data.get("text") ?? ""),
    });
    event.currentTarget.reset();
  };
  return (
    <div className="split-content">
      <section className="panel-stack" aria-labelledby="add-source-title">
        <h2 id="add-source-title">Add source</h2>
        <form className="form-stack" onSubmit={submitPaste}>
          <label>
            Title
            <input name="title" required maxLength={300} />
          </label>
          <label>
            Text
            <textarea name="text" required rows={8} />
          </label>
          <button className="primary" disabled={paste.isPending} type="submit">
            {paste.isPending ? "Adding..." : "Paste text"}
          </button>
        </form>
        <label className="file-field">
          Upload source
          <input
            type="file"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file !== undefined) upload.mutate({ file });
            }}
          />
        </label>
        {error === "" ? null : (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
      </section>
      <section className="panel-stack" aria-labelledby="source-list-title">
        <div>
          <h2 id="source-list-title">Sources</h2>
          <p className="muted">
            Persisted source versions remain available after reload and login.
          </p>
        </div>
        {persistedSources.isPending ? (
          <p className="muted" role="status">
            Loading persisted sources...
          </p>
        ) : null}
        {persistedSources.isError ? (
          <p className="notice error" role="alert">
            Persisted sources could not be loaded. Try again without leaving this notebook.
          </p>
        ) : null}
        {!persistedSources.isPending && !persistedSources.isError && sources.length === 0 ? (
          <div className="empty-state">
            <h3>No sources yet</h3>
            <p>Paste text or upload a file to begin.</p>
          </div>
        ) : null}
        <div className="resource-list">
          {sources.map((source) => (
            <SourceRow
              key={source.source_id}
              source={source}
              onRename={(title) => rename.mutate({ source, title })}
              onLifecycle={(action) => lifecycle.mutate({ source, action })}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function SourceRow({
  source,
  onRename,
  onLifecycle,
}: {
  readonly source: Source;
  readonly onRename: (title: string) => void;
  readonly onLifecycle: (action: "select" | "remove") => void;
}): ReactNode {
  const [editing, setEditing] = useState(false);
  return (
    <article className="resource-row">
      <div className="row-main">
        <h3>{source.display_title}</h3>
        <p className="resource-meta">
          {source.pipeline_status} | {source.availability}
        </p>
      </div>
      <div className="action-cluster">
        {editing ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const title = String(new FormData(event.currentTarget).get("title") ?? "");
              onRename(title);
              setEditing(false);
            }}
          >
            <label className="sr-only" htmlFor={`rename-${source.source_id}`}>
              New title
            </label>
            <input
              id={`rename-${source.source_id}`}
              name="title"
              defaultValue={source.display_title}
              required
            />
            <button type="submit">Save</button>
          </form>
        ) : (
          <button type="button" onClick={() => setEditing(true)}>
            Rename
          </button>
        )}
        <button
          type="button"
          onClick={() => onLifecycle(source.availability === "active" ? "remove" : "select")}
        >
          {source.availability === "active" ? "Remove" : "Select"}
        </button>
      </div>
    </article>
  );
}
