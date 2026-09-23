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
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += chunk.value;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) dispatchFrame(frame, handlers);
  }
}

function dispatchFrame(frame: string, handlers: StreamHandlers): void {
  const event = frame.match(/^event: (.+)$/m)?.[1];
  const data = frame.match(/^data: (.+)$/m)?.[1];
  if (event === undefined || data === undefined) return;
  if (event === "token") {
    const parsed = tokenSchema.parse(JSON.parse(data));
    handlers.onToken(parsed.token);
  } else if (event === "terminal") {
    handlers.onTerminal(terminalSchema.parse(JSON.parse(data)));
  } else if (event === "cancelled") {
    handlers.onCancelled();
  }
}
