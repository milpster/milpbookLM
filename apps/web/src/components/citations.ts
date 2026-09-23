import type { Citation } from "../api/schemas";

/** Stable React key for a citation chip: source version + evidence node. */
export function citationKey(citation: Citation): string {
  return `${citation.source_version_id}:${citation.node_id}`;
}

/** Drop duplicate citations (same source version + node), keeping first occurrence. */
export function dedupeCitations(citations: readonly Citation[]): Citation[] {
  const seen = new Set<string>();
  const unique: Citation[] = [];
  for (const citation of citations) {
    const key = citationKey(citation);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(citation);
  }
  return unique;
}
