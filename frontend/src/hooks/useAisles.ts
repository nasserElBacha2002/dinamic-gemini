/**
 * TanStack Query hooks for inventory metrics and aisles.
 */

import { useMemo } from 'react';
import { useQuery, useQueries } from '@tanstack/react-query';
import { getAisles, getAisleAssets, getInventoryMetrics, getExecutionLog } from '../api/client';
import { queryKeys } from '../api/queryKeys';

export function useInventoryMetrics(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.metrics(inventoryId ?? ''),
    queryFn: () => getInventoryMetrics(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}

export function useAislesList(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.aisles(inventoryId ?? ''),
    queryFn: () => getAisles(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}

/** Fetches asset count per aisle; returns a map aisleId -> count. Aisle IDs are deduped to avoid duplicate queries. */
export function useAisleAssetCounts(inventoryId: string | undefined, aisleIds: string[], options?: { enabled?: boolean }) {
  const stableAisleIds = useMemo(() => [...new Set(aisleIds)], [aisleIds.join(',')]);
  const enabled = Boolean(inventoryId) && stableAisleIds.length > 0 && (options?.enabled !== false);
  const queries = useQueries({
    queries: stableAisleIds.map((aisleId) => ({
      queryKey: queryKeys.inventories.aisleAssets(inventoryId ?? '', aisleId),
      queryFn: () => getAisleAssets(inventoryId!, aisleId),
      enabled,
    })),
  });
  const isLoading = queries.some((q) => q.isLoading);
  const error = queries.find((q) => q.error)?.error;
  const data: Record<string, number> = {};
  if (enabled && inventoryId) {
    queries.forEach((q, i) => {
      if (stableAisleIds[i] && q.data) {
        data[stableAisleIds[i]] = Array.isArray(q.data) ? q.data.length : 0;
      }
    });
  }
  return {
    data,
    isLoading,
    error,
    isError: queries.some((q) => q.isError),
    refetch: async () => {
      await Promise.all(queries.map((q) => q.refetch()));
    },
  };
}

/** Execution log for a job (v3.1.1). Enable when jobId is present to support "View log" on demand.
 * refetchInterval: when dialog is open, use 4s so operators see log growth for running jobs. */
export function useExecutionLog(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  options?: { enabled?: boolean; refetchInterval?: number | false }
) {
  return useQuery({
    queryKey: queryKeys.inventories.executionLog(
      inventoryId ?? '',
      aisleId ?? '',
      jobId ?? ''
    ),
    queryFn: () => getExecutionLog(inventoryId!, aisleId!, jobId!),
    enabled:
      Boolean(inventoryId && aisleId && jobId) && (options?.enabled !== false),
    refetchInterval: options?.refetchInterval,
  });
}
