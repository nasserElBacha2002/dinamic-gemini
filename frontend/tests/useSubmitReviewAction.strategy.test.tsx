import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { useSubmitReviewAction } from '../src/hooks/useMutations';
import * as client from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useSubmitReviewAction strategy invalidation', () => {
  beforeEach(() => {
    vi.spyOn(client, 'submitReviewAction').mockResolvedValue(undefined as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reviewQueue strategy invalidates detail + reviewQueue only', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'reviewQueue',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'confirm' });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    const calls = invalidateSpy.mock.calls.map((c) => c[0]);

    expect(calls).toEqual(
      expect.arrayContaining([
        { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
        { queryKey: queryKeys.reviewQueue.all },
      ])
    );
    expect(calls).toHaveLength(2);
  });

  it('aisleResults strategy invalidates detail + positions + merge-results', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'aisleResults',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'update_quantity', corrected_quantity: 7 });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    const calls = invalidateSpy.mock.calls.map((c) => c[0]);

    expect(calls).toEqual(
      expect.arrayContaining([
        { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
        { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
        { queryKey: queryKeys.inventories.mergeResults('inv-1', 'aisle-1') },
      ])
    );
    expect(calls).toHaveLength(3);
  });

  it('default strategy preserves phase3 compatibility', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ action_type: 'mark_image_mismatch' });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    const calls = invalidateSpy.mock.calls.map((c) => c[0]);

    expect(calls).toEqual(
      expect.arrayContaining([
        { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
        { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
        { queryKey: queryKeys.inventories.mergeResults('inv-1', 'aisle-1') },
        { queryKey: queryKeys.inventories.aisles('inv-1') },
        { queryKey: queryKeys.reviewQueue.all },
      ])
    );
  });
});

