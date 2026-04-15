import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getReviewQueuePositions, type ReviewQueueListQuery } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import {
  canonicalizeReviewQueueListQuery,
  reviewQueueListKeyPart,
} from '../api/queryParamCanonicalization';

export function useReviewQueue(listQuery: ReviewQueueListQuery, options?: { enabled?: boolean }) {
  const canonical = canonicalizeReviewQueueListQuery(listQuery);
  return useQuery({
    queryKey: queryKeys.reviewQueue.list(reviewQueueListKeyPart(canonical)),
    queryFn: () => getReviewQueuePositions(canonical),
    enabled: options?.enabled ?? true,
    placeholderData: keepPreviousData,
  });
}
