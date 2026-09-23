import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { RouteProps } from "../App";
import { resolveLocator } from "../api/client";

export function ViewerRoute({ navigate, params }: RouteProps): ReactNode {
  const versionId = params["versionId"];
  const nodeId = params["nodeId"];
  const locator = useQuery({
    queryKey: ["authorized-locator", versionId, nodeId],
    queryFn: () => resolveLocator(versionId ?? "", nodeId ?? ""),
    enabled: versionId !== undefined && nodeId !== undefined,
  });
  return (
    <section className="page-stack viewer-page" aria-labelledby="viewer-title">
      <header className="page-heading">
        <div>
          <p className="kicker">Citation</p>
          <h1 id="viewer-title">Source viewer</h1>
        </div>
        <button
          type="button"
          onClick={() => {
            window.history.back();
            setTimeout(() => navigate(window.location.pathname), 0);
          }}
        >
          Back
        </button>
      </header>
      {locator.isPending ? <p role="status">Resolving citation...</p> : null}
      {locator.isError ? (
        <p className="notice error" role="alert">
          This citation is unavailable or no longer authorized.
        </p>
      ) : null}
      {locator.data === undefined ? null : <Viewer locator={locator.data} />}
    </section>
  );
}

function Viewer({
  locator,
}: {
  readonly locator: Awaited<ReturnType<typeof resolveLocator>>;
}): ReactNode {
  if (locator.state === "unavailable (purged)")
    return (
      <div className="empty-state">
        <h2>Source unavailable</h2>
        <p>This source version was removed and is no longer available.</p>
      </div>
    );
  const summary = `Version ${locator.source_version_id}, node ${locator.node_id}${locator.page === undefined ? "" : `, page ${locator.page}`}${locator.time_seconds === undefined ? "" : `, ${locator.time_seconds} seconds`}`;
  if (locator.media_type === "text/html" && locator.html !== undefined)
    return (
      <div className="viewer-frame">
        <p className="muted">{summary}</p>
        <iframe title="Source HTML" sandbox="" srcDoc={locator.html} />
      </div>
    );
  if (locator.media_type === "application/pdf" && locator.content_url !== undefined)
    return (
      <div className="viewer-frame">
        <p className="muted">{summary}</p>
        <object
          aria-label="PDF source"
          data={`${locator.content_url}${locator.page === undefined ? "" : `#page=${locator.page}`}`}
          type="application/pdf"
        >
          <a href={locator.content_url}>Open PDF source</a>
        </object>
      </div>
    );
  if (locator.media_type?.startsWith("audio/") && locator.content_url !== undefined)
    return (
      <div className="viewer-frame">
        <p className="muted">{summary}</p>
        {/* biome-ignore lint/a11y/useMediaCaption: the prototype locator does not expose an audio transcript */}
        <audio
          controls
          src={`${locator.content_url}${locator.time_seconds === undefined ? "" : `#t=${locator.time_seconds}`}`}
        />
      </div>
    );
  return (
    <div className="empty-state">
      <h2>Source not viewable here</h2>
      <p>{summary}</p>
      <p>This citation was verified, but the source content cannot be displayed in the app.</p>
    </div>
  );
}
