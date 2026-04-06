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

/** Stable cache identity for positions list: job_id and pagination must not alias across runs. */
export function positionsListQueryKeyPart(q: AislePositionsListQuery | undefined): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (!q) return out;
  if (q.page != null) out.page = q.page;
  if (q.page_size != null) out.page_size = q.page_size;
  if (q.job_id != null && String(q.job_id).trim() !== '') {
    out.job_id = String(q.job_id).trim();
  }
  if (q.status != null && String(q.status).trim() !== '') out.status = String(q.status).trim();
  if (q.needs_review != null) out.needs_review = q.needs_review ? 1 : 0;
  if (q.min_confidence != null && !Number.isNaN(q.min_confidence)) out.min_confidence = q.min_confidence;
  if (q.sku_filter != null && String(q.sku_filter).trim() !== '') out.sku_filter = String(q.sku_filter).trim();
  if (q.sort_by != null && String(q.sort_by).trim() !== '') out.sort_by = String(q.sort_by).trim();
  if (q.sort_dir != null && String(q.sort_dir).trim() !== '') out.sort_dir = String(q.sort_dir).trim();
  return out;
}

export function useAislePositions(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; listQuery?: AislePositionsListQuery }
) {
  const listQuery = options?.listQuery;
  const listKey = positionsListQueryKeyPart(listQuery);
  return useQuery({
    queryKey: [...queryKeys.inventories.positions(inventoryId ?? '', aisleId ?? ''), listKey] as const,
    queryFn: () => getAislePositions(inventoryId!, aisleId!, listQuery),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
  });
}

export function usePositionDetail(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  positionId: string | undefined,
  options?: { enabled?: boolean; jobId?: string | null }
) {
  const jobId = options?.jobId;
  return useQuery({
    queryKey: [
      ...queryKeys.inventories.positionDetail(inventoryId ?? '', aisleId ?? '', positionId ?? ''),
      jobId ?? null,
    ] as const,
    queryFn: () => getPositionDetail(inventoryId!, aisleId!, positionId!, { jobId }),
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
