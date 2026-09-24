import { z } from "zod";
import { authHeaders } from "./client";
import type { Terminal } from "./schemas";
import { terminalSchema } from "./schemas";

type StreamHandlers = {
  readonly onToken: (token: string) => void;
  readonly onTerminal: (terminal: Terminal) => void;
  readonly onCancelled: () => void;
};

const tokenSchema = z.object({ token: z.string() });
const errorSchema = z.object({ detail: z.string() });

class ChatStreamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatStreamError";
  }
}

export async function streamChat(
  conversationId: string,
  content: string,
  selectedNoteRevisionIds: readonly string[],
  signal: AbortSignal,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`/api/v1/conversations/${conversationId}/messages/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify({ content, selected_note_revision_ids: selectedNoteRevisionIds }),
    signal,
  });
  if (!response.ok || response.body === null) {
    throw new Error(`Chat stream failed (${response.status})`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let completed = false;
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += chunk.value;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      completed = dispatchFrame(frame, handlers) || completed;
      if (completed) {
        await reader.cancel();
        return;
      }
    }
  }
  if (buffer.trim() !== "") completed = dispatchFrame(buffer, handlers);
  if (!completed) throw new ChatStreamError("Chat stream ended without a terminal event");
}

function dispatchFrame(frame: string, handlers: StreamHandlers): boolean {
  const event = frame.match(/^event: (.+)$/m)?.[1];
  const data = frame.match(/^data: (.+)$/m)?.[1];
  if (event === undefined || data === undefined) return false;
  if (event === "token") {
    const parsed = tokenSchema.parse(JSON.parse(data));
    handlers.onToken(parsed.token);
  } else if (event === "terminal") {
    handlers.onTerminal(terminalSchema.parse(JSON.parse(data)));
    return true;
  } else if (event === "cancelled") {
    handlers.onCancelled();
    return true;
  } else if (event === "error") {
    const parsed = errorSchema.parse(JSON.parse(data));
    throw new ChatStreamError(parsed.detail);
  }
  return false;
}
