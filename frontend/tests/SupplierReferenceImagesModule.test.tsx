import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SupplierReferenceImagesModule from '../src/features/clients/components/SupplierReferenceImagesModule';
import { AppSnackbarProvider } from '../src/components/ui';

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSupplierReferenceImages: vi.fn(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })),
    useUploadSupplierReferenceImages: vi.fn(() => ({
      mutateAsync: vi.fn().mockResolvedValue({ items: [] }),
      isPending: false,
      reset: vi.fn(),
      isError: false,
      error: null,
    })),
    useDeleteSupplierReferenceImage: vi.fn(() => ({
      mutateAsync: vi.fn().mockResolvedValue({ deleted: true, id: 'x' }),
      isPending: false,
      reset: vi.fn(),
      isError: false,
      error: null,
    })),
  };
});

function renderModule() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>
        <SupplierReferenceImagesModule
          clientId="client-1"
          supplierId="supplier-1"
          supplierName="Proveedor Test"
          open
          onClose={vi.fn()}
        />
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('SupplierReferenceImagesModule', () => {
  it('renders drawer title and supplier context in Spanish', () => {
    renderModule();
    expect(screen.getByText('Imágenes de referencia', { exact: true })).toBeInTheDocument();
    expect(screen.getByText(/proveedor:\s*proveedor test/i)).toBeInTheDocument();
    expect(screen.getByText(/no hay imágenes de referencia/i)).toBeInTheDocument();
  });

  it('shows Spanish load error copy when the list query is in error', async () => {
    const hooks = await import('../src/hooks');
    vi.mocked(hooks.useSupplierReferenceImages).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('network'),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useSupplierReferenceImages>);

    renderModule();

    expect(
      screen.getByText('No se pudieron cargar las imágenes de referencia.', { exact: true })
    ).toBeInTheDocument();
  });
});
