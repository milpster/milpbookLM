import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { RouteProps } from "../App";
import { getCapabilities, getHealthComponents, getJobActivity } from "../api/client";
import { queryKeys } from "../api/query-keys";
import type { JobActivitySlot, ServerComponent } from "../api/schemas";
import { useAuth } from "../state/auth";

const componentLabels: Readonly<Record<string, string>> = {
  database: "Database",
  blob_store: "Blob store",
  worker: "Worker",
  chat_provider: "Chat provider",
  embedding_provider: "Embeddings",
  search: "Search",
};

function componentLabel(component: ServerComponent): string {
  return componentLabels[component.component] ?? component.component;
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function activeLine(slot: JobActivitySlot): string {
  return `${slot.kind} (${slot.state}, ${formatAge(slot.age_seconds)})`;
}

function recentLine(slot: JobActivitySlot): string {
  return `${slot.kind} ${slot.state} ${formatAge(slot.age_seconds)} ago`;
}

export function SettingsRoute(_props: RouteProps): ReactNode {
  const { actor } = useAuth();
  const capabilities = useQuery({ queryKey: queryKeys.capabilities(), queryFn: getCapabilities });
  const health = useQuery({
    queryKey: queryKeys.healthComponents(),
    queryFn: getHealthComponents,
    refetchInterval: 20_000,
  });
  const activity = useQuery({
    queryKey: queryKeys.jobActivity(),
    queryFn: getJobActivity,
    refetchInterval: 20_000,
  });
  return (
    <section className="page-stack" aria-labelledby="settings-title">
      <header className="page-heading">
        <div>
          <p className="kicker">Account and installation</p>
          <h1 id="settings-title">Settings</h1>
        </div>
      </header>
      <p className="health-strip">
        <span>Server health:</span>
        {health.isPending ? null : health.isError ? (
          <span title="Server health could not be loaded.">unavailable</span>
        ) : (
          health.data.components.map((component) => (
            <span className="health-chip" key={component.component} title={component.detail}>
              <span className={`health-dot ${component.status}`} aria-hidden="true" />
              {componentLabel(component)}
              <span className="sr-only">: {component.status}</span>
            </span>
          ))
        )}
      </p>
      <div className="split-content">
        <section className="panel-stack">
          <h2>Account</h2>
          <dl className="definition-list">
            <div>
              <dt>Name</dt>
              <dd>{actor?.display_name}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{actor?.email}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{actor?.installation_admin ? "Installation administrator" : "Member"}</dd>
            </div>
          </dl>
        </section>
        <section className="panel-stack">
          <h2>Server activity</h2>
          {activity.isPending ? (
            <p className="muted" role="status">
              Loading activity...
            </p>
          ) : activity.isError ? (
            <p className="muted">Server activity is unavailable right now.</p>
          ) : activity.data.active.length === 0 && activity.data.recent.length === 0 ? (
            <p className="muted">idle</p>
          ) : (
            <div className="form-stack compact">
              <p className="resource-meta">
                {activity.data.running} running · {activity.data.queued} queued
                {activity.data.active.length > 0
                  ? ` — ${activity.data.active.map(activeLine).join(", ")}`
                  : ""}
              </p>
              {activity.data.recent.length === 0 ? null : (
                <p className="muted">recent: {activity.data.recent.map(recentLine).join(", ")}</p>
              )}
            </div>
          )}
        </section>
      </div>
      <section className="panel-stack" aria-labelledby="capabilities-title">
        <h2 id="capabilities-title">Capabilities</h2>
        <p className="muted">Each feature reports whether it is available on this installation.</p>
        {capabilities.isPending ? (
          <p role="status">Loading capabilities...</p>
        ) : (
          <div className="capability-grid">
            {capabilities.data?.capabilities.map((capability) => (
              <article key={capability.id} className="capability">
                <div>
                  <h3>{capability.name}</h3>
                </div>
                <p>{capability.description}</p>
                <p className={`status ${capability.state}`}>{capability.state}</p>
                {capability.reason === null ? null : <p className="muted">{capability.reason}</p>}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
