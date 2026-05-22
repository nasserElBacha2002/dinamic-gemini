import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as client from '../src/api/client';
import { useJobAuditability } from '../src/hooks/useAisles';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useJobAuditability', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls getJobAuditability with ids when enabled', async () => {
    vi.spyOn(client, 'getJobAuditability').mockResolvedValue({
      job_id: 'j1',
      status: 'succeeded',
      target_type: 'aisle',
      target_id: 'a1',
      created_at: null,
      started_at: null,
      finished_at: null,
      inventory_id: null,
      aisle_id: null,
      client_id: null,
      client_supplier_id: null,
      provider_name: null,
      model_name: null,
      prompt_key: null,
      prompt_version: null,
      supplier_prompt_config_id: null,
      supplier_prompt_config_version: null,
      supplier_prompt_fallback_used: null,
      supplier_prompt_fallback_reason: null,
      protected_prompt_contract_key: null,
      protected_prompt_contract_version: null,
      effective_prompt_hash: null,
      prompt_composition_available: false,
      reference_usage: null,
      supplier_reference_images_used: null,
      inventory_visual_references_used: null,
      reference_source: null,
      reference_image_count: null,
      reference_ids: [],
      warnings: [],
      metadata_sources: {
        job_row: false,
        result_json: false,
        aisle_join: false,
        inventory_join: false,
        hybrid_report: false,
        execution_log: false,
        run_audit_snapshot: false,
      },
      missing_metadata: [],
      legacy_mode: false,
      cost_snapshot: null,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useJobAuditability('inv-1', 'aisle-1', 'j1', { enabled: true }),
      { wrapper: wrapper(qc) }
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getJobAuditability).toHaveBeenCalledWith('inv-1', 'aisle-1', 'j1');
  });
});
