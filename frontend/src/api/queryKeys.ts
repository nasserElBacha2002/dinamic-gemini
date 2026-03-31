/**
 * TanStack Query key factory for v3 API.
 * Keys are deterministic and domain-oriented for precise invalidation.
 */

export const queryKeys = {
  all: ['v3'] as const,

  inventories: {
    all: ['v3', 'inventories'] as const,
    list: () => [...queryKeys.inventories.all, 'list'] as const,
    detail: (inventoryId: string) => [...queryKeys.inventories.all, 'detail', inventoryId] as const,
    visualReferences: (inventoryId: string) =>
      [...queryKeys.inventories.all, 'visual-references', inventoryId] as const,
    metrics: (inventoryId: string) => [...queryKeys.inventories.all, 'metrics', inventoryId] as const,
    aisles: (inventoryId: string) => [...queryKeys.inventories.all, 'aisles', inventoryId] as const,
    positions: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'positions', aisleId] as const,
    positionDetail: (inventoryId: string, aisleId: string, positionId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'positions', aisleId, 'detail', positionId] as const,
    /** Execution log for a job (v3.1.1). */
    executionLog: (inventoryId: string, aisleId: string, jobId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'aisle', aisleId, 'jobs', jobId, 'execution-log'] as const,
    jobDetail: (inventoryId: string, aisleId: string, jobId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'jobs', jobId, 'detail'] as const,
    mergeResults: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'merge-results', aisleId] as const,
  },

  analytics: {
    all: ['v3', 'analytics'] as const,
    summary: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'summary', params] as const,
    trends: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'trends', params] as const,
    inventories: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'inventories', params] as const,
    aisles: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'aisles', params] as const,
    quality: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'quality', params] as const,
  },
} as const;
