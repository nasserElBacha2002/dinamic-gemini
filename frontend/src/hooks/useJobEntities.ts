/**
 * TanStack Query hook for v1 job entities (Epic 3.1.B).
 */

import { useQuery } from '@tanstack/react-query';
import { getJobEntities } from '../api/client';
import { queryKeys } from '../api/queryKeys';

export function useJobEntities(
  jobId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.jobEntities(jobId ?? ''),
    queryFn: () => getJobEntities(jobId!),
    enabled: Boolean(jobId && jobId.trim()) && (options?.enabled !== false),
  });
}
