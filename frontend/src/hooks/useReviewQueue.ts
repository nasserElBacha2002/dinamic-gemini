import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getReviewQueuePositions, type ReviewQueueListQuery } from '../api/client';

export function useReviewQueue(listQuery: ReviewQueueListQuery, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['reviewQueue', listQuery] as const,
    queryFn: () => getReviewQueuePositions(listQuery),
    enabled: options?.enabled ?? true,
    placeholderData: keepPreviousData,
  });
}
