/**
 * TanStack Query hooks for positions (list and detail).
 */

import { useQuery } from '@tanstack/react-query';
import {
  getAisleMergeResults,
  getAislePositions,
  getJobImageResults,
  getPositionDetail,
  type AislePositionsListQuery,
  type JobImageResultsQuery,
} from '../api/client';
import { queryKeys } from '../api/queryKeys';
import {
  canonicalizeAislePositionsListQuery,
  canonicalizeOptionalId,
  positionsListKeyPart,
} from '../api/queryParamCanonicalization';

/** Stable cache identity for positions list: job_id and pagination must not alias across runs. */
export function positionsListQueryKeyPart(q: AislePositionsListQuery | undefined): Record<string, string | number> {
  return positionsListKeyPart(q);
}

export function useAislePositions(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; listQuery?: AislePositionsListQuery }
) {
  const listQuery = options?.listQuery;
  const canonical = canonicalizeAislePositionsListQuery(listQuery);
  const listKey = positionsListKeyPart(canonical);
  return useQuery({
    queryKey: queryKeys.inventories.positionsList(inventoryId ?? '', aisleId ?? '', listKey),
    queryFn: () => getAislePositions(inventoryId!, aisleId!, canonical),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
  });
}

export function usePositionDetail(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  positionId: string | undefined,
  options?: { enabled?: boolean; jobId?: string | null; exactPosition?: boolean }
) {
  const jobId = canonicalizeOptionalId(options?.jobId);
  const exactPosition = options?.exactPosition ?? false;
  return useQuery({
    queryKey: queryKeys.inventories.positionDetailScoped(
      inventoryId ?? '',
      aisleId ?? '',
      positionId ?? '',
      jobId,
      exactPosition
    ),
    queryFn: () =>
      getPositionDetail(inventoryId!, aisleId!, positionId!, { jobId, exactPosition }),
    enabled: Boolean(inventoryId && aisleId && positionId) && (options?.enabled !== false),
  });
}

export function useAisleMergeResults(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  options?: { enabled?: boolean; jobId?: string | null }
) {
  const jobId = canonicalizeOptionalId(options?.jobId);
  return useQuery({
    queryKey: queryKeys.inventories.mergeResultsForJob(inventoryId ?? '', aisleId ?? '', jobId),
    queryFn: () => getAisleMergeResults(inventoryId!, aisleId!, { jobId }),
    enabled: Boolean(inventoryId && aisleId) && (options?.enabled !== false),
  });
}

/** Job image coverage (photos jobs): per-image rows with 0..n nested results + counters. */
export function useJobImageResults(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  query?: JobImageResultsQuery,
  options?: { enabled?: boolean }
) {
  const resultStatus = query?.result_status ?? 'all';
  const page = query?.page ?? 1;
  const pageSize = query?.page_size ?? 25;
  const paramsKey = { result_status: resultStatus, page, page_size: pageSize };
  return useQuery({
    queryKey: queryKeys.inventories.jobImageResults(
      inventoryId ?? '',
      aisleId ?? '',
      jobId ?? '',
      paramsKey
    ),
    queryFn: () =>
      getJobImageResults(inventoryId!, aisleId!, jobId!, {
        result_status: resultStatus,
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(inventoryId && aisleId && jobId) && (options?.enabled !== false),
  });
}
