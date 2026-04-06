/**
 * TanStack Query hooks for positions (list and detail).
 */

import { useQuery } from '@tanstack/react-query';
import {
  getAisleMergeResults,
  getAislePositions,
  getPositionDetail,
  type AislePositionsListQuery,
} from '../api/client';
import { queryKeys } from '../api/queryKeys';

export function useAislePositions(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; listQuery?: AislePositionsListQuery }
) {
  const listQuery = options?.listQuery;
  return useQuery({
    queryKey: [...queryKeys.inventories.positions(inventoryId ?? '', aisleId ?? ''), listQuery ?? {}] as const,
    queryFn: () => getAislePositions(inventoryId!, aisleId!, listQuery),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
  });
}

export function usePositionDetail(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  positionId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.positionDetail(inventoryId ?? '', aisleId ?? '', positionId ?? ''),
    queryFn: () => getPositionDetail(inventoryId!, aisleId!, positionId!),
    enabled: Boolean(inventoryId && aisleId && positionId) && (options?.enabled !== false),
  });
}

export function useAisleMergeResults(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; jobId?: string | null }
) {
  const jobId = options?.jobId;
  return useQuery({
    queryKey: [...queryKeys.inventories.mergeResults(inventoryId ?? '', aisleId ?? ''), jobId ?? null] as const,
    queryFn: () => getAisleMergeResults(inventoryId!, aisleId!, { jobId }),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
  });
}
