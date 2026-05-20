import { useMutation, useQueryClient } from '@tanstack/react-query';
import { runAisleCodeScan } from '../../../api/codeScansApi';
import { queryKeys } from '../../../api/queryKeys';

export function useRunAisleCodeScan(
  inventoryId: string,
  aisleId: string,
  jobId?: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => runAisleCodeScan(inventoryId, aisleId, { jobId }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleCodeScans(inventoryId, aisleId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleCodeScanSummary(inventoryId, aisleId),
      });
    },
  });
}
