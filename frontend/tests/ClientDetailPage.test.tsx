import '@testing-library/jest-dom/vitest';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ClientDetail from '../src/pages/ClientDetail';

const { useClientMock, useClientSuppliersMock } = vi.hoisted(() => ({
  useClientMock: vi.fn(),
  useClientSuppliersMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useClient: useClientMock,
    useClientSuppliers: useClientSuppliersMock,
  };
});

function renderPage(route: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/clientes/:clientId" element={<ClientDetail />} />
          <Route path="/clientes" element={<div data-testid="clients-list-route">clientes</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ClientDetail page', () => {
  beforeEach(() => {
    useClientMock.mockReset();
    useClientSuppliersMock.mockReset();
  });

  it('renders client information and suppliers rows', () => {
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
    useClientSuppliersMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'supplier-1',
            client_id: 'client-1',
            name: 'Proveedor Norte',
            status: 'active',
            created_at: '2024-01-03T00:00:00Z',
            updated_at: '2024-01-04T00:00:00Z',
          },
        ],
        page: 1,
        page_size: 25,
        total_items: 1,
        total_pages: 1,
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage('/clientes/client-1');
    expect(screen.getByText(/información del cliente/i)).toBeInTheDocument();
    expect(screen.getByText(/cliente norte/i)).toBeInTheDocument();
    expect(screen.getByText(/proveedores del cliente/i)).toBeInTheDocument();
    expect(screen.getByText(/proveedor norte/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /crear proveedor/i })).toBeDisabled();
  });

  it('renders client loading state', () => {
    useClientMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useClientSuppliersMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage('/clientes/client-1');
    expect(screen.getByText(/cargando cliente/i)).toBeInTheDocument();
  });

  it('renders client error state', () => {
    useClientMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('boom'),
      refetch: vi.fn(),
    });
    useClientSuppliersMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage('/clientes/client-1');
    expect(screen.getByText(/no se pudo cargar el cliente/i)).toBeInTheDocument();
  });

  it('renders suppliers empty state', () => {
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
    useClientSuppliersMock.mockReturnValue({
      data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage('/clientes/client-1');
    expect(screen.getByText(/todavía no hay proveedores cargados para este cliente/i)).toBeInTheDocument();
  });
});
