/**
 * TanStack Query hooks for inventories (list and detail).
 */

import { useQuery } from '@tanstack/react-query';
import type { InventoriesListQuery } from '../api/client';
import { getInventories, getInventory, getInventoryVisualReferences } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { canonicalizeInventoriesListQuery, inventoriesListKeyPart } from '../api/queryParamCanonicalization';

/**
 * Paginated / sortable inventories table (GET /api/v3/inventories).
 * Pass `listQuery` for server-driven page, page_size, sort_by, sort_dir, search, status.
 */
export function useInventoriesList(listQuery?: InventoriesListQuery) {
  const q = canonicalizeInventoriesListQuery(listQuery);
  return useQuery({
    queryKey: queryKeys.inventories.listWithParams(inventoriesListKeyPart(q)),
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

export function useInventoryVisualReferences(
  inventoryId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.visualReferences(inventoryId ?? ''),
    queryFn: () => getInventoryVisualReferences(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}
