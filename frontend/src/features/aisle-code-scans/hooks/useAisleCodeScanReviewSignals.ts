import { useQuery } from '@tanstack/react-query';
import { getAisleCodeScanReviewSignals } from '../../../api/codeScansApi';
import { queryKeys } from '../../../api/queryKeys';

export function useAisleCodeScanReviewSignals(
  inventoryId: string,
  aisleId: string,
  options?: { enabled?: boolean }
) {
  const enabled =
    (options?.enabled ?? true) && Boolean(inventoryId?.trim() && aisleId?.trim());

  return useQuery({
    queryKey: queryKeys.inventories.aisleCodeScanReviewSignals(inventoryId, aisleId),
    queryFn: () => getAisleCodeScanReviewSignals(inventoryId, aisleId),
    enabled,
  });
}
