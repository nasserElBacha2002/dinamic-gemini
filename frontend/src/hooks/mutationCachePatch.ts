import type { QueryClient, QueryKey } from '@tanstack/react-query';
import type { Aisle, AisleJobsListResponse } from '../api/types';
import { queryKeys, DEFAULT_AISLES_LIST_TABLE_QUERY } from '../api/queryKeys';
import { recordNonReviewPatchObs } from '../dev/cacheMutationObservability';

type AislesListLike = {
  items: Aisle[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

function isDefaultAislesListQueryKey(queryKey: QueryKey, inventoryId: string): boolean {
  if (!Array.isArray(queryKey) || queryKey.length < 5) return false;
  const prefix = queryKeys.inventories.aisles(inventoryId);
  if (queryKey[0] !== prefix[0] || queryKey[1] !== prefix[1] || queryKey[2] !== prefix[2]) return false;
  if (queryKey[3] !== prefix[3]) return false;
  const params = queryKey[4];
  if (!params || typeof params !== 'object') return false;
  const page = (params as { page?: unknown }).page;
  const pageSize = (params as { page_size?: unknown }).page_size;
  const keys = Object.keys(params as object);
  return (
    keys.length === 2 &&
    page === DEFAULT_AISLES_LIST_TABLE_QUERY.page &&
    pageSize === DEFAULT_AISLES_LIST_TABLE_QUERY.page_size
  );
}

/**
 * Conservative Phase 6 patch: add the created aisle to the default inventory-detail aisle list only.
 * We skip filtered/paginated variants to avoid inventing membership/sort semantics.
 */
export function patchCreateAisleIntoAislesLists(
  queryClient: QueryClient,
  inventoryId: string,
  createdAisle: Aisle
): boolean {
  const queries = queryClient.getQueryCache().findAll({
    queryKey: queryKeys.inventories.aisles(inventoryId),
  });

  let patched = false;
  for (const query of queries) {
    const key = query.queryKey;
    if (!isDefaultAislesListQueryKey(key, inventoryId)) continue;
    const old = query.state.data as AislesListLike | undefined;
    if (!old || !Array.isArray(old.items)) continue;
    if (old.items.some((a) => a.id === createdAisle.id)) continue;

    // Best-effort local insertion for default 200-row table: if page is full, keep server as source of truth.
    if (typeof old.page_size === 'number' && old.page_size > 0 && old.items.length >= old.page_size) continue;

    const items = [createdAisle, ...old.items];
    const totalItems = Math.max(items.length, old.total_items + 1);
    const totalPages =
      typeof old.page_size === 'number' && old.page_size > 0
        ? Math.max(1, Math.ceil(totalItems / old.page_size))
        : old.total_pages;

    queryClient.setQueryData<AislesListLike>(key, {
      ...old,
      items,
      total_items: totalItems,
      total_pages: totalPages,
    });
    patched = true;
  }

  recordNonReviewPatchObs({
    flow: 'create_aisle',
    inventoryId,
    patched,
    note: patched ? 'default_aisles_table_row_inserted' : 'skipped_no_eligible_cache_or_full_page',
  });
  return patched;
}

/**
 * Replace one aisle row in the default inventory-detail aisles list cache (code / is_active updates).
 */
export function patchAisleInAislesLists(
  queryClient: QueryClient,
  inventoryId: string,
  updatedAisle: Aisle
): boolean {
  const queries = queryClient.getQueryCache().findAll({
    queryKey: queryKeys.inventories.aisles(inventoryId),
  });

  let patched = false;
  for (const query of queries) {
    const key = query.queryKey;
    if (!isDefaultAislesListQueryKey(key, inventoryId)) continue;
    const old = query.state.data as AislesListLike | undefined;
    if (!old || !Array.isArray(old.items)) continue;
    const idx = old.items.findIndex((a) => a.id === updatedAisle.id);
    if (idx < 0) continue;

    const items = [...old.items];
    items[idx] = { ...items[idx], ...updatedAisle };
    queryClient.setQueryData<AislesListLike>(key, {
      ...old,
      items,
    });
    patched = true;
  }

  recordNonReviewPatchObs({
    flow: 'update_aisle',
    inventoryId,
    aisleId: updatedAisle.id,
    patched,
    note: patched ? 'default_aisles_table_row_replaced' : 'skipped_no_eligible_cache',
  });
  return patched;
}

/**
 * Conservative Phase 6 patch: update only operational pointer metadata on cached aisle jobs lists.
 * Job status, timing, and other run fields remain server-authoritative.
 */
export function patchPromoteOperationalJobInAisleJobs(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  operationalJobId: string
): boolean {
  let patched = false;
  queryClient.setQueriesData<AisleJobsListResponse>(
    { queryKey: queryKeys.inventories.aisleJobs(inventoryId, aisleId) },
    (old) => {
      if (!old || !Array.isArray(old.jobs)) return old;
      let changed = old.operational_job_id !== operationalJobId;
      const jobs = old.jobs.map((job) => {
        const nextOperational = job.id === operationalJobId;
        if ((job.is_operational ?? false) !== nextOperational) {
          changed = true;
        }
        return {
          ...job,
          is_operational: nextOperational,
        };
      });
      if (!changed) return old;
      patched = true;
      return {
        ...old,
        operational_job_id: operationalJobId,
        jobs,
      };
    }
  );
  recordNonReviewPatchObs({
    flow: 'promote_operational_job',
    inventoryId,
    aisleId,
    patched,
    note: patched ? 'aisle_jobs_operational_flags_updated' : 'no_jobs_list_cache_or_no_change',
  });
  return patched;
}
