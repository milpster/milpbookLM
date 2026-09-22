import { HTTPError } from "ky";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Node has no `location` to resolve ky's relative prefixUrl against, so the
 * test drives the real ky pipeline through a minimal Request stand-in and a
 * stubbed fetch (a wire-level fake at the transport seam).
 */
class FakeRequest {
  readonly url: string;
  readonly method: string;
  readonly headers: Headers;

  constructor(input: string | FakeRequest, init: { method?: string; headers?: HeadersInit } = {}) {
    this.url = typeof input === "string" ? input : input.url;
    this.method = init.method ?? (typeof input === "string" ? "GET" : input.method);
    this.headers = new Headers(
      init.headers ?? (typeof input === "string" ? undefined : input.headers),
    );
  }

  clone(): FakeRequest {
    return new FakeRequest(this);
  }
}

const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const notebookBody = {
  notebook_id: "1b671a6e-400d-4e5f-8f8e-9d0f1a2b3c4d",
  title: "Notebook",
  custody_state: "active",
  membership: null,
};

describe("api client session-invalidation signal", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("Request", FakeRequest);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("clears credential state and fires the signal on a 401 mutation, keeping the caller error", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () =>
        jsonResponse(200, {
          user_id: "2c5a3a1d-93b8-4a11-9db4-2817e88a5c40",
          csrf_token: "csrf-token",
        }),
      )
      .mockImplementation(async () => jsonResponse(401, { detail: "authentication required" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await import("./client");

    await client.login("user@example.com", "password");
    expect(client.authHeaders()).toEqual({ "x-csrf-token": "csrf-token" });

    const listener = vi.fn();
    client.onSessionInvalidated(listener);

    const failure = await client
      .createNotebook({ title: "Notebook" })
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(HTTPError);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(client.authHeaders()).toEqual({});
  });

  it("fires the signal for every credential failure while a listener stays registered", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(401, { detail: "authentication required" })),
    );
    const client = await import("./client");
    const listener = vi.fn();
    client.onSessionInvalidated(listener);

    await expect(client.createNotebook({ title: "A" })).rejects.toThrow(HTTPError);
    await expect(client.createNotebook({ title: "B" })).rejects.toThrow(HTTPError);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it.each(["origin_rejected", "csrf_rejected"])(
    "fires the signal on a 403 credential failure (%s)",
    async (reason) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => jsonResponse(403, { detail: { reason } })),
      );
      const client = await import("./client");
      const listener = vi.fn();
      client.onSessionInvalidated(listener);

      await expect(client.createNotebook({ title: "Notebook" })).rejects.toThrow(HTTPError);
      expect(listener).toHaveBeenCalledTimes(1);
    },
  );

  it("keeps the session on a 403 authorization denial", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(403, { detail: { reason: "deny:not_member" } })),
    );
    const client = await import("./client");
    const listener = vi.fn();
    client.onSessionInvalidated(listener);

    await expect(client.getNotebook("1b671a6e-400d-4e5f-8f8e-9d0f1a2b3c4d")).rejects.toThrow(
      HTTPError,
    );
    expect(listener).not.toHaveBeenCalled();
  });

  it("keeps the session on a 403 with a non-credential body shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(403, { detail: "forbidden" })),
    );
    const client = await import("./client");
    const listener = vi.fn();
    client.onSessionInvalidated(listener);

    await expect(client.getNotebook("1b671a6e-400d-4e5f-8f8e-9d0f1a2b3c4d")).rejects.toThrow(
      HTTPError,
    );
    expect(listener).not.toHaveBeenCalled();
  });

  it("leaves successful responses untouched", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, notebookBody)),
    );
    const client = await import("./client");
    const listener = vi.fn();
    client.onSessionInvalidated(listener);

    const notebook = await client.createNotebook({ title: "Notebook" });
    expect(notebook.notebook_id).toBe(notebookBody.notebook_id);
    expect(listener).not.toHaveBeenCalled();
  });

  it("keeps the session on a rate-limit 429", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () =>
        jsonResponse(200, {
          user_id: "2c5a3a1d-93b8-4a11-9db4-2817e88a5c40",
          csrf_token: "csrf-token",
        }),
      )
      .mockImplementationOnce(async () =>
        jsonResponse(429, { detail: { reason: "rate_limited", retry_after_seconds: 300 } }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = await import("./client");
    await client.login("user@example.com", "password");
    const listener = vi.fn();
    client.onSessionInvalidated(listener);

    await expect(client.login("user@example.com", "password")).rejects.toThrow(HTTPError);
    expect(listener).not.toHaveBeenCalled();
    expect(client.authHeaders()).toEqual({ "x-csrf-token": "csrf-token" });
  });

  it("stops notifying after the listener unsubscribes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(401, { detail: "authentication required" })),
    );
    const client = await import("./client");
    const listener = vi.fn();
    const unsubscribe = client.onSessionInvalidated(listener);
    unsubscribe();

    await expect(client.createNotebook({ title: "Notebook" })).rejects.toThrow(HTTPError);
    expect(listener).not.toHaveBeenCalled();
  });
});
