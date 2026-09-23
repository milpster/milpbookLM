import { z } from "zod";

export const actorSchema = z.object({
  user_id: z.string().uuid(),
  email: z.string(),
  display_name: z.string(),
  status: z.string(),
  installation_admin: z.boolean(),
  csrf_token: z.string(),
});

export const loginSchema = z.object({ user_id: z.string().uuid(), csrf_token: z.string() });

export const notebookSchema = z.object({
  notebook_id: z.string().uuid(),
  title: z.string(),
  custody_state: z.string(),
  membership: z.string().nullable(),
});

export const sourceSchema = z.object({
  source_id: z.string().uuid(),
  source_version_id: z.string().uuid(),
  notebook_id: z.string().uuid(),
  source_type: z.string(),
  display_title: z.string(),
  availability: z.string(),
  content_sha256: z.string(),
  content_size_bytes: z.number(),
  status: z.string(),
  pipeline_status: z.string(),
  etag: z.string(),
  job_id: z.string().uuid().optional(),
});

export const citationSchema = z.object({
  evidence_id: z.string(),
  label: z.string(),
  source_version_id: z.string().uuid(),
  node_id: z.string().uuid(),
  locator_kind: z.string(),
  char_start: z.number(),
  char_end: z.number(),
  url: z.string(),
});

export const chatConfigSchema = z.object({
  style: z.enum(["standard", "learning", "custom"]),
  length: z.enum(["shorter", "default", "longer"]),
  output_language: z.enum(["DE", "EN"]),
});

export const messageSchema = z.object({
  id: z.string().uuid(),
  role: z.string(),
  content: z.string(),
  manifest_id: z.string().uuid(),
  citations: z.array(citationSchema),
});

export const conversationSchema = z.object({
  id: z.string().uuid(),
  notebook_id: z.string().uuid(),
  config: chatConfigSchema,
  instructions: z.string(),
  messages: z.array(messageSchema),
});

export const terminalSchema = z.object({
  answer_message_id: z.string().uuid().nullable(),
  manifest_id: z.string().uuid(),
  insufficient_evidence: z.boolean(),
  state: conversationSchema.nullable(),
});

export const capabilitySchema = z.object({
  id: z.string(),
  name: z.string(),
  classification: z.string(),
  state: z.enum(["available", "disabled", "degraded", "provisional"]),
  reason: z.string().nullable(),
});

export const capabilitiesSchema = z.object({ capabilities: z.array(capabilitySchema) });

export const jobSchema = z.object({
  job_id: z.string().uuid(),
  kind: z.string(),
  capacity_class: z.string(),
  state: z.string(),
  waiting_reason: z.string().nullable(),
  priority: z.number(),
  attempts: z.number(),
  max_attempts: z.number(),
  progress: z.unknown().nullable(),
  result_ref: z.string().nullable(),
  error_code: z.string().nullable(),
  cancel_reason: z.string().nullable(),
  enqueued_at: z.string().nullable(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});

export const locatorSchema = z.discriminatedUnion("state", [
  z.object({ state: z.literal("unavailable (purged)") }),
  z.object({
    state: z.literal("available"),
    source_version_id: z.string().uuid(),
    node_id: z.string().uuid(),
    media_type: z.string().optional(),
    html: z.string().optional(),
    content_url: z.string().optional(),
    page: z.number().int().positive().optional(),
    time_seconds: z.number().nonnegative().optional(),
  }),
]);

export type Actor = z.infer<typeof actorSchema>;
export type Capability = z.infer<typeof capabilitySchema>;
export type ChatConfig = z.infer<typeof chatConfigSchema>;
export type Citation = z.infer<typeof citationSchema>;
export type Conversation = z.infer<typeof conversationSchema>;
export type Job = z.infer<typeof jobSchema>;
export type Locator = z.infer<typeof locatorSchema>;
export type Notebook = z.infer<typeof notebookSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type Terminal = z.infer<typeof terminalSchema>;
