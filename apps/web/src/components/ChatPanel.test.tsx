import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChat } from "../api/chat-stream";
import type { Conversation } from "../api/schemas";
import { rememberActiveConversation } from "../state/conversations";
import { ChatPanel } from "./ChatPanel";

vi.mock("../api/chat-stream", () => ({
  streamChat: vi.fn(async () => undefined),
}));

const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "6f1e1b6e-0a3a-4d6c-9a8e-1c2d3e4f5a6b";
const CONVERSATION_ID = "bbbbbbbb-0000-4000-8000-000000000001";
const NOTE_A = "aaaaaaaa-0000-4000-8000-00000000000a";
const NOTE_B = "aaaaaaaa-0000-4000-8000-00000000000b";

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
} satisfies Conversation;

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
              created_by_name: "Chat Author",
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
              author_name: "Chat Author",
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

function stubGroundingFetch() {
  const note = (id: string, title: string, revisionId: string, revisionNumber: number) => ({
    note_id: id,
    notebook_id: NOTEBOOK_ID,
    kind: "user",
    editable: true,
    title,
    current_revision_id: revisionId,
    revision: revisionNumber,
    etag: String(revisionNumber),
    created_by_user_id: ACTOR_ID,
    created_by_name: "Chat Author",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });
  const revision = (id: string, noteId: string, revisionNumber: number) => ({
    revision_id: id,
    note_id: noteId,
    revision_number: revisionNumber,
    content: { blocks: [{ type: "paragraph", text: "Grounding" }] },
    content_sha256: `hash-${revisionNumber}`,
    author_user_id: ACTOR_ID,
    author_name: "Chat Author",
    provenance_refs: [],
    content_dependencies: [],
    created_at: "2026-01-01T00:00:00Z",
  });
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
            note(NOTE_A, "Research log", "cccccccc-0000-4000-8000-00000000000c", 2),
            note(NOTE_B, "Reading list", "cccccccc-0000-4000-8000-00000000000e", 1),
          ],
        });
      if (url.includes(`/notes/${NOTE_A}/revisions`))
        return jsonResponse(200, {
          revisions: [
            revision("cccccccc-0000-4000-8000-00000000000c", NOTE_A, 1),
            revision("cccccccc-0000-4000-8000-00000000000d", NOTE_A, 2),
          ],
        });
      if (url.includes(`/notes/${NOTE_B}/revisions`))
        return jsonResponse(200, {
          revisions: [revision("cccccccc-0000-4000-8000-00000000000e", NOTE_B, 1)],
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
    let finishStream = (): void => undefined;
    vi.mocked(streamChat).mockImplementationOnce(
      async (_conversationId, _content, _noteIds, _signal, handlers) =>
        new Promise<void>((resolve) => {
          finishStream = () => {
            handlers.onTerminal({
              answer_message_id: "dddddddd-0000-4000-8000-000000000001",
              manifest_id: "eeeeeeee-0000-4000-8000-000000000001",
              insufficient_evidence: false,
              state: {
                ...conversationBody,
                messages: [
                  {
                    id: "dddddddd-0000-4000-8000-000000000001",
                    role: "assistant",
                    content: "milpbookLM is grounded in selected evidence.",
                    manifest_id: "eeeeeeee-0000-4000-8000-000000000001",
                    citations: [],
                  },
                ],
              },
            });
            resolve();
          };
        }),
    );
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    stubApiFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "What is a notebook?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await vi.waitFor(() => expect(vi.mocked(streamChat)).toHaveBeenCalledTimes(1));
    expect(
      screen.getByText("Reviewing selected evidence and preparing an answer...").textContent,
    ).toContain("Reviewing selected evidence and preparing an answer");
    expect(screen.getByRole("status", { name: "Assistant status" }).textContent).toBe(
      "Request in progress",
    );
    expect(vi.mocked(streamChat).mock.calls[0]?.[0]).toBe(CONVERSATION_ID);
    expect(vi.mocked(streamChat).mock.calls[0]?.[1]).toBe("What is a notebook?");
    finishStream();
    expect(
      (await screen.findByText("milpbookLM is grounded in selected evidence.")).textContent,
    ).toBe("milpbookLM is grounded in selected evidence.");
    expect(screen.queryByText(/assistant, streaming/i)).toBeNull();
  });

  it("defaults to all notes in a foldable tree and submits only the checked revisions", async () => {
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    sessionStorage.clear();
    stubApiFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    expect(await screen.findByText("1 / 1 selected")).toBeDefined();
    expect(screen.queryByRole("checkbox")).toBeNull();
    const showButton = screen.getByRole("button", { name: "Show notes" });
    expect(showButton.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(showButton);
    const checkbox = (await screen.findByRole("checkbox")) as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    expect(screen.getByRole("button", { name: "Hide notes" })).toBeDefined();
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Use my note" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await vi.waitFor(() => expect(vi.mocked(streamChat)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(streamChat).mock.calls[0]?.[2]).toEqual([]);
  });

  it("seeds every revision selected with the tree collapsed on mount", async () => {
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    sessionStorage.clear();
    stubGroundingFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    expect(await screen.findByText("3 / 3 selected")).toBeDefined();
    expect(screen.queryByRole("checkbox")).toBeNull();
    const showButton = screen.getByRole("button", { name: "Show notes" });
    expect(showButton.getAttribute("aria-expanded")).toBe("false");
    expect(
      JSON.parse(
        sessionStorage.getItem(`milpbookLM:chat-notes:${ACTOR_ID}:${NOTEBOOK_ID}`) ?? "[]",
      ),
    ).toEqual([
      "cccccccc-0000-4000-8000-00000000000c",
      "cccccccc-0000-4000-8000-00000000000d",
      "cccccccc-0000-4000-8000-00000000000e",
    ]);
    fireEvent.click(showButton);
    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(4);
    for (const checkbox of checkboxes) expect((checkbox as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("rev 2")).toBeDefined();
    expect(screen.getAllByText("rev 1")).toHaveLength(1);
  });

  it("shows a spinner in the status line while a request is in flight", async () => {
    let finishStream = (): void => undefined;
    vi.mocked(streamChat).mockImplementationOnce(
      async (_conversationId, _content, _noteIds, _signal, handlers) =>
        new Promise<void>((resolve) => {
          finishStream = () => {
            handlers.onTerminal({
              answer_message_id: null,
              manifest_id: "eeeeeeee-0000-4000-8000-000000000001",
              insufficient_evidence: false,
              state: null,
            });
            resolve();
          };
        }),
    );
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    stubApiFetch();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Spinner check" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    const status = await screen.findByRole("status", { name: "Assistant status" });
    await vi.waitFor(() => expect(status.querySelector(".spinner")).not.toBeNull());
    expect(status.textContent).toBe("Request in progress");
    finishStream();
    await vi.waitFor(() => expect(status.querySelector(".spinner")).toBeNull());
    expect(status.textContent).toBe("Answer complete");
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
