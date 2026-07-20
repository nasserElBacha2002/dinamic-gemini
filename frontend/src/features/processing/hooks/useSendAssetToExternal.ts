import { useMutation, useQueryClient } from '@tanstack/react-query';
import { sendAssetToExternal } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';

export interface SendExternalMutationInput {
  reason: string;
  expected_state_version: number;
  idempotencyKey: string;
}

export function useSendAssetToExternal(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ idempotencyKey, ...body }: SendExternalMutationInput) =>
      sendAssetToExternal(inventoryId, aisleId, jobId, assetId, body, {
        idempotencyKey,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.processingAssetDetail(inventoryId, aisleId, jobId, assetId),
      });
    },
  });
}
