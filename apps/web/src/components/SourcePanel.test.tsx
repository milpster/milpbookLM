import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobProvider } from "../state/jobs";
import { SourcePanel } from "./SourcePanel";

const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "6f1e1b6e-0a3a-4d6c-9a8e-1c2d3e4f5a6b";
const SOURCE_ID = "cccccccc-0000-4000-8000-000000000001";
const VERSION_ID = "dddddddd-0000-4000-8000-000000000001";
const ROOT_NODE_ID = "aaaaaaaa-0000-4000-8000-000000000001";
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
  canonical_root_node_id: null,
  job_id: JOB_ID,
};
const terminalSource = {
  ...activatingSource,
  pipeline_status: "active" as const,
  canonical_root_node_id: ROOT_NODE_ID,
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

const source = (
  n: number,
  pipeline_status: string,
  availability: string,
): Record<string, unknown> => ({
  source_id: `cccccccc-0000-4000-8000-${n.toString(16).padStart(12, "0")}`,
  source_version_id: `dddddddd-0000-4000-8000-${n.toString(16).padStart(12, "0")}`,
  notebook_id: NOTEBOOK_ID,
  source_type: "plain_text",
  display_title: `Source ${n}`,
  availability,
  content_sha256: "abc123",
  content_size_bytes: 42,
  status: "quarantined_identified",
  pipeline_status,
  etag: `etag-${n}`,
  canonical_root_node_id: n === 4 ? ROOT_NODE_ID : null,
});

// Every enum value of pipeline_status and availability appears once.
const ALL_STATE_SOURCES: ReadonlyArray<readonly [number, string, string]> = [
  [1, "activating", "active"],
  [2, "parsing", "active"],
  [3, "parsed", "active"],
  [4, "active", "active"],
  [5, "parse_failed", "stale"],
  [6, "encrypted", "inaccessible_revoked"],
  [7, "inactive", "deleted_tombstoned"],
  [8, "tombstoned", "deleted_tombstoned"],
];

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
    const navigate = vi.fn();
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
    renderWithProviders(
      <SourcePanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={navigate} />,
    );
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "My source" } });
    fireEvent.change(screen.getByLabelText(/text/i), { target: { value: "Some content" } });
    fireEvent.click(screen.getByRole("button", { name: /paste text/i }));
    expect((await screen.findByText("activating")).className).toBe("status in-progress");
    expect(screen.getByText("active").className).toBe("status ready");
    await waitFor(() => expect(screen.getAllByText("active")).toHaveLength(2));
    for (const badge of screen.getAllByText("active")) {
      expect(badge.className).toBe("status ready");
    }
    expect(screen.queryByText("activating")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open Pasted source" }));
    expect(navigate).toHaveBeenCalledWith(`/viewer/${VERSION_ID}/${ROOT_NODE_ID}`);
  });

  it("colors every pipeline status and availability value with its state class", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes("/sources") && url.includes("notebook_id"))
          return jsonResponse(
            200,
            ALL_STATE_SOURCES.map(([n, pipeline, availability]) =>
              source(n, pipeline, availability),
            ),
          );
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithProviders(
      <SourcePanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={vi.fn()} />,
    );
    const expectBadges = (label: string, visualClass: string): void => {
      const badges = screen.getAllByText(label);
      expect(badges.length).toBeGreaterThan(0);
      for (const badge of badges) expect(badge.className).toBe(`status ${visualClass}`);
    };
    await screen.findByText("parsed");
    expectBadges("activating", "in-progress");
    expectBadges("parsing", "in-progress");
    expectBadges("parsed", "ready");
    expectBadges("active", "ready");
    expectBadges("parse_failed", "failed");
    expectBadges("stale", "failed");
    expectBadges("encrypted", "failed");
    expectBadges("inaccessible_revoked", "failed");
    expectBadges("inactive", "failed");
    expectBadges("tombstoned", "failed");
    expectBadges("deleted_tombstoned", "failed");
    expect(screen.getAllByRole("button", { name: /^Open Source / })).toHaveLength(
      ALL_STATE_SOURCES.length,
    );
    // The activating and parsing rows intentionally share this reason.
    expect(screen.getAllByText("Source content is still being prepared.")).toHaveLength(2);
    expect(screen.getByText("Source processing failed, so its contents are unavailable.")).toBeDefined();
  });
});
