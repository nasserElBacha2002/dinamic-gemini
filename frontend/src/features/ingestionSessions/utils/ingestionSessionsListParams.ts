/** Query params builder for capture sessions list (shared with page + tests). */

export function buildSessionsListParams(inventoryId: string, selectedAisleId: string) {
  return {
    inventoryId,
    aisleId: selectedAisleId.trim() ? selectedAisleId : undefined,
    page: 1,
    pageSize: 100,
  };
}
