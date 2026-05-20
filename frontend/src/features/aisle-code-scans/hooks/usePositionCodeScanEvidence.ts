import { useQuery } from '@tanstack/react-query';
import { getPositionCodeScanEvidence } from '../../../api/codeScansApi';
import { queryKeys } from '../../../api/queryKeys';

export function usePositionCodeScanEvidence(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  options?: { enabled?: boolean }
) {
  const enabled =
    (options?.enabled ?? true) &&
    Boolean(inventoryId?.trim() && aisleId?.trim() && positionId?.trim());

  return useQuery({
    queryKey: queryKeys.inventories.positionCodeScanEvidence(
      inventoryId,
      aisleId,
      positionId
    ),
    queryFn: () => getPositionCodeScanEvidence(inventoryId, aisleId, positionId),
    enabled,
  });
}
