/**
 * TanStack Query hooks for inventories (list and detail).
 */

import { useQuery } from '@tanstack/react-query';
import type { InventoriesListQuery } from '../api/client';
import { getInventories, getInventory } from '../api/client';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { queryKeys } from '../api/queryKeys';

/**
 * Paginated / sortable inventories table (GET /api/v3/inventories).
 * Pass `listQuery` for server-driven page, page_size, sort_by, sort_dir, search, status.
 */
export function useInventoriesList(listQuery?: InventoriesListQuery) {
  const q: InventoriesListQuery = {
    page: 1,
    page_size: DEFAULT_LIST_PAGE_SIZE,
    ...listQuery,
  };
  return useQuery({
    queryKey: [...queryKeys.inventories.list(), q] as const,
    queryFn: () => getInventories(q),
  });
}

export function useInventoryDetail(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.detail(inventoryId ?? ''),
    queryFn: () => getInventory(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}
