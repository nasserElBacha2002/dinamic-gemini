import { useQuery } from '@tanstack/react-query';
import { getProcessingAssets } from '../../../api/processingApi';
import { queryKeys } from '../../../api/queryKeys';
import type { ProcessingUrlFilters } from '../utils/processingUrlFilters';
import { processingFiltersToApiQuery } from '../utils/processingUrlFilters';

export function useProcessingAssets(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  jobId: string | undefined,
  filters: ProcessingUrlFilters,
  options?: { enabled?: boolean; pageSize?: number }
) {
  const apiQuery = processingFiltersToApiQuery(filters);
  const pageSize = options?.pageSize ?? apiQuery.page_size;
  const paramsKey = {
    status: apiQuery.status ?? '',
    strategy: apiQuery.strategy ?? '',
    resolved_by: apiQuery.resolved_by ?? '',
    search: apiQuery.search ?? '',
    page: apiQuery.page,
    page_size: pageSize,
    has_warnings: apiQuery.has_warnings ?? '',
    has_fallback: apiQuery.has_fallback ?? '',
  };

  return useQuery({
    queryKey: queryKeys.inventories.processingAssets(
      inventoryId ?? '',
      aisleId ?? '',
      jobId ?? '',
      paramsKey
    ),
    queryFn: () =>
      getProcessingAssets(inventoryId!, aisleId!, jobId!, {
        ...apiQuery,
        page_size: pageSize,
      }),
    enabled: Boolean(inventoryId && aisleId && jobId) && (options?.enabled !== false),
  });
}
