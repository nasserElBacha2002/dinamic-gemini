import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { useSubmitReviewAction } from '../src/hooks/useMutations';
import * as client from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';
import {
  canonicalizeAislePositionsListQuery,
  positionsListKeyPart,
} from '../src/api/queryParamCanonicalization';
import type { PositionSummary } from '../src/api/types/responses';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function basePosition(overrides: Partial<PositionSummary> = {}): PositionSummary {
  return {
    id: 'pos-1',
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.9,
    needs_review: true,
    position_code: 'P1',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    qty: 3,
    qtySource: 'detected',
    has_evidence: true,
    ...overrides,
  };
}

describe('useSubmitReviewAction cache patching (Phase 5)', () => {
  beforeEach(() => {
    vi.spyOn(client, 'submitReviewAction').mockResolvedValue(undefined as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('aisleResults strategy: patches list + detail; only merge-results is invalidated', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plCanon = canonicalizeAislePositionsListQuery({});
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(plKey, {
      positions: [basePosition({ qty: 3 })],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });

    const detailKey = queryKeys.inventories.positionDetailScoped('inv-1', 'aisle-1', 'pos-1', null, false);
    qc.setQueryData(detailKey, {
      position: basePosition(),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    });

    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'aisleResults',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'update_quantity', corrected_quantity: 9 });
    await waitFor(() => expect(client.submitReviewAction).toHaveBeenCalled());

    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy.mock.calls[0][0]).toEqual({
      queryKey: queryKeys.inventories.mergeResults('inv-1', 'aisle-1'),
    });

    const list = qc.getQueryData<{
      positions: PositionSummary[];
    }>(plKey);
    expect(list?.positions[0].qty).toBe(9);
    expect(list?.positions[0].review_resolution).toBe('qty_corrected');
  });

  it('detail strategy: patches caches and performs no invalidations', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plCanon = canonicalizeAislePositionsListQuery({});
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(plKey, {
      positions: [basePosition()],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });
    const detailKey = queryKeys.inventories.positionDetailScoped('inv-1', 'aisle-1', 'pos-1', null, false);
    qc.setQueryData(detailKey, {
      position: basePosition(),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    });

    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'detail',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'confirm' });
    await waitFor(() => expect(client.submitReviewAction).toHaveBeenCalled());
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('fallback strategy: does not patch; invalidates the Phase 3 set only', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const setDataSpy = vi.spyOn(qc, 'setQueriesData');
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ action_type: 'mark_image_mismatch' });
    await waitFor(() => expect(client.submitReviewAction).toHaveBeenCalled());

    expect(setDataSpy).not.toHaveBeenCalled();
    expect(invalidateSpy).toHaveBeenCalledTimes(4);
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1') },
      { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.mergeResults('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.aisles('inv-1') },
    ]);
  });

  it('aisleResults: no-op when payload cannot patch (missing corrected_quantity) invalidates list, detail, and merge', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plCanon = canonicalizeAislePositionsListQuery({});
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(plKey, {
      positions: [basePosition({ qty: 3 })],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });
    const detailKey = queryKeys.inventories.positionDetailScoped('inv-1', 'aisle-1', 'pos-1', null, false);
    qc.setQueryData(detailKey, {
      position: basePosition(),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    });

    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'aisleResults',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'update_quantity' });
    await waitFor(() => expect(client.submitReviewAction).toHaveBeenCalled());

    expect(invalidateSpy).toHaveBeenCalledTimes(3);
    const keys = invalidateSpy.mock.calls.map((c) => (c[0] as { queryKey: unknown }).queryKey);
    expect(keys).toEqual([
      queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1'),
      queryKeys.inventories.positions('inv-1', 'aisle-1'),
      queryKeys.inventories.mergeResults('inv-1', 'aisle-1'),
    ]);
  });

  it('does not mutate cached data for another inventory', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plCanon = canonicalizeAislePositionsListQuery({});
    const otherKey = queryKeys.inventories.positionsList('inv-other', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(otherKey, {
      positions: [basePosition({ id: 'pos-other' })],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });

    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(plKey, {
      positions: [basePosition()],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });
    const detailKey = queryKeys.inventories.positionDetailScoped('inv-1', 'aisle-1', 'pos-1', null, false);
    qc.setQueryData(detailKey, {
      position: basePosition(),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    });

    const { result } = renderHook(
      () =>
        useSubmitReviewAction('inv-1', 'aisle-1', 'pos-1', {
          strategy: 'aisleResults',
        }),
      { wrapper: wrapper(qc) }
    );

    await result.current.mutateAsync({ action_type: 'confirm' });
    await waitFor(() => expect(client.submitReviewAction).toHaveBeenCalled());

    const other = qc.getQueryData<{ positions: PositionSummary[] }>(otherKey);
    expect(other?.positions[0].needs_review).toBe(true);
  });
});
