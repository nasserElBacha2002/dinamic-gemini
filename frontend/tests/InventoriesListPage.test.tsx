import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import InventoriesList from '../src/pages/InventoriesList';
import { AppSnackbarProvider } from '../src/components/ui';
import * as breakpointHook from '../src/hooks/useAppBreakpoint';

vi.mock('../src/hooks/useAppBreakpoint', async () => {
  const actual = await vi.importActual<typeof import('../src/hooks/useAppBreakpoint')>(
    '../src/hooks/useAppBreakpoint'
  );
  return {
    ...actual,
    useAppBreakpoint: vi.fn(),
  };
});

const useAppBreakpointMock = vi.mocked(breakpointHook.useAppBreakpoint);

function desktopBreakpoint(): breakpointHook.AppBreakpoint {
  return {
    isPhone: false,
    isTablet: false,
    isDesktop: true,
    isMdUp: true,
    isSmUp: true,
    isMobileNav: false,
    isCompact: false,
    isDesktopShell: true,
    useTemporaryNavigation: false,
    useMobileTableCards: false,
    useFullscreenDialog: false,
    useMobileFilterDrawer: false,
    useVerticalWizard: false,
  };
}

const {
  useInventoriesListMock,
  useCreateInventoryMock,
  useSoftDeleteInventoriesMock,
} = vi.hoisted(() => ({
  useInventoriesListMock: vi.fn(),
  useCreateInventoryMock: vi.fn(),
  useSoftDeleteInventoriesMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoriesList: useInventoriesListMock,
    useCreateInventory: useCreateInventoryMock,
    useSoftDeleteInventories: useSoftDeleteInventoriesMock,
  };
});

function renderPage() {
  useAppBreakpointMock.mockReturnValue(desktopBreakpoint());
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={createTheme()}>
      <QueryClientProvider client={queryClient}>
        <AppSnackbarProvider>
          <MemoryRouter>
            <InventoriesList />
          </MemoryRouter>
        </AppSnackbarProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

const twoItems = {
  items: [
    {
      id: 'inv-1',
      name: 'Warehouse A',
      status: 'draft',
      processing_mode: 'production',
      client_id: 'c1',
      client_name: 'Client One',
      created_at: '2026-01-01T00:00:00Z',
      aisles_count: 1,
      pending_review_count: 0,
      last_activity_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'inv-2',
      name: 'Warehouse B',
      status: 'draft',
      processing_mode: 'production',
      client_id: null,
      client_name: null,
      created_at: '2026-01-02T00:00:00Z',
      aisles_count: 0,
      pending_review_count: 0,
      last_activity_at: '2026-01-02T00:00:00Z',
    },
  ],
  page: 1,
  page_size: 25,
  total_items: 2,
  total_pages: 1,
};

function clickConfirmInDialog() {
  const dialog = screen.getByRole('dialog');
  const confirm = within(dialog)
    .getAllByRole('button')
    .find(
      (b) =>
        /eliminar|delete/i.test(b.textContent || '') &&
        !/cancel/i.test(b.textContent || '')
    );
  expect(confirm).toBeTruthy();
  fireEvent.click(confirm!);
}

describe('InventoriesList page', () => {
  beforeEach(() => {
    useAppBreakpointMock.mockReset();
    useAppBreakpointMock.mockReturnValue(desktopBreakpoint());
    useInventoriesListMock.mockReset();
    useCreateInventoryMock.mockReset();
    useSoftDeleteInventoriesMock.mockReset();
    useCreateInventoryMock.mockReturnValue({ mutateAsync: vi.fn() });
    useSoftDeleteInventoriesMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
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

  it('disables delete until selection and supports multi-select confirm', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      deleted_ids: ['inv-1', 'inv-2'],
      already_deleted_ids: [],
      not_found_ids: [],
    });
    const refetch = vi.fn().mockResolvedValue(undefined);
    useInventoriesListMock.mockReturnValue({
      data: twoItems,
      isLoading: false,
      isError: false,
      error: null,
      refetch,
    });
    useSoftDeleteInventoriesMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    renderPage();
    const deleteBtn = screen.getByTestId('inventories-delete-selected');
    expect(deleteBtn).toBeDisabled();

    const selectOne = screen.getByTestId('inventories-select-inv-1').querySelector('input');
    const selectTwo = screen.getByTestId('inventories-select-inv-2').querySelector('input');
    expect(selectOne).toBeTruthy();
    expect(selectTwo).toBeTruthy();
    fireEvent.click(selectOne!);
    expect(deleteBtn).toBeEnabled();
    expect(screen.getByTestId('inventories-selected-count')).toBeInTheDocument();

    fireEvent.click(selectTwo!);
    fireEvent.click(deleteBtn);

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /cancelar|cancel/i }));
    expect(mutateAsync).not.toHaveBeenCalled();

    fireEvent.click(deleteBtn);
    await screen.findByRole('dialog');
    clickConfirmInDialog();

    expect(mutateAsync).toHaveBeenCalledWith(['inv-1', 'inv-2']);
  });

  it('shows API error in confirm dialog and keeps selection', async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error('fail'));
    useInventoriesListMock.mockReturnValue({
      data: twoItems,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useSoftDeleteInventoriesMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    renderPage();
    const selectOne = screen.getByTestId('inventories-select-inv-1').querySelector('input');
    fireEvent.click(selectOne!);
    fireEvent.click(screen.getByTestId('inventories-delete-selected'));
    await screen.findByRole('dialog');
    clickConfirmInDialog();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByTestId('inventories-select-inv-1').querySelector('input')).toBeChecked();
  });

  it('renders client column with name and empty state', () => {
    useInventoriesListMock.mockReturnValue({
      data: twoItems,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByTestId('inventory-client-cell-inv-1')).toHaveTextContent('Client One');
    expect(screen.getByTestId('inventory-client-cell-inv-2')).toHaveTextContent(/sin cliente|no client/i);
  });
});
