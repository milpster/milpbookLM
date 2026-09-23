import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChat } from "../api/chat-stream";
import { rememberActiveConversation } from "../state/conversations";
import { ChatPanel } from "./ChatPanel";

vi.mock("../api/chat-stream", () => ({
  streamChat: vi.fn(async () => undefined),
}));

const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "6f1e1b6e-0a3a-4d6c-9a8e-1c2d3e4f5a6b";
const CONVERSATION_ID = "bbbbbbbb-0000-4000-8000-000000000001";

const capabilitiesBody = {
  capabilities: [
    {
      id: "grounded_chat",
      name: "Grounded chat",
      description: "Answer questions from selected notebook sources with pinned note revisions when chosen.",
      classification: "stable/core",
      state: "available",
      reason: null,
    },
  ],
};
const conversationBody = {
  id: CONVERSATION_ID,
  notebook_id: NOTEBOOK_ID,
  config: { style: "standard", length: "default", output_language: "EN" },
  instructions: "",
  messages: [],
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

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function stubApiFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
      const url = requestUrl(input);
      if (url.includes("/capabilities")) return jsonResponse(200, capabilitiesBody);
      if (url.includes(`/conversations/${CONVERSATION_ID}`))
        return jsonResponse(200, conversationBody);
      if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
        return jsonResponse(200, {
          notes: [
            {
              note_id: "aaaaaaaa-0000-4000-8000-000000000001",
              notebook_id: NOTEBOOK_ID,
              kind: "user",
              editable: true,
              title: "Selected note",
              current_revision_id: "cccccccc-0000-4000-8000-000000000001",
              revision: 1,
              etag: "1",
              created_by_user_id: ACTOR_ID,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
        });
      if (url.includes("/notes/aaaaaaaa-0000-4000-8000-000000000001/revisions"))
        return jsonResponse(200, {
          revisions: [
            {
              revision_id: "cccccccc-0000-4000-8000-000000000001",
              note_id: "aaaaaaaa-0000-4000-8000-000000000001",
              revision_number: 1,
              content: { blocks: [{ type: "paragraph", text: "Pinned" }] },
              content_sha256: "hash",
              author_user_id: ACTOR_ID,
              provenance_refs: [],
              content_dependencies: [],
              created_at: "2026-01-01T00:00:00Z",
            },
          ],
        });
      return jsonResponse(404, { detail: "not found" });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ChatPanel composer", () => {
  it("submits the message on Enter", async () => {
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    stubApiFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "What is a notebook?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await vi.waitFor(() => expect(vi.mocked(streamChat)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(streamChat).mock.calls[0]?.[0]).toBe(CONVERSATION_ID);
    expect(vi.mocked(streamChat).mock.calls[0]?.[1]).toBe("What is a notebook?");
  });

  it("submits only explicitly selected immutable note revisions", async () => {
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    stubApiFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    const checkbox = await screen.findByRole("checkbox");
    fireEvent.click(checkbox);
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Use my note" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await vi.waitFor(() => expect(vi.mocked(streamChat)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(streamChat).mock.calls[0]?.[2]).toEqual([
      "cccccccc-0000-4000-8000-000000000001",
    ]);
  });

  it("keeps the draft and does not submit on Shift+Enter", async () => {
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    stubApiFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    const textarea = (await screen.findByRole("textbox")) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "line one\nline two" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(vi.mocked(streamChat)).not.toHaveBeenCalled();
    expect(textarea.value).toBe("line one\nline two");
  });
});
