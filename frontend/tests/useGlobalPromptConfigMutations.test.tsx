import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as clientApi from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';
import {
  useActivateGlobalPromptConfig,
  useCreateGlobalPromptConfig,
} from '../src/hooks/useMutations';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('global prompt config mutations', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('useCreateGlobalPromptConfig invalidates global prompt keys', async () => {
    vi.spyOn(clientApi, 'createGlobalPromptConfigVersion').mockResolvedValue({
      id: 'cfg-1',
      scope_type: 'global',
      provider_name: null,
      model_name: null,
      instructions_text: 'x',
      version: 1,
      is_active: false,
      created_at: '2026-05-08T00:00:00Z',
      updated_at: '2026-05-08T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useCreateGlobalPromptConfig(), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ instructions_text: 'x', activate: false });
    await waitFor(() => expect(clientApi.createGlobalPromptConfigVersion).toHaveBeenCalled());

    const invalidations = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(invalidations).toContainEqual({ queryKey: queryKeys.admin.globalPromptConfigs.list() });
    expect(invalidations).toContainEqual({ queryKey: queryKeys.admin.globalPromptConfigs.active() });
    expect(invalidations).toContainEqual({ queryKey: queryKeys.admin.globalPromptConfigs.all });
  });

  it('useActivateGlobalPromptConfig invalidates global prompt keys', async () => {
    vi.spyOn(clientApi, 'activateGlobalPromptConfigVersion').mockResolvedValue({
      id: 'cfg-2',
      scope_type: 'global',
      provider_name: null,
      model_name: null,
      instructions_text: 'x',
      version: 2,
      is_active: true,
      created_at: '2026-05-08T00:00:00Z',
      updated_at: '2026-05-08T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useActivateGlobalPromptConfig(), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync('cfg-2');
    await waitFor(() => expect(clientApi.activateGlobalPromptConfigVersion).toHaveBeenCalledWith('cfg-2'));

    const invalidations = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(invalidations).toContainEqual({ queryKey: queryKeys.admin.globalPromptConfigs.list() });
    expect(invalidations).toContainEqual({ queryKey: queryKeys.admin.globalPromptConfigs.active() });
    expect(invalidations).toContainEqual({ queryKey: queryKeys.admin.globalPromptConfigs.all });
  });
});
