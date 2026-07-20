/**
 * TanStack Query key factory for v3 API.
 * Keys are deterministic and domain-oriented for precise invalidation.
 */

/** Default aisles table chunk on inventory detail — shared by `useAislesList` and Phase 6 aisle-list patches. */
export const DEFAULT_AISLES_LIST_TABLE_QUERY = { page: 1, page_size: 200 } as const;

export const queryKeys = {
  all: ['v3'] as const,

  captureSessions: {
    all: ['v3', 'capture-sessions'] as const,
    list: (inventoryId: string, params: Record<string, string | number>) =>
      [...queryKeys.captureSessions.all, 'list', inventoryId, params] as const,
    detail: (inventoryId: string, sessionId: string) =>
      [...queryKeys.captureSessions.all, 'detail', inventoryId, sessionId] as const,
    items: (inventoryId: string, sessionId: string) =>
      [...queryKeys.captureSessions.detail(inventoryId, sessionId), 'items'] as const,
    groups: (inventoryId: string, sessionId: string) =>
      [...queryKeys.captureSessions.detail(inventoryId, sessionId), 'groups'] as const,
  },

  inventories: {
    all: ['v3', 'inventories'] as const,
    list: () => [...queryKeys.inventories.all, 'list'] as const,
    listWithParams: (params: Record<string, string | number>) =>
      [...queryKeys.inventories.list(), params] as const,
    detail: (inventoryId: string) => [...queryKeys.inventories.all, 'detail', inventoryId] as const,
    /** Selectable pipeline providers for POST aisle process (Phase 5). */
    processingProviderOptions: (mode: 'test' | 'production' = 'test') =>
      [...queryKeys.inventories.all, 'processing-provider-options', mode] as const,
    metrics: (inventoryId: string) => [...queryKeys.inventories.all, 'metrics', inventoryId] as const,
    aisles: (inventoryId: string) => [...queryKeys.inventories.all, 'aisles', inventoryId] as const,
    /** Inventory-detail default aisles table (single fixed page; see `useAislesList`). */
    aislesListTable: (inventoryId: string) =>
      [...queryKeys.inventories.aisles(inventoryId), DEFAULT_AISLES_LIST_TABLE_QUERY] as const,
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
    /** GET .../jobs/{jobId}/auditability (Phase H). */
    jobAuditability: (inventoryId: string, aisleId: string, jobId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'aisle', aisleId, 'jobs', jobId, 'auditability'] as const,
    mergeResults: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'merge-results', aisleId] as const,
    mergeResultsForJob: (inventoryId: string, aisleId: string, jobId: string | null) =>
      [...queryKeys.inventories.mergeResults(inventoryId, aisleId), jobId] as const,
    /** GET .../aisles/{aisle}/jobs (run list for selector). */
    aisleJobs: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'aisle-jobs', aisleId] as const,
    /** Source assets (uploaded photos/videos) for one aisle. */
    aisleSourceAssets: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'source-assets', aisleId] as const,
    aisleCodeScans: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'code-scans', aisleId] as const,
    aisleCodeScanSummary: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'code-scans', aisleId, 'summary'] as const,
    aisleCodeScanReviewSignals: (inventoryId: string, aisleId: string) =>
      [...queryKeys.inventories.all, 'aisles', inventoryId, 'code-scans', aisleId, 'review-signals'] as const,
    positionCodeScanEvidence: (inventoryId: string, aisleId: string, positionId: string) =>
      [
        ...queryKeys.inventories.all,
        'aisles',
        inventoryId,
        'positions',
        positionId,
        'code-scan-evidence',
        aisleId,
      ] as const,
    /** Run selector list (`listAisleJobs`); `limit` is part of cache identity. */
    aisleJobsList: (inventoryId: string, aisleId: string, limit: number) =>
      [...queryKeys.inventories.aisleJobs(inventoryId, aisleId), limit] as const,
    /** GET .../jobs/{jobId}/image-results (photo coverage view); params (result_status/page/page_size) are part of cache identity. */
    jobImageResults: (
      inventoryId: string,
      aisleId: string,
      jobId: string,
      params: Record<string, string | number>
    ) =>
      [
        ...queryKeys.inventories.all,
        'aisles',
        inventoryId,
        aisleId,
        'jobs',
        jobId,
        'image-results',
        params,
      ] as const,
    benchmarkCompareMany: (
      inventoryId: string,
      aisleId: string,
      baselineJobId: string,
      jobIdsOrdered: readonly string[],
      includeDiffRows: boolean,
      maxDiffRows?: number
    ) =>
      [
        ...queryKeys.inventories.all,
        'benchmark-compare-many',
        inventoryId,
        aisleId,
        baselineJobId,
        [...jobIdsOrdered],
        includeDiffRows ? 1 : 0,
        maxDiffRows ?? null,
      ] as const,
    /** Invalidate all benchmark-compare queries for one inventory (narrower than full `benchmark-compare` prefix). */
    benchmarkCompareInventory: (inventoryId: string) =>
      [...queryKeys.inventories.all, 'benchmark-compare', inventoryId] as const,
  },

  clients: {
    all: ['v3', 'clients'] as const,
    list: (params: Record<string, string | number>) =>
      [...queryKeys.clients.all, 'list', params] as const,
    detail: (clientId: string) => [...queryKeys.clients.all, 'detail', clientId] as const,
    suppliers: {
      all: (clientId: string) => [...queryKeys.clients.all, 'suppliers', clientId] as const,
      list: (clientId: string, params: Record<string, string | number>) =>
        [...queryKeys.clients.suppliers.all(clientId), 'list', params] as const,
      detail: (clientId: string, supplierId: string) =>
        [...queryKeys.clients.suppliers.all(clientId), 'detail', supplierId] as const,
      referenceImages: (clientId: string, supplierId: string) =>
        [...queryKeys.clients.suppliers.all(clientId), 'reference-images', supplierId] as const,
      promptConfigs: {
        all: (clientId: string, supplierId: string) =>
          [...queryKeys.clients.suppliers.all(clientId), 'prompt-configs', supplierId] as const,
        scope: (
          clientId: string,
          supplierId: string,
          scopeType: 'all_providers_models' | 'provider' | 'provider_model',
          providerName: string | null,
          modelName: string | null
        ) =>
          [
            ...queryKeys.clients.suppliers.promptConfigs.all(clientId, supplierId),
            'scope',
            scopeType,
            providerName ?? '__all_providers__',
            modelName ?? '__default__',
          ] as const,
        listByScope: (
          clientId: string,
          supplierId: string,
          scopeType: 'all_providers_models' | 'provider' | 'provider_model',
          providerName: string | null,
          modelName: string | null
        ) => [...queryKeys.clients.suppliers.promptConfigs.scope(clientId, supplierId, scopeType, providerName, modelName), 'list'] as const,
        activeByScope: (
          clientId: string,
          supplierId: string,
          scopeType: 'all_providers_models' | 'provider' | 'provider_model',
          providerName: string | null,
          modelName: string | null
        ) =>
          [
            ...queryKeys.clients.suppliers.promptConfigs.scope(
              clientId,
              supplierId,
              scopeType,
              providerName,
              modelName
            ),
            'active',
          ] as const,
      },
      extractionProfiles: {
        all: (clientId: string, supplierId: string) =>
          [...queryKeys.clients.suppliers.all(clientId), 'extraction-profiles', supplierId] as const,
        list: (clientId: string, supplierId: string) =>
          [...queryKeys.clients.suppliers.extractionProfiles.all(clientId, supplierId), 'list'] as const,
        active: (clientId: string, supplierId: string) =>
          [...queryKeys.clients.suppliers.extractionProfiles.all(clientId, supplierId), 'active'] as const,
        annotations: (clientId: string, supplierId: string, imageId: string) =>
          [
            ...queryKeys.clients.suppliers.extractionProfiles.all(clientId, supplierId),
            'annotations',
            imageId,
          ] as const,
      },
    },
  },

  observability: {
    all: ['v3', 'observability'] as const,
    metrics: (params: Record<string, string | undefined>) =>
      [...queryKeys.observability.all, 'metrics', params] as const,
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
    costSummary: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'cost-summary', params] as const,
    manualInterventions: (params: Record<string, string | undefined>) =>
      [...queryKeys.analytics.all, 'manual-interventions', params] as const,
  },
} as const;
