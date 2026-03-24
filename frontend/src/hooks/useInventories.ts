/**
 * TanStack Query hooks for inventories (list and detail).
 */

import { useQuery } from '@tanstack/react-query';
import { getInventories, getInventory } from '../api/client';
import { queryKeys } from '../api/queryKeys';

/** List query returns screen-ready rows (InventoryListItem), not thin Inventory. */
export function useInventoriesList() {
  return useQuery({
    queryKey: queryKeys.inventories.list(),
    queryFn: getInventories,
  });
}

export function useInventoryDetail(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.detail(inventoryId ?? ''),
    queryFn: () => getInventory(inventoryId!),
    enabled: Boolean(inventoryId) && (options?.enabled !== false),
  });
}
