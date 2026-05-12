import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import * as clientApi from '../src/api/client';
import { queryKeys } from '../src/api/queryKeys';
import {
  useDeleteSupplierReferenceImage,
  useUploadSupplierReferenceImages,
} from '../src/hooks/useMutations';

function wrapper(qc: QueryClient) {
  return function W({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('supplier reference image mutations', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('useUploadSupplierReferenceImages invalidates scoped referenceImages query', async () => {
    vi.spyOn(clientApi, 'uploadSupplierReferenceImages').mockResolvedValue({ items: [] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useUploadSupplierReferenceImages('client-1', 'supplier-1'), {
      wrapper: wrapper(qc),
    });

    const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
    await result.current.mutateAsync({ files: [file], label: 'L' });

    await waitFor(() => expect(clientApi.uploadSupplierReferenceImages).toHaveBeenCalled());
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toContainEqual({
      queryKey: queryKeys.clients.suppliers.referenceImages('client-1', 'supplier-1'),
    });
  });

  it('useDeleteSupplierReferenceImage invalidates scoped referenceImages query', async () => {
    vi.spyOn(clientApi, 'deleteSupplierReferenceImage').mockResolvedValue({
      deleted: true,
      id: 'img-1',
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useDeleteSupplierReferenceImage('client-1', 'supplier-1'), {
      wrapper: wrapper(qc),
    });

    await result.current.mutateAsync('img-1');

    await waitFor(() => expect(clientApi.deleteSupplierReferenceImage).toHaveBeenCalled());
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toContainEqual({
      queryKey: queryKeys.clients.suppliers.referenceImages('client-1', 'supplier-1'),
    });
  });
});
