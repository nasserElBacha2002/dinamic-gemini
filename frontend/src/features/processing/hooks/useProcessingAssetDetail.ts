import { useQuery } from '@tanstack/react-query';
import { getProcessingAssetDetail } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';

export function useProcessingAssetDetail(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  assetId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.inventories.processingAssetDetail(
      inventoryId ?? '',
      aisleId ?? '',
      jobId ?? '',
      assetId ?? ''
    ),
    queryFn: () => getProcessingAssetDetail(inventoryId!, aisleId!, jobId!, assetId!),
    enabled: Boolean(inventoryId && aisleId && jobId && assetId) && (options?.enabled !== false),
  });
}
