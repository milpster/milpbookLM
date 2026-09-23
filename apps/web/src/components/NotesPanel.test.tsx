import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotesPanel } from "./NotesPanel";

const ACTOR_ID = "11111111-1111-4111-8111-111111111111";
const NOTEBOOK_ID = "6f1e1b6e-0a3a-4d6c-9a8e-1c2d3e4f5a6b";

const TITLES = [
  "Start here — your private research workspace",
  "Collecting sources",
  "Grounded chat with citations",
  "Research runs",
  "Notes — capture and transform your thinking",
  "Artifacts & study progress (API preview)",
  "Privacy, custody & what stays local",
];

const noteId = (index: number) =>
  `00000000-0000-4000-8000-${(index + 1).toString(16).padStart(12, "0")}`;
const revId = (index: number) =>
  `aaaaaaaa-0000-4000-8000-${(index + 1).toString(16).padStart(12, "0")}`;

const notes = TITLES.map((title, index) => ({
  note_id: noteId(index),
  notebook_id: NOTEBOOK_ID,
  kind: "user" as const,
  editable: true,
  title,
  current_revision_id: revId(index),
  revision: 1,
  etag: `etag-${index}`,
  created_by_user_id: ACTOR_ID,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}));

const revisionsFor = (note: (typeof notes)[number]) => [
  {
    revision_id: note.current_revision_id,
    note_id: note.note_id,
    revision_number: 1,
    content: { blocks: [{ type: "paragraph", text: `Body of ${note.title}` }] },
    content_sha256: "sha",
    author_user_id: ACTOR_ID,
    provenance_refs: [],
    content_dependencies: [],
    created_at: "2026-01-01T00:00:00Z",
  },
];

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("NotesPanel", () => {
  it("renders the seven seeded guide notes and auto-selects the first", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
          return jsonResponse(200, { notes });
        for (const note of notes) {
          if (url.includes(`/notes/${note.note_id}/revisions`))
            return jsonResponse(200, { revisions: revisionsFor(note) });
          if (url.includes(`/notes/${note.note_id}`)) return jsonResponse(200, note);
        }
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    for (const title of TITLES) {
      expect((await screen.findAllByText(title)).length).toBeGreaterThan(0);
    }
    const firstTitle = TITLES[0];
    if (firstTitle === undefined) throw new Error("expected a first seeded title");
    // Auto-select: the first note's body renders in the detail pane (both the
    // read-only paragraph view and the edit textarea defaultValue).
    expect(
      (await screen.findAllByText(`Body of ${firstTitle}`)).length,
    ).toBeGreaterThan(0);
  });
});
