import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) return jsonResponse(200, { notes });
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
    // read-only paragraph view and the edit textarea value).
    expect((await screen.findAllByText(`Body of ${firstTitle}`)).length).toBeGreaterThan(0);
  });

  it("marks the sole revision as current and renders no dead View button", async () => {
    const firstNote = notes[0];
    if (firstNote === undefined) throw new Error("expected a seeded note fixture");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
          return jsonResponse(200, { notes: [firstNote] });
        if (url.includes(`/notes/${firstNote.note_id}/revisions`))
          return jsonResponse(200, { revisions: revisionsFor(firstNote) });
        if (url.includes(`/notes/${firstNote.note_id}`)) return jsonResponse(200, firstNote);
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    expect(await screen.findByText("(current)")).toBeDefined();
    expect(screen.queryByRole("button", { name: "View" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Hide" })).toBeNull();
    expect(screen.getByRole("button", { name: /save new revision/i })).toBeDefined();
  });

  it("shows an old revision read-only with a banner and return action, then restores editing", async () => {
    const note = {
      note_id: "00000000-0000-4000-8000-0000000000aa",
      notebook_id: NOTEBOOK_ID,
      kind: "user" as const,
      editable: true,
      title: "Revision flow",
      current_revision_id: "aaaaaaaa-0000-4000-8000-000000000002",
      revision: 2,
      etag: "etag-rev2",
      created_by_user_id: ACTOR_ID,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    };
    const revision = (revisionNumber: number, text: string) => ({
      revision_id: `aaaaaaaa-0000-4000-8000-${revisionNumber.toString(16).padStart(12, "0")}`,
      note_id: note.note_id,
      revision_number: revisionNumber,
      content: { blocks: [{ type: "paragraph", text }] },
      content_sha256: "sha",
      author_user_id: ACTOR_ID,
      provenance_refs: [],
      content_dependencies: [],
      created_at: "2026-01-01T00:00:00Z",
    });
    const revisions = [revision(1, "First body"), revision(2, "Second body")];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
          return jsonResponse(200, { notes: [note] });
        if (url.includes(`/notes/${note.note_id}/revisions`))
          return jsonResponse(200, { revisions });
        if (url.includes(`/notes/${note.note_id}`)) return jsonResponse(200, note);
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    expect((await screen.findAllByText("Second body")).length).toBeGreaterThan(0);
    expect(screen.getByText("(current)")).toBeDefined();
    expect(screen.getByRole("button", { name: "View" })).toBeDefined();
    expect(screen.getByRole("button", { name: /save new revision/i })).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "View" }));

    expect(screen.getByText("Viewing revision 1 (read-only)")).toBeDefined();
    expect((await screen.findAllByText("First body")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Second body")).toBeNull();
    expect(screen.queryByRole("button", { name: /save new revision/i })).toBeNull();
    expect(screen.getByRole("button", { name: "Hide" })).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Return to current revision" }));

    expect(screen.queryByText("Viewing revision 1 (read-only)")).toBeNull();
    expect((await screen.findAllByText("Second body")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /save new revision/i })).toBeDefined();
    expect(screen.getByRole("button", { name: "View" })).toBeDefined();
  });

  describe("revision dirty check", () => {
    const note = {
      note_id: "00000000-0000-4000-8000-0000000000bb",
      notebook_id: NOTEBOOK_ID,
      kind: "user" as const,
      editable: true,
      title: "Dirty check",
      current_revision_id: "aaaaaaaa-0000-4000-8000-000000000002",
      revision: 2,
      etag: "etag-rev2",
      created_by_user_id: ACTOR_ID,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    };
    const revision = (revisionNumber: number, text: string) => ({
      revision_id: `aaaaaaaa-0000-4000-8000-${revisionNumber.toString(16).padStart(12, "0")}`,
      note_id: note.note_id,
      revision_number: revisionNumber,
      content: { blocks: [{ type: "paragraph", text }] },
      content_sha256: "sha",
      author_user_id: ACTOR_ID,
      provenance_refs: [],
      content_dependencies: [],
      created_at: "2026-01-01T00:00:00Z",
    });
    const initialRevisions = [revision(1, "First body"), revision(2, "Second body")];

    function stubDirtyCheckApi(onPostRevision: () => void) {
      let saved = false;
      const updatedNote = {
        ...note,
        current_revision_id: "aaaaaaaa-0000-4000-8000-000000000003",
        revision: 3,
        etag: "etag-rev3",
      };
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
          const url = requestUrl(input);
          const method =
            init?.method ??
            (typeof input === "string" || input instanceof URL ? "GET" : input.method);
          if (method === "POST" && url.includes(`/notes/${note.note_id}/revisions`)) {
            saved = true;
            onPostRevision();
            return jsonResponse(200, { note: updatedNote, revision: revision(3, "Third body") });
          }
          if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
            return jsonResponse(200, { notes: [saved ? updatedNote : note] });
          if (url.includes(`/notes/${note.note_id}/revisions`))
            return jsonResponse(200, {
              revisions: saved ? [...initialRevisions, revision(3, "Third body")] : initialRevisions,
            });
          if (url.includes(`/notes/${note.note_id}`))
            return jsonResponse(200, saved ? updatedNote : note);
          return jsonResponse(404, { detail: "not found" });
        }),
      );
    }

    async function renderDetail() {
      renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
      const textarea = (await screen.findByDisplayValue("Second body")) as HTMLTextAreaElement;
      const saveButton = screen.getByRole("button", {
        name: /save new revision/i,
      }) as HTMLButtonElement;
      return { textarea, saveButton };
    }

    it("keeps Save new revision disabled with a hint until the text differs", async () => {
      stubDirtyCheckApi(() => undefined);
      const { textarea, saveButton } = await renderDetail();
      expect(saveButton.disabled).toBe(true);
      expect(screen.getByText("No changes yet.")).toBeDefined();
      fireEvent.change(textarea, { target: { value: "Second body, revised" } });
      expect(saveButton.disabled).toBe(false);
      expect(screen.queryByText("No changes yet.")).toBeNull();
    });

    it("treats whitespace-only changes as no change", async () => {
      stubDirtyCheckApi(() => undefined);
      const { textarea, saveButton } = await renderDetail();
      fireEvent.change(textarea, { target: { value: "  Second body \n" } });
      expect(saveButton.disabled).toBe(true);
      expect(screen.getByText("No changes yet.")).toBeDefined();
    });

    it("re-disables after a saved revision reloads as the current text", async () => {
      let saved = false;
      stubDirtyCheckApi(() => {
        saved = true;
      });
      const { textarea, saveButton } = await renderDetail();
      fireEvent.change(textarea, { target: { value: "Third body" } });
      expect(saveButton.disabled).toBe(false);
      fireEvent.click(saveButton);
      await vi.waitFor(() => expect(saved).toBe(true));
      await vi.waitFor(() => expect(saveButton.disabled).toBe(true));
      expect(screen.getByText("No changes yet.")).toBeDefined();
      expect(screen.getByDisplayValue("Third body")).toBeDefined();
    });
  });
});
