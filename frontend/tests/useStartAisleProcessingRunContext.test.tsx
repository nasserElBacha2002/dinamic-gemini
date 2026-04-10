/**
 * Process → cache invalidation: after starting aisle processing, jobs and positions refresh keys fire.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { useStartAisleProcessing } from '../src/hooks/useMutations';
import * as client from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useStartAisleProcessing', () => {
  beforeEach(() => {
    vi.spyOn(client, 'startAisleProcessing').mockResolvedValue({ job_id: 'new-job-1' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('invalidates inventory detail, aisles list, aisle jobs, and positions for the aisle', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useStartAisleProcessing('inv-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ aisleId: 'aisle-9' });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalled();
    });

    const calls = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(calls).toEqual(
      expect.arrayContaining([
        { queryKey: queryKeys.inventories.aisles('inv-1') },
        { queryKey: queryKeys.inventories.detail('inv-1') },
        { queryKey: queryKeys.inventories.aisleJobs('inv-1', 'aisle-9') },
        { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-9') },
      ])
    );
  });

  it('passes provider_name to the API when provided', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useStartAisleProcessing('inv-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ aisleId: 'aisle-9', providerName: 'openai' });

    expect(client.startAisleProcessing).toHaveBeenCalledWith('inv-1', 'aisle-9', {
      providerName: 'openai',
    });
  });
});
