import type { FormEvent, ReactNode } from "react";
import { useState } from "react";
import type { Source } from "../api/schemas";

type StatusVisualClass = "ready" | "in-progress" | "failed";

const STATUS_CLASS: Readonly<
  Record<Source["pipeline_status"] | Source["availability"], StatusVisualClass>
> = {
  parsed: "ready",
  active: "ready",
  activating: "in-progress",
  parsing: "in-progress",
  parse_failed: "failed",
  encrypted: "failed",
  inactive: "failed",
  tombstoned: "failed",
  stale: "failed",
  inaccessible_revoked: "failed",
  deleted_tombstoned: "failed",
};

const PIPELINE_REASON: Readonly<Record<Source["pipeline_status"], string | null>> = {
  activating: "Source content is still being prepared.",
  parsing: "Source content is still being prepared.",
  parsed: "Source content is waiting to be activated.",
  active: null,
  parse_failed: "Source processing failed, so its contents are unavailable.",
  encrypted: "This source is encrypted, so its contents are unavailable.",
  inactive: "This source is inactive, so its contents are unavailable.",
  tombstoned: "This source version was removed and is no longer available.",
};

const AVAILABILITY_REASON: Readonly<Record<Source["availability"], string | null>> = {
  active: null,
  stale: null,
  inaccessible_revoked: "Access to this source was revoked.",
  deleted_tombstoned: "This source was removed from the notebook.",
};

const OPENABLE_AVAILABILITY: ReadonlySet<Source["availability"]> = new Set([
  "active",
  "stale",
]);

type Props = {
  readonly source: Source;
  readonly onOpen: (path: string) => void;
  readonly onRename: (title: string) => void;
  readonly onLifecycle: (action: "select" | "remove") => void;
};

export function SourceRow({ source, onOpen, onRename, onLifecycle }: Props): ReactNode {
  const [editing, setEditing] = useState(false);
  const viewerPath =
    OPENABLE_AVAILABILITY.has(source.availability) && source.canonical_root_node_id !== null
      ? `/viewer/${source.source_version_id}/${source.canonical_root_node_id}`
      : null;
  const reasonId = `source-open-reason-${source.source_id}`;
  const unavailableReason =
    AVAILABILITY_REASON[source.availability] ??
    PIPELINE_REASON[source.pipeline_status] ??
    "Source content is not available yet.";

  const submitRename = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const title = String(new FormData(event.currentTarget).get("title") ?? "");
    onRename(title);
    setEditing(false);
  };

  return (
    <article className="resource-row">
      <div className="row-main">
        <h3>{source.display_title}</h3>
        <p className="resource-meta">
          <span className={`status ${STATUS_CLASS[source.pipeline_status]}`}>
            {source.pipeline_status}
          </span>
          {" | "}
          <span className={`status ${STATUS_CLASS[source.availability]}`}>
            {source.availability}
          </span>
        </p>
        {viewerPath === null ? (
          <p className="muted" id={reasonId}>
            {unavailableReason}
          </p>
        ) : null}
      </div>
      <div className="action-cluster">
        <button
          type="button"
          aria-label={`Open ${source.display_title}`}
          aria-describedby={viewerPath === null ? reasonId : undefined}
          disabled={viewerPath === null}
          onClick={viewerPath === null ? undefined : () => onOpen(viewerPath)}
        >
          Open source
        </button>
        {editing ? (
          <form onSubmit={submitRename}>
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
