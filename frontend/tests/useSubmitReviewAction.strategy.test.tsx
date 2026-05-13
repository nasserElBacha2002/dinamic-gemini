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

function createTestQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe('useSubmitReviewAction strategy invalidation', () => {
  beforeEach(() => {
    vi.spyOn(client, 'submitReviewAction').mockResolvedValue(undefined as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('aisleResults strategy invalidates detail + positions + merge-results', async () => {
    const qc = createTestQueryClient();
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

    expect(calls).toHaveLength(3);
    expect(calls).toEqual([
      { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
      { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.mergeResults('inv-1', 'aisle-1') },
    ]);
  });

  it('detail strategy invalidates detail + positions only', async () => {
    const qc = createTestQueryClient();
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'detail',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'confirm' });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    const calls = invalidateSpy.mock.calls.map((c) => c[0]);

    expect(calls).toHaveLength(2);
    expect(calls).toEqual([
      { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
      { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
    ]);
  });

  it('default strategy preserves phase3 compatibility', async () => {
    const qc = createTestQueryClient();
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ action_type: 'mark_image_mismatch' });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    const calls = invalidateSpy.mock.calls.map((c) => c[0]);

    expect(calls).toHaveLength(4);
    expect(calls).toEqual([
      { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
      { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.mergeResults('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.aisles('inv-1') },
    ]);
  });
});

