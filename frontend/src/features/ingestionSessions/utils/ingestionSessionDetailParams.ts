/** Route/query guards for ingestion session detail (shared with page + tests). */

export function hasRequiredDetailParams(inventoryId: string, sessionId: string | undefined): boolean {
  return Boolean(inventoryId.trim() && sessionId);
}
