import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import ClientsList from '../src/pages/ClientsList';
import { AppSnackbarProvider } from '../src/components/ui';

const { useClientsMock, useCreateClientMock } = vi.hoisted(() => ({
  useClientsMock: vi.fn(),
  useCreateClientMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useClients: useClientsMock,
    useCreateClient: useCreateClientMock,
  };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter>
          <ClientsList />
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('ClientsList page', () => {
  beforeEach(() => {
    useClientsMock.mockReset();
    useCreateClientMock.mockReset();
    useCreateClientMock.mockReturnValue({ mutateAsync: vi.fn() });
  });

  it('renders loading state', () => {
    useClientsMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByTestId('clients-list-section')).toBeInTheDocument();
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders error state', () => {
    useClientsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('boom'),
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByText(/no se pudieron cargar los clientes/i)).toBeInTheDocument();
  });

  it('renders empty state', () => {
    useClientsMock.mockReturnValue({
      data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByText(/todavía no hay clientes cargados/i)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /crear cliente/i })).toHaveLength(2);
  });

  it('opens create dialog from clients page action', () => {
    useClientsMock.mockReturnValue({
      data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getAllByRole('button', { name: /crear cliente/i })[0]);
    expect(screen.getByRole('dialog', { name: /crear cliente/i })).toBeInTheDocument();
  });

  it('validates empty name in create client dialog', async () => {
    useClientsMock.mockReturnValue({
      data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getAllByRole('button', { name: /crear cliente/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));
    expect(await screen.findByText(/nombre del cliente es obligatorio/i)).toBeInTheDocument();
  });

  it('submits valid name through create mutation', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: 'client-2' });
    useCreateClientMock.mockReturnValue({ mutateAsync });
    useClientsMock.mockReturnValue({
      data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getAllByRole('button', { name: /crear cliente/i })[0]);
    fireEvent.change(screen.getByLabelText(/nombre del cliente/i), { target: { value: 'Cliente Centro' } });
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ name: 'Cliente Centro' }));
  });

  it('renders client rows when data exists', () => {
    useClientsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'client-1',
            name: 'Cliente Norte',
            status: 'active',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-02T00:00:00Z',
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

    renderPage();
    expect(screen.getByText('Cliente Norte')).toBeInTheDocument();
    expect(screen.getByText(/activo/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /ver detalle/i })).toHaveAttribute('href', '/clientes/client-1');
  });
});
