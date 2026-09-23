import ky, { HTTPError } from "ky";
import type { z } from "zod";
import type {
  CreateNotebookRequest,
  LoginRequest,
  PasteSourceRequest,
  RegisterRequest,
} from "./contract";
import type { Actor, ChatConfig, Source } from "./schemas";
import {
  actorSchema,
  capabilitiesSchema,
  conversationSchema,
  jobSchema,
  instanceStatsSchema,
  locatorSchema,
  loginSchema,
  noteListSchema,
  noteSchema,
  noteSnapshotSchema,
  notebookSchema,
  revisionListSchema,
  sourceSchema,
} from "./schemas";

let csrfToken = "";

type SessionInvalidationListener = () => void;
const sessionInvalidationListeners = new Set<SessionInvalidationListener>();

/** Subscribe to global session-invalidation events (dead cookie / CSRF drift). */
export function onSessionInvalidated(listener: SessionInvalidationListener): () => void {
  sessionInvalidationListeners.add(listener);
  return () => {
    sessionInvalidationListeners.delete(listener);
  };
}

function emitSessionInvalidation(): void {
  csrfToken = "";
  for (const listener of sessionInvalidationListeners) listener();
}

const api = ky.create({
  prefixUrl: "/api/v1",
  credentials: "include",
  retry: 0,
  timeout: 30_000,
  hooks: {
    beforeRequest: [
      (request) => {
        if (request.method !== "GET" && request.method !== "HEAD" && csrfToken !== "") {
          request.headers.set("x-csrf-token", csrfToken);
        }
      },
    ],
    afterResponse: [
      async (_request, _options, response) => {
        if (response.status === 401) emitSessionInvalidation();
        return undefined; // never intercept: per-caller error handling stays intact
      },
    ],
  },
});

async function parsed<T extends z.ZodType>(
  request: Promise<Response>,
  schema: T,
): Promise<z.output<T>> {
  const response = await request;
  return schema.parse(await response.json());
}

export function isApiError(error: unknown): error is HTTPError {
  return error instanceof HTTPError;
}

export async function register(input: RegisterRequest): Promise<void> {
  await api.post("auth/register", { json: input });
}

export async function login(
  email: LoginRequest["email"],
  password: LoginRequest["password"],
): Promise<string> {
  const result = await parsed(api.post("auth/login", { json: { email, password } }), loginSchema);
  csrfToken = result.csrf_token;
  return result.user_id;
}

export async function logout(): Promise<void> {
  await api.post("auth/logout");
  csrfToken = "";
}

export async function getActor(): Promise<Actor> {
  const actor = await parsed(api.get("auth/me"), actorSchema);
  csrfToken = actor.csrf_token;
  return actor;
}
export const getCapabilities = () => parsed(api.get("capabilities"), capabilitiesSchema);
export const getInstanceStats = () => parsed(api.get("auth/instance-stats"), instanceStatsSchema);
export const listNotebooks = () => parsed(api.get("notebooks"), notebookSchema.array());
export const getNotebook = (id: string) => parsed(api.get(`notebooks/${id}`), notebookSchema);
export const createNotebook = (input: CreateNotebookRequest) =>
  parsed(api.post("notebooks", { json: input }), notebookSchema);
export const listSources = (notebookId: string) =>
  parsed(api.get("sources", { searchParams: { notebook_id: notebookId } }), sourceSchema.array());

export const pasteSource = (input: PasteSourceRequest) =>
  parsed(api.post("sources/paste", { json: input }), sourceSchema);

export const uploadSource = (notebookId: string, file: File) => {
  const data = new FormData();
  data.set("file", file);
  return parsed(
    api.post(`sources/import?notebook_id=${encodeURIComponent(notebookId)}`, { body: data }),
    sourceSchema,
  );
};

export const getSource = (id: string) => parsed(api.get(`sources/${id}`), sourceSchema);
export const selectSource = (id: string) => parsed(api.post(`sources/${id}/select`), sourceSchema);
export const removeSource = (id: string) => parsed(api.post(`sources/${id}/remove`), sourceSchema);
export const renameSource = (source: Source, title: string) =>
  parsed(
    api.patch(`sources/${source.source_id}`, {
      json: { title },
      headers: { "If-Match": source.etag },
    }),
    sourceSchema,
  );

export const createConversation = (notebookId: string, config: ChatConfig) =>
  parsed(
    api.post("conversations", { json: { notebook_id: notebookId, ...config } }),
    conversationSchema,
  );
export const getConversation = (id: string) =>
  parsed(api.get(`conversations/${id}`), conversationSchema);
export const updateConversationConfig = (id: string, config: ChatConfig) =>
  parsed(api.put(`conversations/${id}/config`, { json: config }), conversationSchema);
export const cancelConversation = async (id: string): Promise<void> => {
  await api.post(`conversations/${id}/cancel`);
};
export const listNotes = (notebookId: string) =>
  parsed(api.get(`notebooks/${notebookId}/notes`), noteListSchema);
export const getNote = (id: string) => parsed(api.get(`notes/${id}`), noteSchema);
export const listNoteRevisions = (id: string) =>
  parsed(api.get(`notes/${id}/revisions`), revisionListSchema);
export const createNote = (
  notebookId: string,
  title: string,
  content: Record<string, unknown>,
) =>
  parsed(
    api.post(`notebooks/${notebookId}/notes`, { json: { title, content } }),
    noteSnapshotSchema,
  );
export const editNote = (id: string, etag: string, content: Record<string, unknown>) =>
  parsed(
    api.post(`notes/${id}/revisions`, { json: { content }, headers: { "If-Match": etag } }),
    noteSnapshotSchema,
  );
export const getJob = (id: string) => parsed(api.get(`jobs/${id}`), jobSchema);
export const resolveLocator = (versionId: string, nodeId: string) =>
  parsed(api.get(`source-versions/${versionId}/nodes/${nodeId}`), locatorSchema);

export function authHeaders(): HeadersInit {
  return csrfToken === "" ? {} : { "x-csrf-token": csrfToken };
}
