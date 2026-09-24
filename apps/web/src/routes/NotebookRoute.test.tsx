import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotebookRoute } from "./NotebookRoute";

const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "735ed65a-c69e-48b3-940f-aceb99cd0bf3";

vi.mock("../state/auth", () => ({
  useAuth: () => ({
    actor: {
      user_id: ACTOR_ID,
      email: "user@example.com",
      display_name: "User",
      status: "active",
      installation_admin: false,
      csrf_token: "csrf-token",
    },
  }),
}));

const notebookBody = {
  notebook_id: NOTEBOOK_ID,
  title: "Atlas",
  custody_state: "active",
  membership: null,
};

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

describe("NotebookRoute", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("remembers the notebook after it loads, so Settings→Notebooks reopens it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes(`/notebooks/${NOTEBOOK_ID}`)) return jsonResponse(200, notebookBody);
        if (url.includes("/notes")) return jsonResponse(200, { notes: [] });
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <NotebookRoute navigate={vi.fn()} params={{ notebookId: NOTEBOOK_ID }} />
      </QueryClientProvider>,
    );

    await vi.waitFor(() =>
      expect(sessionStorage.getItem(`milpbookLM:last-notebook:${ACTOR_ID}`)).toBe(NOTEBOOK_ID),
    );
  });

  it("does not remember a notebook that fails to load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes(`/notebooks/${NOTEBOOK_ID}`)) return jsonResponse(403, { detail: {} });
        if (url.includes("/notes")) return jsonResponse(200, { notes: [] });
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <NotebookRoute navigate={vi.fn()} params={{ notebookId: NOTEBOOK_ID }} />
      </QueryClientProvider>,
    );

    await vi.waitFor(() =>
      expect(document.querySelector("h1#notebook-title")?.textContent).toBe("Loading..."),
    );
    expect(sessionStorage.getItem(`milpbookLM:last-notebook:${ACTOR_ID}`)).toBeNull();
  });
});
