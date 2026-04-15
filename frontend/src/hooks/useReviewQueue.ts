import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getReviewQueuePositions, type ReviewQueueListQuery } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { reviewQueueListKeyPart } from '../api/queryParamCanonicalization';

export function useReviewQueue(listQuery: ReviewQueueListQuery, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.reviewQueue.list(reviewQueueListKeyPart(listQuery)),
    queryFn: () => getReviewQueuePositions(listQuery),
    enabled: options?.enabled ?? true,
    placeholderData: keepPreviousData,
  });
}
