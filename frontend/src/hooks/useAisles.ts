/**
 * TanStack Query hooks for inventory metrics and aisles.
 */

import { useQuery } from '@tanstack/react-query';
import { getAisles, getInventoryMetrics, getExecutionLog, type AislesListQuery } from '../api/client';
import { queryKeys } from '../api/queryKeys';

export function useInventoryMetrics(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.metrics(inventoryId ?? ''),
    queryFn: () => getInventoryMetrics(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}

const defaultAisleTableQuery: AislesListQuery = { page: 1, page_size: 200 };

export function useAislesList(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...queryKeys.inventories.aisles(inventoryId ?? ''), defaultAisleTableQuery] as const,
    queryFn: () => getAisles(inventoryId!, defaultAisleTableQuery),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
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
