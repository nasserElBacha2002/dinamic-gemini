import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApiError } from '../src/api/types';
import ClientSupplierDetail from '../src/pages/ClientSupplierDetail';
import { AppSnackbarProvider } from '../src/components/ui';

const {
  useClientMock,
  useClientSupplierMock,
  useActiveSupplierPromptConfigMock,
  useSupplierReferenceImagesMock,
  useSupplierPromptConfigsMock,
  useCreateSupplierPromptConfigVersionMock,
  useActivateSupplierPromptConfigVersionMock,
  useProcessingProviderOptionsMock,
  useUploadSupplierReferenceImagesMock,
  useDeleteSupplierReferenceImageMock,
} = vi.hoisted(() => ({
  useClientMock: vi.fn(),
  useClientSupplierMock: vi.fn(),
  useActiveSupplierPromptConfigMock: vi.fn(),
  useSupplierReferenceImagesMock: vi.fn(),
  useSupplierPromptConfigsMock: vi.fn(),
  useCreateSupplierPromptConfigVersionMock: vi.fn(),
  useActivateSupplierPromptConfigVersionMock: vi.fn(),
  useProcessingProviderOptionsMock: vi.fn(),
  useUploadSupplierReferenceImagesMock: vi.fn(),
  useDeleteSupplierReferenceImageMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useClient: useClientMock,
    useClientSupplier: useClientSupplierMock,
    useActiveSupplierPromptConfig: useActiveSupplierPromptConfigMock,
    useSupplierReferenceImages: useSupplierReferenceImagesMock,
    useSupplierPromptConfigs: useSupplierPromptConfigsMock,
    useCreateSupplierPromptConfigVersion: useCreateSupplierPromptConfigVersionMock,
    useActivateSupplierPromptConfigVersion: useActivateSupplierPromptConfigVersionMock,
    useProcessingProviderOptions: useProcessingProviderOptionsMock,
    useUploadSupplierReferenceImages: useUploadSupplierReferenceImagesMock,
    useDeleteSupplierReferenceImage: useDeleteSupplierReferenceImageMock,
  };
});

function renderPage(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/clientes/:clientId/proveedores/:supplierId" element={<ClientSupplierDetail />} />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('ClientSupplierDetail page', () => {
  beforeEach(() => {
    useClientMock.mockReset();
    useClientSupplierMock.mockReset();
    useActiveSupplierPromptConfigMock.mockReset();
    useSupplierReferenceImagesMock.mockReset();
    useSupplierPromptConfigsMock.mockReset();
    useCreateSupplierPromptConfigVersionMock.mockReset();
    useActivateSupplierPromptConfigVersionMock.mockReset();
    useProcessingProviderOptionsMock.mockReset();
    useUploadSupplierReferenceImagesMock.mockReset();
    useDeleteSupplierReferenceImageMock.mockReset();

    useClientMock.mockReturnValue({
      data: {
        id: 'client-1',
        name: 'Cliente Norte',
        status: 'active',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useClientSupplierMock.mockReturnValue({
      data: {
        id: 'supplier-1',
        client_id: 'client-1',
        name: 'Proveedor Norte',
        status: 'active',
        created_at: '2024-01-03T00:00:00Z',
        updated_at: '2024-01-04T00:00:00Z',
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useActiveSupplierPromptConfigMock.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useSupplierReferenceImagesMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useSupplierPromptConfigsMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useCreateSupplierPromptConfigVersionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useActivateSupplierPromptConfigVersionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useProcessingProviderOptionsMock.mockReturnValue({
      data: {
        default_provider_key: 'gemini',
        default_prompt_key: 'hybrid_v1',
        prompt_profiles: [],
        providers: [
          {
            key: 'gemini',
            label: 'Gemini',
            execution_mode: 'native',
            models: [{ id: 'gemini-2.0-flash-exp', label: 'gemini-2.0-flash-exp' }],
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
    });
    useUploadSupplierReferenceImagesMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ items: [] }),
      isPending: false,
      reset: vi.fn(),
      isError: false,
      error: null,
    });
    useDeleteSupplierReferenceImageMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ deleted: true, id: 'x' }),
      isPending: false,
      reset: vi.fn(),
      isError: false,
      error: null,
    });
  });

  it('shows warning when active prompt query returns 404', () => {
    useActiveSupplierPromptConfigMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new ApiError('Not found', 404),
      refetch: vi.fn(),
    });
    renderPage('/clientes/client-1/proveedores/supplier-1');
    expect(screen.getByRole('status')).toHaveTextContent(/sin prompt activo/i);
  });

  it('shows summary tab by default and does not show drawer management buttons', () => {
    renderPage('/clientes/client-1/proveedores/supplier-1');
    expect(screen.getByRole('tab', { name: /^resumen$/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^prompts$/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^imágenes de referencia$/i })).toBeInTheDocument();
    expect(screen.getByText(/configuración del proveedor/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /gestionar prompts/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /gestionar imágenes de referencia/i })).not.toBeInTheDocument();
  });

  it('shows prompt management in Prompts tab', async () => {
    renderPage('/clientes/client-1/proveedores/supplier-1');
    fireEvent.click(screen.getByRole('tab', { name: /^prompts$/i }));
    await waitFor(() => {
      expect(screen.getByText(/prompts del proveedor/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { name: /instrucciones del proveedor/i })).toBeInTheDocument();
  });

  it('shows reference image section in Imágenes de referencia tab', async () => {
    renderPage('/clientes/client-1/proveedores/supplier-1');
    fireEvent.click(screen.getByRole('tab', { name: /^imágenes de referencia$/i }));
    await waitFor(() => {
      expect(screen.getByText(/imágenes de referencia del proveedor/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/estas imágenes se usan como contexto visual comparativo durante el procesamiento/i)
    ).toBeInTheDocument();
  });

  it('opens prompts tab from query param', () => {
    renderPage('/clientes/client-1/proveedores/supplier-1?tab=prompts');
    expect(screen.getByText(/prompts del proveedor/i)).toBeInTheDocument();
  });

  it('opens reference images tab from query param', () => {
    renderPage('/clientes/client-1/proveedores/supplier-1?tab=imagenes');
    expect(screen.getByText(/imágenes de referencia del proveedor/i)).toBeInTheDocument();
  });
});
