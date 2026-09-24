import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Conversation } from "../api/schemas";
import { rememberActiveConversation } from "../state/conversations";
import { ChatPanel } from "./ChatPanel";

// Unlike ChatPanel.test.tsx, streamChat is NOT mocked here: these tests drive
// the real SSE parser against a fetch stub that yields server-shaped frames.
const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "6f1e1b6e-0a3a-4d6c-9a8e-1c2d3e4f5a6b";
const CONVERSATION_ID = "bbbbbbbb-0000-4000-8000-000000000001";

const capabilitiesBody = {
  capabilities: [
    {
      id: "grounded_chat",
      name: "Grounded chat",
      description:
        "Answer questions from selected notebook sources with pinned note revisions when chosen.",
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
const terminalBody = {
  answer_message_id: "dddddddd-0000-4000-8000-000000000002",
  manifest_id: "eeeeeeee-0000-4000-8000-000000000001",
  insufficient_evidence: false,
  state: {
    ...conversationBody,
    messages: [
      {
        id: "dddddddd-0000-4000-8000-000000000001",
        role: "user",
        content: "Stream please",
        manifest_id: "eeeeeeee-0000-4000-8000-000000000001",
        citations: [],
      },
      {
        id: "dddddddd-0000-4000-8000-000000000002",
        role: "assistant",
        content: "milpbookLM streams grounded answers.",
        manifest_id: "eeeeeeee-0000-4000-8000-000000000001",
        citations: [
          {
            evidence_id: "evidence-1",
            label: "Judgment p. 3",
            source_version_id: "12121212-0000-4000-8000-000000000001",
            node_id: "13131313-0000-4000-8000-000000000001",
            locator_kind: "char",
            char_start: 0,
            char_end: 9,
            url: "/viewer/12121212-0000-4000-8000-000000000001/13131313-0000-4000-8000-000000000001",
          },
        ],
      },
    ],
  },
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

function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sseStream(): {
  readonly response: Response;
  readonly push: (frame: string) => void;
  readonly close: () => void;
} {
  let push: (frame: string) => void = () => undefined;
  let close: () => void = () => undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      push = (frame) => controller.enqueue(encoder.encode(frame));
      close = () => controller.close();
    },
  });
  const response = new Response(body, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
  return { response, push, close };
}

function stubFetch(streamResponse: Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
      const url = requestUrl(input);
      if (url.includes("/messages/stream")) return streamResponse;
      if (url.includes("/capabilities")) return jsonResponse(200, capabilitiesBody);
      if (url.includes(`/conversations/${CONVERSATION_ID}`))
        return jsonResponse(200, conversationBody);
      return jsonResponse(404, { detail: "not found" });
    }),
  );
}

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function submitMessage(value: string): Promise<HTMLElement> {
  const textarea = await screen.findByRole("textbox");
  fireEvent.change(textarea, { target: { value } });
  fireEvent.keyDown(textarea, { key: "Enter" });
  return textarea;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ChatPanel live streaming", () => {
  it("renders streamed deltas progressively and settles on the cited answer", async () => {
    const stream = sseStream();
    stubFetch(stream.response);
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    sessionStorage.clear();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    await submitMessage("Stream please");
    await screen.findByText("Reviewing selected evidence and preparing an answer...");
    stream.push(sseFrame("token", { token: "" }));
    stream.push(sseFrame("token", { token: "milp" }));
    await screen.findByText("milp");
    stream.push(sseFrame("token", { token: "book" }));
    await screen.findByText("milpbook");
    stream.push(sseFrame("terminal", terminalBody));
    await screen.findByText("milpbookLM streams grounded answers.");
    expect(screen.queryByText("milpbook")).toBeNull();
    expect(screen.getByRole("link", { name: "Judgment p. 3" })).toBeDefined();
    expect(screen.getByRole("status", { name: "Assistant status" }).textContent).toBe(
      "Answer complete",
    );
  });

  it("reports a server error frame mid-stream without a phantom answer", async () => {
    const stream = sseStream();
    stubFetch(stream.response);
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    sessionStorage.clear();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    await submitMessage("Fail mid-stream");
    stream.push(sseFrame("token", { token: "partial answer" }));
    await screen.findByText("partial answer");
    stream.push(
      sseFrame("error", {
        code: "grounding_invalid",
        detail: "selected revision is no longer available",
      }),
    );
    await screen.findByText("The request failed: selected revision is no longer available");
    expect(screen.queryByText("partial answer")).toBeNull();
    expect(screen.queryByText("Answer complete")).toBeNull();
  });

  it("reports an honest error when the stream drops before the terminal event", async () => {
    const stream = sseStream();
    stubFetch(stream.response);
    rememberActiveConversation(NOTEBOOK_ID, CONVERSATION_ID);
    sessionStorage.clear();
    renderWithClient(
      <ChatPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} navigate={() => undefined} />,
    );
    await submitMessage("Drop mid-stream");
    stream.push(sseFrame("token", { token: "half an answer" }));
    await screen.findByText("half an answer");
    stream.close();
    await screen.findByText("The connection was lost. The conversation was reloaded.");
    expect(screen.queryByText("half an answer")).toBeNull();
    expect(screen.queryByText("Answer complete")).toBeNull();
  });
});
