/**
 * Phase 3 — query cache isolation: positions/detail keys include job scope.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { useAislePositions, usePositionDetail } from '../src/hooks/usePositions';
import * as client from '../src/api/client';
import type { PositionListResponse, PositionDetailResponse } from '../src/api/types';

const emptyList = (): PositionListResponse => ({
  positions: [],
  page: 1,
  page_size: 500,
  total_items: 0,
  total_pages: 0,
  raw_fetch_truncated: false,
  result_job_id: null,
  result_context_source: null,
});

const minimalDetail = (): PositionDetailResponse => ({
  position: {} as PositionDetailResponse['position'],
  evidences: [],
  review_actions: [],
});

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('usePositions run context (Phase 3)', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getAislePositions').mockImplementation(async (_inv, _aisle, q) => ({
      ...emptyList(),
      result_job_id: q?.job_id ?? 'resolved-default',
      result_context_source: q?.job_id ? 'explicit' : 'operational',
    }));
    vi.spyOn(client, 'getPositionDetail').mockResolvedValue(minimalDetail());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches distinct cache entries for different job_id on positions list', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrap = wrapper(qc);

    const { result: rA } = renderHook(
      () =>
        useAislePositions('inv-1', 'aisle-1', {
          listQuery: { page: 1, page_size: 10, job_id: 'job-a' },
        }),
      { wrapper: wrap }
    );
    const { result: rB } = renderHook(
      () =>
        useAislePositions('inv-1', 'aisle-1', {
          listQuery: { page: 1, page_size: 10, job_id: 'job-b' },
        }),
      { wrapper: wrap }
    );

    await waitFor(() => expect(rA.current.isSuccess).toBe(true));
    await waitFor(() => expect(rB.current.isSuccess).toBe(true));

    expect(rA.current.data?.result_job_id).toBe('job-a');
    expect(rB.current.data?.result_job_id).toBe('job-b');

    expect(client.getAislePositions).toHaveBeenCalledWith(
      'inv-1',
      'aisle-1',
      expect.objectContaining({ job_id: 'job-a' })
    );
    expect(client.getAislePositions).toHaveBeenCalledWith(
      'inv-1',
      'aisle-1',
      expect.objectContaining({ job_id: 'job-b' })
    );
  });

  it('passes job_id to position detail fetch when provided', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrap = wrapper(qc);

    const { result } = renderHook(
      () =>
        usePositionDetail('inv-1', 'aisle-1', 'pos-1', {
          jobId: 'job-z',
        }),
      { wrapper: wrap }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getPositionDetail).toHaveBeenCalledWith('inv-1', 'aisle-1', 'pos-1', {
      jobId: 'job-z',
    });
  });
});
