import { z } from "zod";

export const actorSchema = z.object({
  user_id: z.string().uuid(),
  email: z.string(),
  display_name: z.string(),
  status: z.string(),
  installation_admin: z.boolean(),
  csrf_token: z.string(),
});

export const instanceStatsSchema = z.object({
  registered_users: z.number().int().nonnegative(),
  active_users: z.number().int().nonnegative(),
});

export const serverComponentSchema = z.object({
  component: z.string(),
  status: z.enum(["ok", "degraded", "down"]),
  detail: z.string(),
});

export const serverComponentsSchema = z.object({
  components: z.array(serverComponentSchema),
});

export const loginSchema = z.object({ user_id: z.string().uuid(), csrf_token: z.string() });

export const notebookSchema = z.object({
  notebook_id: z.string().uuid(),
  title: z.string(),
  custody_state: z.string(),
  membership: z.string().nullable(),
});

// Exact values from the server enums (source_versions.status / sources.availability).
export const sourcePipelineStatusSchema = z.enum([
  "activating",
  "parsing",
  "parsed",
  "encrypted",
  "parse_failed",
  "active",
  "inactive",
  "tombstoned",
]);

export const sourceAvailabilitySchema = z.enum([
  "active",
  "stale",
  "inaccessible_revoked",
  "deleted_tombstoned",
]);

export const sourceSchema = z.object({
  source_id: z.string().uuid(),
  source_version_id: z.string().uuid(),
  notebook_id: z.string().uuid(),
  source_type: z.string(),
  display_title: z.string(),
  availability: sourceAvailabilitySchema,
  content_sha256: z.string(),
  content_size_bytes: z.number(),
  status: z.string(),
  pipeline_status: sourcePipelineStatusSchema,
  etag: z.string(),
  canonical_root_node_id: z.string().uuid().nullable(),
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
  description: z.string().trim().min(1),
  classification: z.string(),
  state: z.enum(["available", "disabled", "degraded", "provisional"]),
  reason: z.string().nullable(),
});

export const capabilitiesSchema = z.object({ capabilities: z.array(capabilitySchema) });

// Exact values from the durable JobState enum (ch15).
export const jobStateSchema = z.enum([
  "queued",
  "leased",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "waiting_external",
  "waiting_capacity",
  "retry_scheduled",
]);

export const jobSchema = z.object({
  job_id: z.string().uuid(),
  kind: z.string(),
  capacity_class: z.string(),
  state: jobStateSchema,
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
    text: z.string().optional(),
    content_url: z.string().optional(),
    page: z.number().int().positive().optional(),
    time_seconds: z.number().nonnegative().optional(),
  }),
]);

// Exact values from the NoteKind domain enum.
export const noteKindSchema = z.enum(["user", "saved_chat_response", "derived_from_source"]);

export const noteContentRefSchema = z.object({
  kind: z.string(),
  id: z.string().uuid(),
});

export const noteRevisionSchema = z.object({
  revision_id: z.string().uuid(),
  note_id: z.string().uuid(),
  revision_number: z.number().int().positive(),
  content: z.record(z.string(), z.unknown()),
  content_sha256: z.string(),
  author_user_id: z.string().uuid(),
  provenance_refs: z.array(noteContentRefSchema),
  content_dependencies: z.array(noteContentRefSchema),
  created_at: z.string(),
});

export const noteSchema = z.object({
  note_id: z.string().uuid(),
  notebook_id: z.string().uuid(),
  kind: noteKindSchema,
  editable: z.boolean(),
  title: z.string(),
  current_revision_id: z.string().uuid().nullable(),
  revision: z.number().int().positive(),
  etag: z.string(),
  created_by_user_id: z.string().uuid(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const noteListSchema = z.object({ notes: z.array(noteSchema) });
export const revisionListSchema = z.object({ revisions: z.array(noteRevisionSchema) });
export const noteSnapshotSchema = z.object({ note: noteSchema, revision: noteRevisionSchema });

export type Actor = z.infer<typeof actorSchema>;
export type Capability = z.infer<typeof capabilitySchema>;
export type ChatConfig = z.infer<typeof chatConfigSchema>;
export type Citation = z.infer<typeof citationSchema>;
export type Conversation = z.infer<typeof conversationSchema>;
export type Job = z.infer<typeof jobSchema>;
export type Locator = z.infer<typeof locatorSchema>;
export type Note = z.infer<typeof noteSchema>;
export type NoteKind = z.infer<typeof noteKindSchema>;
export type NoteRevision = z.infer<typeof noteRevisionSchema>;
export type NoteSnapshot = z.infer<typeof noteSnapshotSchema>;
export type Notebook = z.infer<typeof notebookSchema>;
export type ServerComponent = z.infer<typeof serverComponentSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type Terminal = z.infer<typeof terminalSchema>;

// Domain TERMINAL_STATES for durable jobs; drives one refetch per finished job.
export const terminalJobStates: ReadonlySet<Job["state"]> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);
