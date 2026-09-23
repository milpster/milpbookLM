import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobProvider } from "../state/jobs";
import { SourcePanel } from "./SourcePanel";

const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "6f1e1b6e-0a3a-4d6c-9a8e-1c2d3e4f5a6b";
const SOURCE_ID = "cccccccc-0000-4000-8000-000000000001";
const VERSION_ID = "dddddddd-0000-4000-8000-000000000001";
const JOB_ID = "eeeeeeee-0000-4000-8000-000000000001";

const activatingSource = {
  source_id: SOURCE_ID,
  source_version_id: VERSION_ID,
  notebook_id: NOTEBOOK_ID,
  source_type: "plain_text",
  display_title: "Pasted source",
  availability: "active" as const,
  content_sha256: "abc123",
  content_size_bytes: 42,
  status: "quarantined_identified",
  pipeline_status: "activating" as const,
  etag: "etag-source",
  job_id: JOB_ID,
};
const terminalSource = {
  ...activatingSource,
  pipeline_status: "active" as const,
  job_id: undefined,
};
const succeededJob = {
  job_id: JOB_ID,
  kind: "source_processing",
  capacity_class: "standard",
  state: "succeeded",
  waiting_reason: null,
  priority: 0,
  attempts: 1,
  max_attempts: 3,
  progress: null,
  result_ref: null,
  error_code: null,
  cancel_reason: null,
  enqueued_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:00:01Z",
  finished_at: "2026-01-01T00:00:02Z",
};

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly listeners = new Map<string, Set<() => void>>();
  onerror: (() => void) | null = null;
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: () => void): void {
    const set = this.listeners.get(type) ?? new Set<() => void>();
    set.add(listener);
    this.listeners.set(type, set);
  }
  removeEventListener(type: string, listener: () => void): void {
    this.listeners.get(type)?.delete(listener);
  }
  close(): void {}
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function renderWithProviders(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <JobProvider enabled>{ui}</JobProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  FakeEventSource.instances = [];
});

describe("SourcePanel live status", () => {
  it("refreshes a pasted source to its terminal status once the ingestion job completes", async () => {
    let sourcesCalls = 0;
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes("/sources/paste")) return jsonResponse(201, activatingSource);
        if (url.includes("/sources") && url.includes("notebook_id")) {
          sourcesCalls += 1;
          return jsonResponse(200, sourcesCalls === 1 ? [] : [terminalSource]);
        }
        if (url.includes(`/jobs/${JOB_ID}`)) return jsonResponse(200, succeededJob);
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithProviders(<SourcePanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "My source" } });
    fireEvent.change(screen.getByLabelText(/text/i), { target: { value: "Some content" } });
    fireEvent.click(screen.getByRole("button", { name: /paste text/i }));
    expect(await screen.findByText("activating | active")).toBeDefined();
    expect(await screen.findByText("active | active")).toBeDefined();
  });
});
