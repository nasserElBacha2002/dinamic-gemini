/**
 * Client-side row match: any provided string field may contain the query (case-insensitive).
 */
export function rowMatchesSearchQuery(
  query: string,
  parts: readonly (string | null | undefined)[]
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return parts.some((p) => (p ?? '').toLowerCase().includes(q));
}
