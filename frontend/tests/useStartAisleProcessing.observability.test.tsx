import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as client from '../src/api/client';
import { useStartAisleProcessing } from '../src/hooks/useMutations';
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

describe('useStartAisleProcessing observability (Phase 8 closure)', () => {
  beforeEach(() => {
    clearCacheMutationObservabilityEvents();
    setCacheMutationObservabilityTestOverride(true);
    vi.spyOn(client, 'startAisleProcessing').mockResolvedValue(undefined as never);
  });

  afterEach(() => {
    setCacheMutationObservabilityTestOverride(null);
    clearCacheMutationObservabilityEvents();
    vi.restoreAllMocks();
  });

  it('emits mutation_invalidations with expected domains after success', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useStartAisleProcessing('inv-1'), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({
      aisleId: 'aisle-1',
      providerName: null,
      modelName: null,
      promptKey: null,
    });
    await waitFor(() => expect(client.startAisleProcessing).toHaveBeenCalled());

    const inv = getCacheMutationObservabilityEvents().filter((e) => e.kind === 'mutation_invalidations');
    expect(inv).toHaveLength(1);
    const row = inv[0] as { flow: string; labels: string[] };
    expect(row.flow).toBe('useStartAisleProcessing');
    expect(row.labels).toEqual([
      'inventories.aisles',
      'inventories.detail',
      'inventories.aisleJobs',
      'inventories.positions',
    ]);
  });
});
