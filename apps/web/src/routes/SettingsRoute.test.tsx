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

  it("rejects missing or blank capability descriptions", () => {
    const { description: _description, ...withoutDescription } = capability;
    expect(capabilitySchema.safeParse(withoutDescription).success).toBe(false);
    expect(capabilitySchema.safeParse({ ...withoutDescription, description: "   " }).success).toBe(false);
  });
});
