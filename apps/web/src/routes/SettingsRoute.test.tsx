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

vi.mock("../state/jobs", () => ({ useJobs: () => ({ jobs: [] }) }));

const capability = {
  id: "notebook_management",
  name: "Notebook management",
  description: "Create, organize, duplicate, share, and manage notebook metadata.",
  classification: "stable/core",
  state: "available",
  reason: null,
};

const capabilityResponse = { capabilities: [capability] };

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
});
