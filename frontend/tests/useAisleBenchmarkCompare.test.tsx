/**
 * Benchmark compare query must not hit the API until inventory, aisle, and two distinct job ids are set.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { useAisleBenchmarkCompare } from '../src/hooks/useAisles';
import * as client from '../src/api/client';
import type { AisleBenchmarkCompareResponse } from '../src/api/types';

const minimalComparePayload = (): AisleBenchmarkCompareResponse => ({
  inventory_id: 'inv',
  aisle_id: 'aisle',
  workflow: 'benchmark_compare',
  read_only: true,
  raw_fetch_truncated: { job_a: false, job_b: false },
  run_a: {
    job_id: 'ja',
    status: 'succeeded',
    created_at: '2024-01-01T00:00:00Z',
    metrics: {
      raw_rows_considered: 0,
      consolidated_positions: 0,
      total_quantity: 0,
      unknown_internal_code_count: 0,
      needs_review_count: 0,
    },
  },
  run_b: {
    job_id: 'jb',
    status: 'succeeded',
    created_at: '2024-01-02T00:00:00Z',
    metrics: {
      raw_rows_considered: 0,
      consolidated_positions: 0,
      total_quantity: 0,
      unknown_internal_code_count: 0,
      needs_review_count: 0,
    },
  },
  diff_summary: {
    keys_only_in_a: 0,
    keys_only_in_b: 0,
    keys_in_both: 0,
    quantity_changed: 0,
    sku_changed: 0,
    position_code_changed: 0,
  },
  diff_rows: [],
  diff_rows_truncated: false,
});

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useAisleBenchmarkCompare', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getAisleBenchmarkCompare').mockResolvedValue(minimalComparePayload());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not fetch when inventoryId is missing', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare(undefined, 'aisle', 'a', 'b'), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('does not fetch when aisleId is missing', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare('inv', undefined, 'a', 'b'), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('does not fetch when either job id is missing', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare('inv', 'aisle', '', 'b'), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('does not fetch when job ids are equal', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare('inv', 'aisle', 'same', 'same'), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('does not fetch when enabled is false even if params look valid', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare('inv', 'aisle', 'a', 'b', { enabled: false }), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('fetches when all ids are present, distinct, and enabled', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare('inv-1', 'aisle-1', 'job-a', 'job-b'), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => {
      expect(client.getAisleBenchmarkCompare).toHaveBeenCalledWith('inv-1', 'aisle-1', 'job-a', 'job-b');
    });
  });

  it('trims whitespace on ids before enabling', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useAisleBenchmarkCompare('  inv-1  ', '  aisle-1  ', '  ja  ', '  jb  '), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => {
      expect(client.getAisleBenchmarkCompare).toHaveBeenCalledWith('inv-1', 'aisle-1', 'ja', 'jb');
    });
  });
});
