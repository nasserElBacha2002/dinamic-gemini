/**
 * TanStack Query hook for v1 job entities (Epic 3.1.B/3.1.C).
 * Optional traceability_status filter; when provided, backend returns filtered list (summary remains full-job).
 */

import { useQuery } from '@tanstack/react-query';
import type { TraceabilityStatus } from '../api/types';
import { getJobEntities } from '../api/client';
import { queryKeys } from '../api/queryKeys';

export interface UseJobEntitiesOptions {
  enabled?: boolean;
  /** Epic 3.1.C: filter by traceability_status (valid | missing | invalid | unvalidated). */
  traceability_status?: TraceabilityStatus | null;
}

export function useJobEntities(
  jobId: string | undefined,
  options?: UseJobEntitiesOptions
) {
  const traceabilityStatus =
    options?.traceability_status != null && String(options.traceability_status).trim() !== ''
      ? (String(options.traceability_status).trim() as TraceabilityStatus)
      : undefined;

  return useQuery({
    queryKey: queryKeys.jobEntities(jobId ?? '', traceabilityStatus),
    queryFn: () =>
      getJobEntities(jobId!, { traceability_status: traceabilityStatus ?? undefined }),
    enabled: Boolean(jobId?.trim()) && (options?.enabled !== false),
  });
}
