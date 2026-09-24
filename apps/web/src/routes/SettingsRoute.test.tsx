import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { capabilitySchema } from "../api/schemas";
import { SettingsRoute } from "./SettingsRoute";

vi.mock("../state/auth", () => ({
  useAuth: () => ({
    actor: {
      display_name: "User",
      email: "user@example.com",
      installation_admin: false,
    },
  }),
}));

const capability = {
  id: "notebook_management",
  name: "Notebook management",
  description: "Create, organize, duplicate, share, and manage notebook metadata.",
  classification: "stable/core",
  state: "available",
  reason: null,
};

const capabilityResponse = { capabilities: [capability] };

const activityBody = {
  queued: 1,
  running: 2,
  active: [
    { kind: "parse.text", state: "running", age_seconds: 12 },
    { kind: "index.build", state: "queued", age_seconds: 40 },
  ],
  recent: [{ kind: "source.acquire", state: "succeeded", age_seconds: 94 }],
};

const idleActivityBody = { queued: 0, running: 0, active: [], recent: [] };

const healthBody = {
  components: [
    { component: "database", status: "ok", detail: "connected" },
    { component: "blob_store", status: "ok", detail: "blob root writable" },
    { component: "worker", status: "degraded", detail: "no recent worker activity" },
    { component: "chat_provider", status: "ok", detail: "last request 2m ago" },
    { component: "embedding_provider", status: "ok", detail: "last request 1m ago" },
    { component: "search", status: "down", detail: "unavailable (database down)" },
  ],
};

function renderWithClient(ui: ReactNode): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SettingsRoute", () => {
  it("renders the server-provided capability description", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (): Promise<Response> =>
        new Response(JSON.stringify(capabilityResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    renderWithClient(<SettingsRoute navigate={vi.fn()} params={{}} />);
    expect(
      await screen.findByText("Create, organize, duplicate, share, and manage notebook metadata."),
    ).toBeTruthy();
  });

  it("renders the server health chip strip with a status dot per component", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const body = url.includes("/health/components") ? healthBody : capabilityResponse;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    renderWithClient(<SettingsRoute navigate={vi.fn()} params={{}} />);

    expect(await screen.findByText("Database")).toBeTruthy();
    const chips = document.querySelectorAll(".health-chip");
    expect(chips.length).toBe(6);
    const ok = document.querySelector(".health-dot.ok");
    const degraded = document.querySelector(".health-dot.degraded");
    const down = document.querySelector(".health-dot.down");
    expect(ok).not.toBeNull();
    expect(degraded).not.toBeNull();
    expect(down).not.toBeNull();
    expect(screen.getByText("Blob store")).toBeTruthy();
    expect(screen.getByText("Worker")).toBeTruthy();
    expect(screen.getByText("Chat provider")).toBeTruthy();
    expect(screen.getByText("Embeddings")).toBeTruthy();
    expect(screen.getByText("Search")).toBeTruthy();
    const workerChip = screen.getByText("Worker");
    expect(workerChip.getAttribute("title")).toBe("no recent worker activity");
    expect(workerChip.textContent).toBe("Worker: degraded");
    expect(screen.queryByRole("heading", { name: "Server health" })).toBeNull();
  });

  it("rejects missing or blank capability descriptions", () => {
    const { description: _description, ...withoutDescription } = capability;
    expect(capabilitySchema.safeParse(withoutDescription).success).toBe(false);
    expect(capabilitySchema.safeParse({ ...withoutDescription, description: "   " }).success).toBe(false);
  });

  it("renders the server-wide activity feed with counts, jobs, and ages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const body = url.includes("/jobs/activity")
          ? activityBody
          : url.includes("/health/components")
            ? healthBody
            : capabilityResponse;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    renderWithClient(<SettingsRoute navigate={vi.fn()} params={{}} />);

    expect(
      await screen.findByText(
        "2 running · 1 queued — parse.text (running, 12s), index.build (queued, 40s)",
      ),
    ).toBeTruthy();
    expect(screen.getByText("recent: source.acquire succeeded 1m ago")).toBeTruthy();
  });

  it("renders the idle state when the server reports no current or recent jobs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const body = url.includes("/jobs/activity")
          ? idleActivityBody
          : url.includes("/health/components")
            ? healthBody
            : capabilityResponse;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    renderWithClient(<SettingsRoute navigate={vi.fn()} params={{}} />);

    expect(await screen.findByText("idle", { selector: ".panel-stack p.muted" })).toBeTruthy();
  });

  it("renders a quiet unavailable note when the activity endpoint fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/jobs/activity")) return new Response("server error", { status: 500 });
        const body = url.includes("/health/components") ? healthBody : capabilityResponse;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    renderWithClient(<SettingsRoute navigate={vi.fn()} params={{}} />);

    expect(await screen.findByText("Server activity is unavailable right now.")).toBeTruthy();
  });
});
