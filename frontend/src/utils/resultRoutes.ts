/**
 * Centralized path builders for Result-centric routes (Epic 3–5).
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
