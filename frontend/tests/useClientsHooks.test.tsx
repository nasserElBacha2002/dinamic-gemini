import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as clientApi from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';
import {
  useClientSuppliers,
  useClients,
} from '../src/hooks/useClients';
import {
  useCreateClient,
  useCreateClientSupplier,
} from '../src/hooks/useMutations';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('clients hooks', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('useClients fetches via listClients', async () => {
    vi.spyOn(clientApi, 'listClients').mockResolvedValue({
      items: [],
      page: 1,
      page_size: 25,
      total_items: 0,
      total_pages: 0,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useClients({ page: 1, page_size: 25 }), { wrapper: wrapper(qc) });
    await waitFor(() => {
      expect(clientApi.listClients).toHaveBeenCalledWith({ page: 1, page_size: 25 });
    });
  });

  it('useClientSuppliers is scoped and disabled when clientId is missing', async () => {
    vi.spyOn(clientApi, 'listClientSuppliers').mockResolvedValue({
      items: [],
      page: 1,
      page_size: 25,
      total_items: 0,
      total_pages: 0,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useClientSuppliers(undefined, { page: 1, page_size: 25 }), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(qc.isFetching()).toBe(0));
    expect(clientApi.listClientSuppliers).not.toHaveBeenCalled();
  });

  it('useCreateClient invalidates clients all and created detail', async () => {
    vi.spyOn(clientApi, 'createClient').mockResolvedValue({
      id: 'client-1',
      name: 'Cliente 1',
      status: 'active',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useCreateClient(), { wrapper: wrapper(qc) });

    await result.current.mutateAsync({ name: 'Cliente 1' });
    await waitFor(() => expect(clientApi.createClient).toHaveBeenCalled());
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.clients.all },
      { queryKey: queryKeys.clients.detail('client-1') },
    ]);
  });

  it('useCreateClientSupplier invalidates supplier scope for the same client', async () => {
    vi.spyOn(clientApi, 'createClientSupplier').mockResolvedValue({
      id: 'supplier-1',
      client_id: 'client-1',
      name: 'Proveedor 1',
      status: 'active',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useCreateClientSupplier('client-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync({ name: 'Proveedor 1' });
    await waitFor(() => expect(clientApi.createClientSupplier).toHaveBeenCalled());
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: queryKeys.clients.suppliers.all('client-1') },
      { queryKey: queryKeys.clients.suppliers.detail('client-1', 'supplier-1') },
    ]);
  });
});
