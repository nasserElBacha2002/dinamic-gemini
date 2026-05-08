import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppSnackbarProvider } from '../src/components/ui';
import SupplierPromptConfigsModule from '../src/features/clients/components/SupplierPromptConfigsModule';

const {
  useSupplierPromptConfigsMock,
  useActiveSupplierPromptConfigMock,
  useCreateSupplierPromptConfigVersionMock,
  useActivateSupplierPromptConfigVersionMock,
} = vi.hoisted(() => ({
  useSupplierPromptConfigsMock: vi.fn(),
  useActiveSupplierPromptConfigMock: vi.fn(),
  useCreateSupplierPromptConfigVersionMock: vi.fn(),
  useActivateSupplierPromptConfigVersionMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSupplierPromptConfigs: useSupplierPromptConfigsMock,
    useActiveSupplierPromptConfig: useActiveSupplierPromptConfigMock,
    useCreateSupplierPromptConfigVersion: useCreateSupplierPromptConfigVersionMock,
    useActivateSupplierPromptConfigVersion: useActivateSupplierPromptConfigVersionMock,
  };
});

function renderModule() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>
        <SupplierPromptConfigsModule
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

describe('SupplierPromptConfigsModule', () => {
  it('renders boundary text and empty states', () => {
    useSupplierPromptConfigsMock.mockReturnValue({
      data: { items: [] },
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

    renderModule();

    expect(screen.getByText('Instrucciones del proveedor', { exact: true })).toBeInTheDocument();
    expect(
      screen.getByText(
        'Estas instrucciones se suman al prompt técnico del sistema. No modifican el formato de respuesta ni las reglas internas de procesamiento.',
        { exact: true }
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/no hay una versión activa/i)).toBeInTheDocument();
    expect(screen.getByText(/este proveedor todavía no tiene instrucciones específicas/i)).toBeInTheDocument();
  });

  it('submits create with activate true and false', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    useSupplierPromptConfigsMock.mockReturnValue({
      data: { items: [] },
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
    useCreateSupplierPromptConfigVersionMock.mockReturnValue({
      mutateAsync,
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

    renderModule();

    fireEvent.change(screen.getByLabelText(/instrucciones del proveedor/i), {
      target: { value: '  línea 1\nlínea 2  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /guardar y activar/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_name: 'gemini',
          model_name: null,
          instructions_text: 'línea 1\nlínea 2',
          activate: true,
        })
      )
    );

    fireEvent.change(screen.getByLabelText(/instrucciones del proveedor/i), {
      target: { value: 'otra versión' },
    });
    fireEvent.click(screen.getByRole('button', { name: /guardar sin activar/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          instructions_text: 'otra versión',
          activate: false,
        })
      )
    );
  });

  it('shows blank validation and can activate an inactive version', async () => {
    const activateMutate = vi.fn().mockResolvedValue({});
    useSupplierPromptConfigsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'cfg-1',
            client_supplier_id: 'supplier-1',
            provider_name: 'gemini',
            model_name: null,
            instructions_text: 'texto',
            version: 1,
            is_active: false,
            created_at: '2026-05-08T12:00:00Z',
            updated_at: '2026-05-08T12:00:00Z',
            system_prompt: 'hidden',
            composed_prompt: 'hidden',
          },
        ],
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
    useCreateSupplierPromptConfigVersionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useActivateSupplierPromptConfigVersionMock.mockReturnValue({
      mutateAsync: activateMutate,
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });

    renderModule();

    fireEvent.change(screen.getByLabelText(/instrucciones del proveedor/i), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /guardar y activar/i }));
    expect(screen.getByText('Las instrucciones no pueden estar vacías.', { exact: true })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /activar versión/i }));
    await waitFor(() => expect(activateMutate).toHaveBeenCalledWith('cfg-1'));

    expect(screen.queryByText(/system_prompt/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/composed_prompt/i)).not.toBeInTheDocument();
  });
});

