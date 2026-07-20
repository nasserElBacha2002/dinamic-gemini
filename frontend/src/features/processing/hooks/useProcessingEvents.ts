import { useQuery } from '@tanstack/react-query';
import { getProcessingEvents } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';

export function useProcessingEvents(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  assetId: string | undefined,
  query?: { page?: number; page_size?: number },
  options?: { enabled?: boolean }
) {
  const page = query?.page ?? 1;
  const pageSize = query?.page_size ?? 50;
  const paramsKey = { page, page_size: pageSize };

  return useQuery({
    queryKey: queryKeys.inventories.processingEvents(
      inventoryId ?? '',
      aisleId ?? '',
      jobId ?? '',
      assetId ?? '',
      paramsKey
    ),
    queryFn: () =>
      getProcessingEvents(inventoryId!, aisleId!, jobId!, assetId!, {
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(inventoryId && aisleId && jobId && assetId) && (options?.enabled !== false),
  });
}
