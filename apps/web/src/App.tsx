import { useQuery } from "@tanstack/react-query";
import type { ComponentType, ReactNode } from "react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { getCapabilities } from "./api/client";
import { Shell } from "./components/Shell";
import { useAuth } from "./state/auth";
import { JobProvider } from "./state/jobs";
import { resolveNotebooksPath } from "./state/last-notebook";

const AuthRoute = lazy(() =>
  import("./routes/AuthRoute").then((module) => ({ default: module.AuthRoute })),
);
const NotebooksRoute = lazy(() =>
  import("./routes/NotebooksRoute").then((module) => ({ default: module.NotebooksRoute })),
);
const NotebookRoute = lazy(() =>
  import("./routes/NotebookRoute").then((module) => ({ default: module.NotebookRoute })),
);
const SettingsRoute = lazy(() =>
  import("./routes/SettingsRoute").then((module) => ({ default: module.SettingsRoute })),
);
const ViewerRoute = lazy(() =>
  import("./routes/ViewerRoute").then((module) => ({ default: module.ViewerRoute })),
);

type RouteMatch = {
  readonly component: ComponentType<RouteProps>;
  readonly params: Readonly<Record<string, string>>;
};
export type RouteProps = {
  readonly navigate: (path: string) => void;
  readonly params: Readonly<Record<string, string>>;
};

function matchRoute(path: string): RouteMatch {
  const viewer = path.match(/^\/viewer\/([^/]+)\/([^/]+)$/);
  if (viewer?.[1] !== undefined && viewer[2] !== undefined)
    return { component: ViewerRoute, params: { versionId: viewer[1], nodeId: viewer[2] } };
  const notebook = path.match(/^\/notebooks\/([^/]+)$/);
  if (notebook?.[1] !== undefined)
    return { component: NotebookRoute, params: { notebookId: notebook[1] } };
  if (path === "/settings") return { component: SettingsRoute, params: {} };
  return { component: NotebooksRoute, params: {} };
}

export function App(): ReactNode {
  const { actor, checking } = useAuth();
  const [path, setPath] = useState(window.location.pathname);
  const pathRef = useRef(path);
  const capabilities = useQuery({ queryKey: ["public", "capabilities"], queryFn: getCapabilities });
  const navigate = useCallback(
    (next: string) => {
      const target = resolveNotebooksPath(next, pathRef.current, actor?.user_id ?? null);
      window.history.pushState({}, "", target);
      pathRef.current = target;
      setPath(target);
      window.scrollTo(0, 0);
    },
    [actor],
  );
  useEffect(() => {
    const pop = (): void => {
      const current = window.location.pathname;
      const target = resolveNotebooksPath(current, pathRef.current, actor?.user_id ?? null);
      if (target !== current) window.history.replaceState({}, "", target);
      pathRef.current = target;
      setPath(target);
    };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, [actor]);
  if (checking) return <RouteLoading />;
  if (actor === null)
    return (
      <Suspense fallback={<RouteLoading />}>
        <AuthRoute navigate={navigate} params={{}} />
      </Suspense>
    );
  const match = matchRoute(path);
  const Route = match.component;
  return (
    <JobProvider enabled>
      <Shell path={path} navigate={navigate}>
        {capabilities.isError ? (
          <p className="notice error">
            Feature availability could not be loaded. Please refresh the page.
          </p>
        ) : null}
        <Suspense fallback={<RouteLoading />}>
          <Route navigate={navigate} params={match.params} />
        </Suspense>
      </Shell>
    </JobProvider>
  );
}

function RouteLoading(): ReactNode {
  return (
    <p className="route-loading" role="status">
      Loading view...
    </p>
  );
}
