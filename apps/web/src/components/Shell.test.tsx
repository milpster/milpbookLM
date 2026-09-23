import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Shell } from "./Shell";

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
  it("renders the banner wordmark as milpbookLM with no space", () => {
    render(
      <Shell path="/notebooks" navigate={() => undefined}>
        <p>Content</p>
      </Shell>,
    );
    // Accessible-name computation inserts a space between the text node and the
    // LM span, so assert on the rendered text content itself.
    const wordmark = document.querySelector("a.wordmark");
    expect(wordmark).not.toBeNull();
    expect(wordmark?.textContent).toBe("milpbookLM");
  });
});
