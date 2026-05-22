import { useQuery } from '@tanstack/react-query';
import { getAisleCodeScanSummary, listAisleCodeScans } from '../../../api/codeScansApi';
import { queryKeys } from '../../../api/queryKeys';

export function useAisleCodeScans(
  inventoryId: string,
  aisleId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.aisleCodeScans(inventoryId, aisleId),
    queryFn: () => listAisleCodeScans(inventoryId, aisleId),
    enabled: Boolean(inventoryId && aisleId && (options?.enabled !== false)),
    refetchOnWindowFocus: false,
  });
}

export function useAisleCodeScanSummary(
  inventoryId: string,
  aisleId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.aisleCodeScanSummary(inventoryId, aisleId),
    queryFn: () => getAisleCodeScanSummary(inventoryId, aisleId),
    enabled: Boolean(inventoryId && aisleId && (options?.enabled !== false)),
    refetchOnWindowFocus: false,
  });
}
