import type { paths } from "../generated/api";

type JsonBody<
  Path extends keyof paths,
  Method extends keyof paths[Path],
> = paths[Path][Method] extends { requestBody: { content: { "application/json": infer Body } } }
  ? Body
  : never;

export type LoginRequest = JsonBody<"/api/v1/auth/login", "post">;
export type RegisterRequest = JsonBody<"/api/v1/auth/register", "post">;
export type CreateNotebookRequest = JsonBody<"/api/v1/notebooks", "post">;
export type PasteSourceRequest = JsonBody<"/api/v1/sources/paste", "post">;
export type CreateConversationRequest = JsonBody<"/api/v1/conversations", "post">;
