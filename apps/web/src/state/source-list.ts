import type { Source } from "../api/schemas";

export function mergeSources(
  persisted: readonly Source[],
  session: readonly Source[],
): readonly Source[] {
  const merged = new Map<string, Source>();
  for (const source of [...session, ...persisted]) {
    const identity = `${source.source_id}:${source.source_version_id}`;
    if (!merged.has(identity)) merged.set(identity, source);
  }
  return [...merged.values()];
}
