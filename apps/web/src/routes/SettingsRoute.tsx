import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { RouteProps } from "../App";
import { getCapabilities, getHealthComponents } from "../api/client";
import { queryKeys } from "../api/query-keys";
import type { ServerComponent } from "../api/schemas";
import { useAuth } from "../state/auth";
import { useJobs } from "../state/jobs";

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

export function SettingsRoute(_props: RouteProps): ReactNode {
  const { actor } = useAuth();
  const { jobs } = useJobs();
  const capabilities = useQuery({ queryKey: queryKeys.capabilities(), queryFn: getCapabilities });
  const health = useQuery({
    queryKey: queryKeys.healthComponents(),
    queryFn: getHealthComponents,
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
          <h2>Job activity</h2>
          {jobs.length === 0 ? (
            <p className="muted">No background tasks in this session.</p>
          ) : (
            <ul className="plain-list">
              {jobs.map((job) => (
                <li key={job.job_id}>
                  <strong>{job.kind}</strong>
                  <span>{job.state}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <div className="settings-grid">
        <section className="panel-stack" aria-labelledby="capabilities-title">
          <h2 id="capabilities-title">Capabilities</h2>
          <p className="muted">
            Each feature reports whether it is available on this installation.
          </p>
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
        <section className="panel-stack" aria-labelledby="server-health-title">
          <h2 id="server-health-title">Server health</h2>
          <p className="muted">
            Status of this installation&apos;s components. Green means ok, amber degraded, red down.
          </p>
          {health.isPending ? (
            <p role="status">Loading server health...</p>
          ) : health.isError ? (
            <p className="notice error" role="alert">
              Server health could not be loaded. Please try again.
            </p>
          ) : (
            <ul className="health-list">
              {health.data.components.map((component) => (
                <li className="health-row" key={component.component}>
                  <span className={`health-dot ${component.status}`} aria-hidden="true" />
                  <strong>{componentLabel(component)}</strong>
                  <span className="resource-meta" title={component.detail}>
                    {component.detail}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </section>
  );
}
