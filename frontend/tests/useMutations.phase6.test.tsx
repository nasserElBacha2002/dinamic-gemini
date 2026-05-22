import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as client from '../src/api/client';
import { useCreateAisle, usePromoteAisleOperationalJob } from '../src/hooks/useMutations';
import { queryKeys } from '../src/api/queryKeys';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('Phase 6 mutation cache behavior', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('useCreateAisle patches default aisles cache and skips aisles invalidation', async () => {
    vi.spyOn(client, 'createAisle').mockResolvedValue({
      id: 'aisle-2',
      inventory_id: 'inv-1',
      code: 'A-02',
      status: 'idle',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const aislesKey = queryKeys.inventories.aislesListTable('inv-1');
    qc.setQueryData(aislesKey, {
      items: [
        {
          id: 'aisle-1',
          inventory_id: 'inv-1',
          code: 'A-01',
          status: 'idle',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
      page: 1,
      page_size: 200,
      total_items: 1,
      total_pages: 1,
    });

    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useCreateAisle('inv-1'), { wrapper: wrapper(qc) });
    await result.current.mutateAsync({ code: 'A-02', client_supplier_id: 'sup-1' });
    await waitFor(() => expect(client.createAisle).toHaveBeenCalled());

    const patched = qc.getQueryData<{ items: Array<{ id: string }> }>(aislesKey);
    expect(patched?.items[0].id).toBe('aisle-2');
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.inventories.detail('inv-1') },
    ]);
  });

  it('useCreateAisle falls back to invalidation when aisles cache is missing', async () => {
    vi.spyOn(client, 'createAisle').mockResolvedValue({
      id: 'aisle-2',
      inventory_id: 'inv-1',
      code: 'A-02',
      status: 'idle',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useCreateAisle('inv-1'), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ code: 'A-02', client_supplier_id: 'sup-1' });
    await waitFor(() => expect(client.createAisle).toHaveBeenCalled());

    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.inventories.aisles('inv-1') },
      { queryKey: queryKeys.inventories.detail('inv-1') },
    ]);
  });

  it('usePromoteAisleOperationalJob patches cached operational pointer and skips aisleJobs invalidation', async () => {
    vi.spyOn(client, 'promoteAisleOperationalJob').mockResolvedValue({
      aisle_id: 'aisle-1',
      operational_job_id: 'job-2',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const jobsKey = [...queryKeys.inventories.aisleJobs('inv-1', 'aisle-1'), 50] as const;
    const otherJobsKey = [...queryKeys.inventories.aisleJobs('inv-2', 'aisle-1'), 50] as const;
    qc.setQueryData(jobsKey, {
      operational_job_id: 'job-1',
      jobs: [
        { id: 'job-1', status: 'succeeded', created_at: 't', updated_at: 't', is_operational: true },
        { id: 'job-2', status: 'succeeded', created_at: 't', updated_at: 't', is_operational: false },
      ],
    });
    qc.setQueryData(otherJobsKey, {
      operational_job_id: 'other',
      jobs: [{ id: 'other', status: 'succeeded', created_at: 't', updated_at: 't', is_operational: true }],
    });

    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => usePromoteAisleOperationalJob('inv-1', 'aisle-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync('job-2');
    await waitFor(() => expect(client.promoteAisleOperationalJob).toHaveBeenCalled());

    const patched = qc.getQueryData<{
      operational_job_id: string;
      jobs: Array<{ id: string; is_operational?: boolean }>;
    }>(jobsKey);
    expect(patched?.operational_job_id).toBe('job-2');
    expect(patched?.jobs.find((j) => j.id === 'job-2')?.is_operational).toBe(true);
    expect(patched?.jobs.find((j) => j.id === 'job-1')?.is_operational).toBe(false);
    expect(
      qc.getQueryData<{ operational_job_id: string }>(otherJobsKey)?.operational_job_id
    ).toBe('other');

    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.aisles('inv-1') },
      { queryKey: queryKeys.inventories.benchmarkCompareInventory('inv-1') },
    ]);
  });

  it('usePromoteAisleOperationalJob falls back to aisleJobs invalidation when no cache exists', async () => {
    vi.spyOn(client, 'promoteAisleOperationalJob').mockResolvedValue({
      aisle_id: 'aisle-1',
      operational_job_id: 'job-2',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => usePromoteAisleOperationalJob('inv-1', 'aisle-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync('job-2');
    await waitFor(() => expect(client.promoteAisleOperationalJob).toHaveBeenCalled());

    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.inventories.aisleJobs('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.positions('inv-1', 'aisle-1') },
      { queryKey: queryKeys.inventories.aisles('inv-1') },
      { queryKey: queryKeys.inventories.benchmarkCompareInventory('inv-1') },
    ]);
  });
});
