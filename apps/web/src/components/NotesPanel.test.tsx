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
    expect((await screen.findAllByText(`Body of ${firstTitle}`)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Edit note" })).toBeDefined();
    expect(screen.queryByDisplayValue(`Body of ${firstTitle}`)).toBeNull();
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
    expect(screen.getByRole("button", { name: "Edit note" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /save new revision/i })).toBeNull();
  });

  it("shows an old revision read-only with a banner and return action, then restores the current read mode", async () => {
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
    expect(screen.getByRole("button", { name: "Edit note" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /save new revision/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "View" }));

    expect(screen.getByText("Viewing revision 1 (read-only)")).toBeDefined();
    expect((await screen.findAllByText("First body")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Second body")).toBeNull();
    expect(screen.queryByRole("button", { name: /save new revision/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit note" })).toBeNull();
    expect(screen.getByRole("button", { name: "Hide" })).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Return to current revision" }));

    expect(screen.queryByText("Viewing revision 1 (read-only)")).toBeNull();
    expect((await screen.findAllByText("Second body")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Edit note" })).toBeDefined();
    expect(screen.getByRole("button", { name: "View" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Edit note" }));
    expect(screen.getByRole("button", { name: /save new revision/i })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit note" })).toBeDefined();
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
      fireEvent.click(await screen.findByRole("button", { name: "Edit note" }));
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
      await vi.waitFor(() =>
        expect(screen.getByRole("button", { name: "Edit note" })).toBeDefined(),
      );
      expect(screen.getByText("Third body")).toBeDefined();
      expect(screen.queryByRole("button", { name: /save new revision/i })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Edit note" }));
      const updatedSaveButton = screen.getByRole("button", {
        name: /save new revision/i,
      }) as HTMLButtonElement;
      expect(updatedSaveButton.disabled).toBe(true);
      expect(screen.getByText("No changes yet.")).toBeDefined();
      expect(screen.getByDisplayValue("Third body")).toBeDefined();
    });
  });

  it("renders typed blocks and preserves them while editing the paragraph", async () => {
    const note = notes[0];
    if (note === undefined) throw new Error("expected note");
    const revision = {
      ...revisionsFor(note)[0],
      content: {
        blocks: [
          { type: "heading", level: 2, text: "Heading" },
          { type: "paragraph", text: "Editable" },
          { type: "ordered_list", items: ["One", "Two"] },
          { type: "unordered_list", items: ["Alpha", "Beta"] },
          { type: "unknown", payload: "fallback" },
        ],
      },
    };
    let submitted: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = requestUrl(input);
        const method =
          init?.method ??
          (typeof input === "string" || input instanceof URL ? "GET" : input.method);
        if (method === "POST" && url.includes(`/notes/${note.note_id}/revisions`)) {
          if (!(input instanceof Request)) throw new Error("expected ky request");
          submitted = JSON.parse(await input.clone().text());
          return jsonResponse(201, { note, revision });
        }
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) return jsonResponse(200, { notes: [note] });
        if (url.includes(`/notes/${note.note_id}/revisions`)) return jsonResponse(200, { revisions: [revision] });
        if (url.includes(`/notes/${note.note_id}`)) return jsonResponse(200, note);
        return jsonResponse(404, { detail: "not found" });
      }),
    );
    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    expect(await screen.findByRole("heading", { name: "Heading" })).toBeDefined();
    expect(screen.getAllByRole("list")).toHaveLength(3);
    expect(screen.getByText(/fallback/)).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Edit note" }));
    const textarea = screen.getByDisplayValue("Editable");
    fireEvent.change(textarea, { target: { value: "Edited" } });
    fireEvent.click(screen.getByRole("button", { name: /save new revision/i }));
    await vi.waitFor(() => expect(submitted).not.toBeUndefined());
    expect(submitted).toEqual({
      content: {
        blocks: [
          { type: "heading", level: 2, text: "Heading" },
          { type: "paragraph", text: "Edited" },
          { type: "ordered_list", items: ["One", "Two"] },
          { type: "unordered_list", items: ["Alpha", "Beta"] },
          { type: "unknown", payload: "fallback" },
        ],
      },
    });
  });

  it("creates a note with heading, paragraph, and list blocks", async () => {
    const sourceNote = notes[0];
    if (sourceNote === undefined) throw new Error("expected note fixture");
    const createdNote = {
      ...sourceNote,
      note_id: noteId(99),
      title: "Structured note",
      current_revision_id: revId(99),
      revision: 1,
      etag: "created-etag",
    };
    const createdRevision = {
      ...revisionsFor(createdNote)[0],
      content: {
        blocks: [
          { type: "paragraph", text: "Research starts here." },
          { type: "heading", level: 3, text: "Next steps" },
          { type: "ordered_list", items: ["First", "Second"] },
          { type: "unordered_list", items: ["Keep the source" ] },
        ],
      },
    };
    let submitted: unknown;
    let created = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = requestUrl(input);
        const method =
          init?.method ??
          (typeof input === "string" || input instanceof URL ? "GET" : input.method);
        if (method === "POST" && url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) {
          if (!(input instanceof Request)) throw new Error("expected ky request");
          submitted = JSON.parse(await input.clone().text());
          created = true;
          return jsonResponse(201, { note: createdNote, revision: createdRevision });
        }
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
          return jsonResponse(200, { notes: created ? [createdNote] : [] });
        if (url.includes(`/notes/${createdNote.note_id}/revisions`))
          return jsonResponse(200, { revisions: [createdRevision] });
        if (url.includes(`/notes/${createdNote.note_id}`)) return jsonResponse(200, createdNote);
        return jsonResponse(404, { detail: "not found" });
      }),
    );

    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull();
    const newNoteButton = screen.getByRole("button", { name: "New note" });
    expect(newNoteButton.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(newNoteButton);
    expect(newNoteButton.getAttribute("aria-expanded")).toBe("true");
    fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
      target: { value: "Structured note" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Paragraph block 1" }), {
      target: { value: "Research starts here." },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Add block" }));
    fireEvent.click(screen.getByRole("button", { name: "Heading" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Heading block 2" }), {
      target: { value: "Next steps" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Set heading block 2 to H3" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add block" }));
    fireEvent.click(screen.getByRole("button", { name: "Ordered list" }));
    fireEvent.change(screen.getByRole("textbox", { name: "List item 1 in block 3" }), {
      target: { value: "First" },
    });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "List item 1 in block 3" }), {
      key: "Enter",
    });
    fireEvent.change(screen.getByRole("textbox", { name: "List item 2 in block 3" }), {
      target: { value: "Second" },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Add block" }));
    fireEvent.click(screen.getByRole("button", { name: "Unordered list" }));
    fireEvent.change(screen.getByRole("textbox", { name: "List item 1 in block 4" }), {
      target: { value: "Keep the source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create note" }));

    await vi.waitFor(() => expect(submitted).not.toBeUndefined());
    expect(submitted).toEqual({
      title: "Structured note",
      content: {
        blocks: [
          { type: "paragraph", text: "Research starts here." },
          { type: "heading", level: 3, text: "Next steps" },
          { type: "ordered_list", items: ["First", "Second"] },
          { type: "unordered_list", items: ["Keep the source"] },
        ],
      },
    });
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull();
  });

  it("keeps the create subsection collapsed until New note, resets on Cancel, and clears the create error", async () => {
    const note = notes[0];
    if (note === undefined) throw new Error("expected note fixture");
    let createAttempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = requestUrl(input);
        const method =
          init?.method ??
          (typeof input === "string" || input instanceof URL ? "GET" : input.method);
        if (method === "POST" && url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) {
          createAttempts += 1;
          return jsonResponse(500, { detail: "storage unavailable" });
        }
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`))
          return jsonResponse(200, { notes: [note] });
        if (url.includes(`/notes/${note.note_id}/revisions`))
          return jsonResponse(200, { revisions: revisionsFor(note) });
        if (url.includes(`/notes/${note.note_id}`)) return jsonResponse(200, note);
        return jsonResponse(404, { detail: "not found" });
      }),
    );

    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    // Read-first mount: the reading output shows and the create form is absent.
    expect((await screen.findAllByText(`Body of ${note.title}`)).length).toBeGreaterThan(0);
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull();
    expect(document.getElementById("note-create-form")).toBeNull();
    const newNoteButton = screen.getByRole("button", { name: "New note" });
    expect(newNoteButton.getAttribute("aria-expanded")).toBe("false");
    expect(newNoteButton.getAttribute("aria-controls")).toBe("note-create-form");

    fireEvent.click(newNoteButton);
    expect(newNoteButton.getAttribute("aria-expanded")).toBe("true");
    fireEvent.change(screen.getByRole("textbox", { name: "Title" }), {
      target: { value: "Abandoned draft" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Paragraph block 1" }), {
      target: { value: "Draft body" },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Add block" }));
    fireEvent.click(screen.getByRole("button", { name: "Heading" }));

    // A failed create surfaces the error but keeps the subsection expanded.
    fireEvent.click(screen.getByRole("button", { name: "Create note" }));
    await vi.waitFor(() => expect(createAttempts).toBe(1));
    expect(screen.getByText("Creating the note failed. Please try again.")).toBeDefined();
    expect(newNoteButton.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(newNoteButton.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("note-create-form")).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull();
    expect(screen.queryByText("Creating the note failed. Please try again.")).toBeNull();

    // Reopening starts from a clean draft: empty title and a single empty paragraph.
    fireEvent.click(newNoteButton);
    const title = screen.getByRole("textbox", { name: "Title" }) as HTMLInputElement;
    expect(title.value).toBe("");
    const paragraph = screen.getByRole("textbox", {
      name: "Paragraph block 1",
    }) as HTMLTextAreaElement;
    expect(paragraph.value).toBe("");
    expect(screen.queryByRole("textbox", { name: "Heading block 2" })).toBeNull();
  });

  it("edits one rich block while preserving the other blocks", async () => {
    const note = notes[0];
    if (note === undefined) throw new Error("expected note fixture");
    const revision = {
      ...revisionsFor(note)[0],
      content: {
        blocks: [
          { type: "heading", level: 2, text: "Original heading" },
          { type: "paragraph", text: "Keep this paragraph" },
          { type: "unordered_list", items: ["Keep this item"] },
          { type: "unknown", payload: "keep this block" },
        ],
      },
    };
    let submitted: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = requestUrl(input);
        const method =
          init?.method ??
          (typeof input === "string" || input instanceof URL ? "GET" : input.method);
        if (method === "POST" && url.includes(`/notes/${note.note_id}/revisions`)) {
          if (!(input instanceof Request)) throw new Error("expected ky request");
          submitted = JSON.parse(await input.clone().text());
          return jsonResponse(201, { note, revision });
        }
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) return jsonResponse(200, { notes: [note] });
        if (url.includes(`/notes/${note.note_id}/revisions`)) return jsonResponse(200, { revisions: [revision] });
        if (url.includes(`/notes/${note.note_id}`)) return jsonResponse(200, note);
        return jsonResponse(404, { detail: "not found" });
      }),
    );

    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit note" }));
    const heading = screen.getByRole("textbox", { name: "Heading block 1" });
    expect(heading.className).toContain("note-editor-heading-input");
    fireEvent.change(heading, {
      target: { value: "Updated heading" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save new revision/i }));
    await vi.waitFor(() => expect(submitted).not.toBeUndefined());
    expect(submitted).toEqual({
      content: {
        blocks: [
          { type: "heading", level: 2, text: "Updated heading" },
          { type: "paragraph", text: "Keep this paragraph" },
          { type: "unordered_list", items: ["Keep this item"] },
          { type: "unknown", payload: "keep this block" },
        ],
      },
    });
  });

  it("adds and removes blocks and list items", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
        const url = requestUrl(input);
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) return jsonResponse(200, { notes: [] });
        return jsonResponse(404, { detail: "not found" });
      }),
    );

    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    expect(await screen.findByRole("heading", { name: "No notes yet" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "New note" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add block" }));
    fireEvent.click(screen.getByRole("button", { name: "Unordered list" }));
    fireEvent.click(screen.getByRole("button", { name: "Move block 2 up" }));
    expect(screen.getByRole("textbox", { name: "List item 1 in block 1" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Move block 1 down" }));
    const firstItem = screen.getByRole("textbox", { name: "List item 1 in block 2" });
    fireEvent.keyDown(firstItem, { key: "Enter" });
    const secondItem = screen.getByRole("textbox", { name: "List item 2 in block 2" });
    fireEvent.keyDown(secondItem, { key: "Backspace" });
    expect(screen.queryByRole("textbox", { name: "List item 2 in block 2" })).toBeNull();
    expect(document.activeElement).toBe(firstItem);
    fireEvent.click(screen.getByRole("button", { name: "Delete block 2" }));
    expect(screen.queryByRole("textbox", { name: "List item 1 in block 2" })).toBeNull();
  });

  it("keeps a legacy paragraph note editable", async () => {
    const note = notes[0];
    if (note === undefined) throw new Error("expected note fixture");
    const revision = {
      ...revisionsFor(note)[0],
      content: { blocks: [{ type: "paragraph", text: "Legacy body" }] },
    };
    let submitted: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = requestUrl(input);
        const method =
          init?.method ??
          (typeof input === "string" || input instanceof URL ? "GET" : input.method);
        if (method === "POST" && url.includes(`/notes/${note.note_id}/revisions`)) {
          if (!(input instanceof Request)) throw new Error("expected ky request");
          submitted = JSON.parse(await input.clone().text());
          return jsonResponse(201, { note, revision });
        }
        if (url.includes(`/notebooks/${NOTEBOOK_ID}/notes`)) return jsonResponse(200, { notes: [note] });
        if (url.includes(`/notes/${note.note_id}/revisions`)) return jsonResponse(200, { revisions: [revision] });
        if (url.includes(`/notes/${note.note_id}`)) return jsonResponse(200, note);
        return jsonResponse(404, { detail: "not found" });
      }),
    );

    renderWithClient(<NotesPanel actorId={ACTOR_ID} notebookId={NOTEBOOK_ID} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit note" }));
    const paragraph = await screen.findByDisplayValue("Legacy body");
    expect(paragraph.getAttribute("aria-label")).toBe("Paragraph block 1");
    expect(paragraph.className).toContain("note-editor-paragraph");
    fireEvent.change(paragraph, {
      target: { value: "Legacy body revised" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save new revision/i }));
    await vi.waitFor(() => expect(submitted).not.toBeUndefined());
    expect(submitted).toEqual({
      content: { blocks: [{ type: "paragraph", text: "Legacy body revised" }] },
    });
  });
});
