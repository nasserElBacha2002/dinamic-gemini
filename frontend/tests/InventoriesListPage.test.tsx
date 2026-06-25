import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import InventoriesList from '../src/pages/InventoriesList';
import { AppSnackbarProvider } from '../src/components/ui';

const { useInventoriesListMock, useCreateInventoryMock } = vi.hoisted(() => ({
  useInventoriesListMock: vi.fn(),
  useCreateInventoryMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoriesList: useInventoriesListMock,
    useCreateInventory: useCreateInventoryMock,
  };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter>
          <InventoriesList />
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('InventoriesList page', () => {
  beforeEach(() => {
    useInventoriesListMock.mockReset();
    useCreateInventoryMock.mockReset();
    useCreateInventoryMock.mockReturnValue({ mutateAsync: vi.fn() });
  });

  it('renders loading state with table section', () => {
    useInventoriesListMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByTestId('inventories-list-section')).toBeInTheDocument();
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('inventories-list-search')).toBeInTheDocument();
  });

  it('renders error state without table section content', () => {
    useInventoriesListMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('boom'),
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.queryByTestId('inventories-list-section')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('passes server list query params from table state', () => {
    useInventoriesListMock.mockReturnValue({
      data: {
        items: [{ id: 'inv-1', name: 'Warehouse A', status: 'active' }],
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
    expect(useInventoriesListMock).toHaveBeenCalled();
    const queryArg = useInventoriesListMock.mock.calls[0]?.[0];
    expect(queryArg).toMatchObject({
      page: 1,
      page_size: 25,
      sort_by: 'created_at',
      sort_dir: 'desc',
    });
    expect(screen.getByText('Warehouse A')).toBeInTheDocument();
  });
});
