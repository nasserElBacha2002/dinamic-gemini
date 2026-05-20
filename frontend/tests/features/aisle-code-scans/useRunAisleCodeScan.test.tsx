import React, { type ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRunAisleCodeScan } from '../../../src/features/aisle-code-scans/hooks/useRunAisleCodeScan';
import { queryKeys } from '../../../src/api/queryKeys';

const runAisleCodeScan = vi.fn();

vi.mock('../../../src/api/codeScansApi', () => ({
  runAisleCodeScan: (...args: unknown[]) => runAisleCodeScan(...args),
}));

function wrapper(client: QueryClient) {
  return function Wrap({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe('useRunAisleCodeScan', () => {
  beforeEach(() => {
    runAisleCodeScan.mockReset();
    runAisleCodeScan.mockResolvedValue({ run: { id: 'run-1' } });
  });

  it('invalidates list and summary queries on success', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useRunAisleCodeScan('inv-1', 'aisle-1'), {
      wrapper: wrapper(client),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.inventories.aisleCodeScans('inv-1', 'aisle-1'),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.inventories.aisleCodeScanSummary('inv-1', 'aisle-1'),
    });
  });

  it('passes jobId to runAisleCodeScan', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useRunAisleCodeScan('inv-1', 'aisle-1', 'job-9'), {
      wrapper: wrapper(client),
    });
    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(runAisleCodeScan).toHaveBeenCalledWith('inv-1', 'aisle-1', { jobId: 'job-9' });
  });
});
