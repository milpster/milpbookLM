import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getJob } from "../api/client";
import type { Job } from "../api/schemas";

type JobState = {
  readonly jobs: readonly Job[];
  readonly watch: (jobId: string) => void;
};

const JobContext = createContext<JobState | null>(null);
const eventNames = ["job.enqueued", "job.started", "job.succeeded", "job.failed", "job.cancelled"];

export function JobProvider({
  children,
  enabled,
}: {
  readonly children: ReactNode;
  readonly enabled: boolean;
}): ReactNode {
  const [ids, setIds] = useState<readonly string[]>([]);
  const [jobs, setJobs] = useState<readonly Job[]>([]);
  const watch = useCallback(
    (jobId: string) =>
      setIds((current) => (current.includes(jobId) ? current : [...current, jobId])),
    [],
  );
  const resync = useCallback(async () => {
    const settled = await Promise.allSettled(ids.map(getJob));
    setJobs(settled.flatMap((entry) => (entry.status === "fulfilled" ? [entry.value] : [])));
  }, [ids]);

  useEffect(() => {
    if (!enabled) return;
    void resync();
    const events = new EventSource("/api/v1/jobs/events", { withCredentials: true });
    const update = (): void => {
      void resync();
    };
    for (const eventName of eventNames) events.addEventListener(eventName, update);
    events.addEventListener("resync", update);
    events.onerror = update;
    return () => events.close();
  }, [enabled, resync]);

  const value = useMemo(() => ({ jobs, watch }), [jobs, watch]);
  return <JobContext.Provider value={value}>{children}</JobContext.Provider>;
}

export function useJobs(): JobState {
  const state = useContext(JobContext);
  if (state === null) throw new Error("JobProvider is missing");
  return state;
}
