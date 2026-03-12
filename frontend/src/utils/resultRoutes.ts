/**
 * Centralized path builders for position-related routes.
 * Keeps navigation strings in one place and avoids typos.
 */

export function pathToAislePositions(inventoryId: string, aisleId: string): string {
  return `/inventories/${inventoryId}/aisles/${aisleId}/positions`;
}

export function pathToPositionDetail(
  inventoryId: string,
  aisleId: string,
  positionId: string
): string {
  return `/inventories/${inventoryId}/aisles/${aisleId}/positions/${positionId}`;
}

/** Epic 3.1.B — Job entities (v1 API) by job ID. */
export function pathToJobEntities(jobId: string): string {
  return `/job-entities/${encodeURIComponent(jobId)}`;
}
