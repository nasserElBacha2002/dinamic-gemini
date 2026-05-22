import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as client from '../src/api/client';
import { useCancelAisleJob, useRetryAisleJob } from '../src/hooks/useMutations';
import {
  clearCacheMutationObservabilityEvents,
  getCacheMutationObservabilityEvents,
  setCacheMutationObservabilityTestOverride,
} from '../src/dev/cacheMutationObservability';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const LABELS = [
  'inventories.aisles',
  'inventories.aisleJobs',
  'inventories.positions',
  'inventories.jobDetail',
] as const;

describe('useCancelAisleJob / useRetryAisleJob observability', () => {
  beforeEach(() => {
    clearCacheMutationObservabilityEvents();
    setCacheMutationObservabilityTestOverride(true);
    vi.spyOn(client, 'cancelAisleJob').mockResolvedValue(undefined as never);
    vi.spyOn(client, 'retryAisleJob').mockResolvedValue(undefined as never);
  });

  afterEach(() => {
    setCacheMutationObservabilityTestOverride(null);
    clearCacheMutationObservabilityEvents();
    vi.restoreAllMocks();
  });

  it('useCancelAisleJob emits mutation_invalidations with expected domains', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useCancelAisleJob('inv-1'), { wrapper: wrapper(qc) });
    await result.current.mutateAsync({ aisleId: 'aisle-1', jobId: 'job-1' });
    await waitFor(() => expect(client.cancelAisleJob).toHaveBeenCalled());
    const inv = getCacheMutationObservabilityEvents().filter((e) => e.kind === 'mutation_invalidations');
    expect(inv).toHaveLength(1);
    const row = inv[0] as { flow: string; labels: readonly string[] };
    expect(row.flow).toBe('useCancelAisleJob');
    expect(row.labels).toEqual([...LABELS]);
  });

  it('useRetryAisleJob emits mutation_invalidations with expected domains', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useRetryAisleJob('inv-1'), { wrapper: wrapper(qc) });
    await result.current.mutateAsync({ aisleId: 'aisle-1', jobId: 'job-1' });
    await waitFor(() => expect(client.retryAisleJob).toHaveBeenCalled());
    const inv = getCacheMutationObservabilityEvents().filter((e) => e.kind === 'mutation_invalidations');
    expect(inv).toHaveLength(1);
    const row = inv[0] as { flow: string; labels: readonly string[] };
    expect(row.flow).toBe('useRetryAisleJob');
    expect(row.labels).toEqual([...LABELS]);
  });
});
