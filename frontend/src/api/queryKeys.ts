/**
 * TanStack Query key factory for v3 API.
 * Keys are deterministic and domain-oriented for precise invalidation.
 */

export const queryKeys = {
  all: ['v3'] as const,

  inventories: {
    all: ['v3', 'inventories'] as const,
    list: () => [...queryKeys.inventories.all, 'list'] as const,
    listWithParams: (params: Record<string, string | number>) =>
      [...queryKeys.inventories.list(), params] as const,
    detail: (inventoryId: string) => [...queryKeys.inventories.all, 'detail', inventoryId] as const,
    /** Selectable pipeline providers for POST aisle process (Phase 5). */
    processingProviderOptions: () => [...queryKeys.inventories.all, 'processing-provider-options'] as const,
    visualReferences: (inventoryId: string) =>
      [...queryKeys.inventories.all, 'visual-references', inventoryId] as const,
    metrics: (inventoryId: string) => [...queryKeys.inventories.all, 'metrics', inventoryId] as const,
    aisles: (inventoryId: string) => [...queryKeys.inventories.all, 'aisles', inventoryId] as const,
    positions: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'positions', aisleId] as const,
    positionsList: (inventoryId: string, aisleId: string, params: Record<string, string | number>) =>
      [...queryKeys.inventories.positions(inventoryId, aisleId), params] as const,
    positionDetail: (inventoryId: string, aisleId: string, positionId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'positions', aisleId, 'detail', positionId] as const,
    positionDetailScoped: (
      inventoryId: string,
      aisleId: string,
      positionId: string,
      jobId: string | null,
      exactPosition: boolean
    ) => [...queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId), jobId, exactPosition ? 1 : 0] as const,
    /** Execution log for a job (v3.1.1). */
    executionLog: (inventoryId: string, aisleId: string, jobId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'aisle', aisleId, 'jobs', jobId, 'execution-log'] as const,
    aisleExecutionLog: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'aisle', aisleId, 'aisle-execution-log'] as const,
    jobDetail: (inventoryId: string, aisleId: string, jobId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, aisleId, 'jobs', jobId, 'detail'] as const,
    mergeResults: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'merge-results', aisleId] as const,
    mergeResultsForJob: (inventoryId: string, aisleId: string, jobId: string | null) =>
      [...queryKeys.inventories.mergeResults(inventoryId, aisleId), jobId] as const,
    /** GET .../aisles/{aisle}/jobs (run list for selector). */
    aisleJobs: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'aisle-jobs', aisleId] as const,
    /** Phase 6 — explicit two-run compare (benchmark analytics payload). */
    benchmarkCompare: (inventoryId: string, aisleId: string, jobAId: string, jobBId: string) =>
      [...queryKeys.inventories.all, 'benchmark-compare', inventoryId, aisleId, jobAId, jobBId] as const,
  },

  reviewQueue: {
    // Keep root compatible with existing invalidation prefixes.
    all: ['reviewQueue'] as const,
    list: (params: Record<string, string | number>) => [...queryKeys.reviewQueue.all, 'list', params] as const,
  },

  admin: {
    all: ['v3', 'admin'] as const,
    aiConfig: () => [...queryKeys.admin.all, 'ai-config'] as const,
    aiComposedPrompt: (providerKey: string, promptKey: string, parity: boolean) =>
      [...queryKeys.admin.all, 'ai-config', 'composed-prompt', providerKey, promptKey, parity] as const,
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
    manualInterventions: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'manual-interventions', params] as const,
  },
} as const;
