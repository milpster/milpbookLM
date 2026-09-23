import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getInstanceStats } from "../api/client";
import { queryKeys } from "../api/query-keys";
import { useAuth } from "../state/auth";
import { useJobs } from "../state/jobs";
import { BrandMark } from "./BrandMark";

type ShellProps = {
  readonly path: string;
  readonly navigate: (path: string) => void;
  readonly children: ReactNode;
};

const links = [
  ["/notebooks", "Notebooks"],
  ["/settings", "Settings"],
] as const;

export function Shell({ path, navigate, children }: ShellProps): ReactNode {
  const { actor, signOut } = useAuth();
  const { jobs } = useJobs();
  const stats = useQuery({
    queryKey: queryKeys.instanceStats(),
    queryFn: getInstanceStats,
    enabled: actor !== null,
    refetchInterval: 20_000,
  });
  const activeJobs = jobs.filter(
    (job) => !["succeeded", "failed", "cancelled"].includes(job.state),
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="topbar">
        <a
          className="wordmark"
          href="/notebooks"
          onClick={(event) => {
            event.preventDefault();
            navigate("/notebooks");
          }}
        >
          <BrandMark className="brand-mark" />
          <span>
            milpbook<span className="wordmark-lm">LM</span>
          </span>
        </a>
        {actor === null ? null : <p className="actor-label">{actor.display_name}</p>}
        {stats.data === undefined ? null : (
          <p className="instance-stats">{stats.data.registered_users} registered · {stats.data.logged_in_users} signed in</p>
        )}
      </header>
      <div className="shell-body">
        <nav aria-label="Primary" className="sidenav">
          {links.map(([href, label]) => (
            <a
              key={href}
              href={href}
              aria-current={path.startsWith(href) ? "page" : undefined}
              onClick={(event) => {
                event.preventDefault();
                navigate(href);
              }}
            >
              {label}
            </a>
          ))}
          {actor === null ? null : (
            <button className="nav-action" type="button" onClick={() => void signOut()}>
              Log out
            </button>
          )}
        </nav>
        <main id="main-content" tabIndex={-1} className="main-content">
          {children}
        </main>
      </div>
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {activeJobs.length === 0
          ? "No background tasks"
          : `${activeJobs.length} background tasks: ${activeJobs.map((job) => `${job.kind}: ${job.state}`).join(". ")}`}
      </div>
    </div>
  );
}
