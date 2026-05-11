import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as clientApi from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';
import {
  useActivateSupplierPromptConfigVersion,
  useCreateSupplierPromptConfigVersion,
} from '../src/hooks/useMutations';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('supplier prompt config mutations', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('useCreateSupplierPromptConfigVersion invalidates scope and supplier prompt keys', async () => {
    vi.spyOn(clientApi, 'createSupplierPromptConfigVersion').mockResolvedValue({
      id: 'cfg-1',
      client_supplier_id: 'supplier-1',
      provider_name: 'gemini',
      model_name: null,
      instructions_text: 'x',
      version: 1,
      is_active: false,
      created_at: '2026-05-08T00:00:00Z',
      updated_at: '2026-05-08T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useCreateSupplierPromptConfigVersion('client-1', 'supplier-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({
      provider_name: 'gemini',
      model_name: null,
      instructions_text: 'x',
      activate: false,
    });
    await waitFor(() => expect(clientApi.createSupplierPromptConfigVersion).toHaveBeenCalled());

    const invalidations = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(invalidations).toContainEqual({
      queryKey: queryKeys.clients.suppliers.promptConfigs.listByScope(
        'client-1',
        'supplier-1',
        'provider',
        'gemini',
        null
      ),
    });
    expect(invalidations).toContainEqual({
      queryKey: queryKeys.clients.suppliers.promptConfigs.activeByScope(
        'client-1',
        'supplier-1',
        'provider',
        'gemini',
        null
      ),
    });
    expect(invalidations).toContainEqual({
      queryKey: queryKeys.clients.suppliers.promptConfigs.all('client-1', 'supplier-1'),
    });
  });

  it('useActivateSupplierPromptConfigVersion invalidates scope and supplier prompt keys', async () => {
    vi.spyOn(clientApi, 'activateSupplierPromptConfigVersion').mockResolvedValue({
      id: 'cfg-2',
      client_supplier_id: 'supplier-1',
      provider_name: 'gemini',
      model_name: 'gemini-2.0-flash-exp',
      instructions_text: 'x',
      version: 2,
      is_active: true,
      created_at: '2026-05-08T00:00:00Z',
      updated_at: '2026-05-08T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useActivateSupplierPromptConfigVersion('client-1', 'supplier-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync('cfg-2');
    await waitFor(() => expect(clientApi.activateSupplierPromptConfigVersion).toHaveBeenCalledWith('client-1', 'supplier-1', 'cfg-2'));

    const invalidations = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(invalidations).toContainEqual({
      queryKey: queryKeys.clients.suppliers.promptConfigs.listByScope(
        'client-1',
        'supplier-1',
        'provider_model',
        'gemini',
        'gemini-2.0-flash-exp'
      ),
    });
    expect(invalidations).toContainEqual({
      queryKey: queryKeys.clients.suppliers.promptConfigs.activeByScope(
        'client-1',
        'supplier-1',
        'provider_model',
        'gemini',
        'gemini-2.0-flash-exp'
      ),
    });
    expect(invalidations).toContainEqual({
      queryKey: queryKeys.clients.suppliers.promptConfigs.all('client-1', 'supplier-1'),
    });
  });
});

