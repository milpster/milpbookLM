import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Shell } from "./Shell";

const { getInstanceStats } = vi.hoisted(() => ({ getInstanceStats: vi.fn() }));

vi.mock("../api/client", () => ({ getInstanceStats }));

vi.mock("../state/auth", () => ({
  useAuth: () => ({
    actor: {
      user_id: "11111111-1111-4111-8111-111111111111",
      email: "user@example.com",
      display_name: "User",
      status: "active",
      installation_admin: false,
      csrf_token: "csrf-token",
    },
    checking: false,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
  }),
}));

vi.mock("../state/jobs", () => ({
  useJobs: () => ({ jobs: [], watch: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Shell", () => {
  it("renders aggregate counts and polls every twenty seconds", async () => {
    getInstanceStats.mockResolvedValue({ registered_users: 4, active_users: 2 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Shell path="/notebooks" navigate={() => undefined}><p>Content</p></Shell>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("4 registered · 2 users active")).toBeTruthy();
    expect(client.getQueryState(["actor", "instance-stats"])?.data).toEqual({ registered_users: 4, active_users: 2 });
  });

  it("keeps navigation usable without a count when aggregate request fails", async () => {
    getInstanceStats.mockRejectedValue(new Error("offline"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Shell path="/notebooks" navigate={() => undefined}><p>Content</p></Shell>
      </QueryClientProvider>,
    );
    await Promise.resolve();
    expect(screen.queryByText(/registered/)).toBeNull();
    expect(screen.getByRole("link", { name: "Notebooks" })).toBeTruthy();
  });

  it("renders the banner wordmark as milpbookLM with no space", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Shell path="/notebooks" navigate={() => undefined}>
          <p>Content</p>
        </Shell>
      </QueryClientProvider>,
    );
    // Accessible-name computation inserts a space between the text node and the
    // LM span, so assert on the rendered text content itself.
    const wordmark = document.querySelector("a.wordmark");
    expect(wordmark).not.toBeNull();
    expect(wordmark?.textContent).toBe("milpbookLM");
  });
});
