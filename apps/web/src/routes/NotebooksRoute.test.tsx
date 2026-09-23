import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotebooksRoute } from "./NotebooksRoute";

const ACTOR_ID = vi.hoisted(() => "11111111-1111-4111-8111-111111111111");

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

const NEW_NOTEBOOK_ID = "735ed65a-c69e-48b3-940f-aceb99cd0bf3";

const capabilitiesBody = {
  capabilities: [
    {
      id: "notebook_management",
      name: "Notebook management",
      description: "Create, organize, duplicate, share, and manage notebook metadata.",
      classification: "stable/core",
      state: "available",
      reason: null,
    },
  ],
};

const newNotebookBody = {
  notebook_id: NEW_NOTEBOOK_ID,
  title: "My research",
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

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method !== undefined) return init.method;
  if (typeof input === "string" || input instanceof URL) return "GET";
  return input.method;
}

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("NotebooksRoute", () => {
  it("opens the new notebook immediately after creating it", async () => {
    const navigate = vi.fn();
    let created = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = requestUrl(input);
        const method = requestMethod(input, init);
        if (url.includes("/capabilities")) return jsonResponse(200, capabilitiesBody);
        if (url.includes("/notebooks") && method === "POST") {
          created = true;
          return jsonResponse(201, newNotebookBody);
        }
        if (url.includes("/notebooks"))
          return jsonResponse(200, created ? [newNotebookBody] : []);
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithClient(<NotebooksRoute navigate={navigate} params={{}} />);
    fireEvent.change(await screen.findByLabelText("Notebook title"), {
      target: { value: "My research" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create notebook" }));
    await vi.waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(`/notebooks/${NEW_NOTEBOOK_ID}`),
    );
  });
});
