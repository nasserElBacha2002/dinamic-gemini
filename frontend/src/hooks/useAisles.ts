/**
 * TanStack Query hooks for inventory metrics and aisles.
 *
 * **Query keys (Phase 2 / 7):** `useAislesList` uses `queryKeys.inventories.aislesListTable` and
 * `useAisleJobsList` uses `queryKeys.inventories.aisleJobsList` — same shapes Phase 6 patch helpers expect.
 * Analytics and other domains use their own `queryKeys` trees; they are not required to share list canonicalizers.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getAisles,
  getInventoryMetrics,
  getExecutionLog,
  getAisleExecutionLog,
  getAisleJobDetail,
  getProcessingProviderOptions,
  listAisleJobs,
  listAisleAssets,
  getAisleBenchmarkCompare,
  type AislesListQuery,
} from '../api/client';
import { queryKeys, DEFAULT_AISLES_LIST_TABLE_QUERY } from '../api/queryKeys';

export function useInventoryMetrics(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.metrics(inventoryId ?? ''),
    queryFn: () => getInventoryMetrics(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}

/** Large page: detail view table is not yet on `DataTable` pagination; fetch one chunk per inventory. */
const aislesListTableQuery: AislesListQuery = { ...DEFAULT_AISLES_LIST_TABLE_QUERY };

export function useAislesList(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.aislesListTable(inventoryId ?? ''),
    queryFn: () => getAisles(inventoryId!, aislesListTableQuery),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}

/** Pipeline provider keys for POST aisle process (Phase 5). */
export function useProcessingProviderOptions(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.processingProviderOptions(),
    queryFn: () => getProcessingProviderOptions(),
    enabled: options?.enabled !== false,
    staleTime: 60_000,
  });
}

/** Execution log for a job (v3.1.1). Enable when jobId is present to support "View log" on demand.
 * refetchInterval: when dialog is open, use 4s so operators see log growth for running jobs. */
export function useExecutionLog(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  options?: { enabled?: boolean }
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
    refetchOnWindowFocus: false,
  });
}

/** Aggregated execution log for an aisle (all jobs). Enable when dialog is open. */
export function useAisleExecutionLog(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.aisleExecutionLog(inventoryId ?? '', aisleId ?? ''),
    queryFn: () => getAisleExecutionLog(inventoryId!, aisleId!),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
    refetchOnWindowFocus: false,
  });
}

export function useAisleJobDetail(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.jobDetail(inventoryId ?? '', aisleId ?? '', jobId ?? ''),
    queryFn: () => getAisleJobDetail(inventoryId!, aisleId!, jobId!),
    enabled: Boolean(inventoryId && aisleId && jobId) && (options?.enabled !== false),
    refetchOnWindowFocus: false,
  });
}

/** Jobs for an aisle, newest first — run selector on Aisle Results (Phase 3). */
export function useAisleJobsList(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; limit?: number }
) {
  const limit = options?.limit ?? 50;
  return useQuery({
    queryKey: queryKeys.inventories.aisleJobsList(inventoryId ?? '', aisleId ?? '', limit),
    queryFn: () => listAisleJobs(inventoryId!, aisleId!, { limit }),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
    refetchOnWindowFocus: false,
  });
}

/** Phase 6 — benchmark compare for explicit job pair (read-only analytics payload). */
/** Uploaded source assets (photos/videos) for one aisle — lazy until drawer opens. */
export function useAisleSourceAssets(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.aisleSourceAssets(inventoryId ?? '', aisleId ?? ''),
    queryFn: () => listAisleAssets(inventoryId!, aisleId!),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
    refetchOnWindowFocus: false,
  });
}

export function useAisleBenchmarkCompare(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobAId: string | undefined,
  jobBId: string | undefined,
  options?: { enabled?: boolean }
) {
  const inv = (inventoryId ?? '').trim();
  const aisle = (aisleId ?? '').trim();
  const a = jobAId?.trim() ?? '';
  const b = jobBId?.trim() ?? '';
  const paramsReady = Boolean(inv && aisle && a && b && a !== b);
  return useQuery({
    queryKey: queryKeys.inventories.benchmarkCompare(inv, aisle, a, b),
    queryFn: () => getAisleBenchmarkCompare(inv, aisle, a, b),
    enabled: paramsReady && (options?.enabled !== false),
    refetchOnWindowFocus: false,
  });
}
