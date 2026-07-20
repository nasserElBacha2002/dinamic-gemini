import { useMutation, useQueryClient } from '@tanstack/react-query';
import { retryAssetPersistence } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';

export interface RetryPersistenceMutationInput {
  reason: string;
  expected_state_version: number;
  idempotencyKey: string;
}

export function useRetryAssetPersistence(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ idempotencyKey, ...body }: RetryPersistenceMutationInput) =>
      retryAssetPersistence(inventoryId, aisleId, jobId, assetId, body, {
        idempotencyKey,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.processingAssetDetail(inventoryId, aisleId, jobId, assetId),
      });
    },
  });
}
