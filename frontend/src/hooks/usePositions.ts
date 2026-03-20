/**
 * TanStack Query hooks for positions (list and detail).
 */

import { useQuery } from '@tanstack/react-query';
import { getAisleMergeResults, getAislePositions, getPositionDetail } from '../api/client';
import { queryKeys } from '../api/queryKeys';

export function useAislePositions(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.positions(inventoryId ?? '', aisleId ?? ''),
    queryFn: () => getAislePositions(inventoryId!, aisleId!),
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
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.mergeResults(inventoryId ?? '', aisleId ?? ''),
    queryFn: () => getAisleMergeResults(inventoryId!, aisleId!),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
  });
}
