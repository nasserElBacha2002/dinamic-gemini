import { useMutation, useQueryClient } from '@tanstack/react-query';
import { reprocessAsset } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';
import type { ReprocessAssetRequest } from '../../../api/types/processing';

export function useReprocessAsset(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ReprocessAssetRequest) =>
      reprocessAsset(inventoryId, aisleId, jobId, assetId, body, {
        idempotencyKey:
          typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : `reprocess-${Date.now()}`,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.processingAssetDetail(inventoryId, aisleId, jobId, assetId),
      });
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) &&
          query.queryKey.includes('processing-assets') &&
          query.queryKey.includes(inventoryId) &&
          query.queryKey.includes(aisleId) &&
          query.queryKey.includes(jobId),
      });
    },
  });
}
