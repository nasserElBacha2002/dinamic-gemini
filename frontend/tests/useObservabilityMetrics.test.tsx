import type { ReactNode } from 'react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as observabilityApi from '../src/api/observabilityApi';
import { useObservabilityMetrics } from '../src/hooks/useObservabilityMetrics';

const emptyMetrics = {
  range: { from: '2026-01-01T00:00:00Z', to: '2026-01-02T00:00:00Z' },
  filters: {
    client_id: null,
    client_supplier_id: null,
    provider_name: null,
    model_name: null,
  },
  totals: {
    runs_total: 0,
    runs_succeeded: 0,
    runs_failed: 0,
    success_rate: null,
    failure_rate: null,
    fallback_runs: 0,
    missing_prompt_config_runs: 0,
    missing_reference_runs: 0,
    legacy_runs: 0,
  },
  by_client: [],
  by_supplier: [],
  by_provider_model: [],
  data_quality: {
    jobs_with_audit_snapshot: 0,
    jobs_without_audit_snapshot: 0,
    jobs_with_missing_metadata: 0,
    artifact_dependent_jobs: 0,
  },
};

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useObservabilityMetrics', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading then resolves', async () => {
    vi.spyOn(observabilityApi, 'getObservabilityMetrics').mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(emptyMetrics), 50))
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useObservabilityMetrics({ from: 'a', to: 'b' }),
      { wrapper: wrapper(qc) }
    );
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observabilityApi.getObservabilityMetrics).toHaveBeenCalledWith(
      expect.objectContaining({ from: 'a', to: 'b' })
    );
  });
});
