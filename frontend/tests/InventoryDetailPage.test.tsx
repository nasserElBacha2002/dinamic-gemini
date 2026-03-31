import '@testing-library/jest-dom/vitest';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import InventoryDetail from '../src/pages/InventoryDetail';
import { AppSnackbarProvider } from '../src/components/ui';

const { useInventoryVisualReferencesMock } = vi.hoisted(() => ({
  useInventoryVisualReferencesMock: vi.fn(),
}));
const { useUploadInventoryVisualReferencesMock } = vi.hoisted(() => ({
  useUploadInventoryVisualReferencesMock: vi.fn(),
}));
const { useDeleteInventoryVisualReferenceMock } = vi.hoisted(() => ({
  useDeleteInventoryVisualReferenceMock: vi.fn(),
}));
const { useReplaceInventoryVisualReferenceMock } = vi.hoisted(() => ({
  useReplaceInventoryVisualReferenceMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => ({
      data: { id: 'inv-1', name: 'Inventory One', status: 'draft', created_at: '2024-01-01T00:00:00Z' },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useInventoryVisualReferences: useInventoryVisualReferencesMock,
    useAislesList: () => ({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'created',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            assets_count: 3,
            positions_count: 7,
            pending_review_positions_count: 1,
            latest_job: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useExecutionLog: () => ({
      data: { events: [] },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    }),
    useCreateAisle: () => ({ mutateAsync: vi.fn() }),
    useStartAisleProcessing: () => ({ mutateAsync: vi.fn() }),
    useUploadAisleAssetsFlex: () => ({ mutateAsync: vi.fn() }),
    useUploadInventoryVisualReferences: useUploadInventoryVisualReferencesMock,
    useDeleteInventoryVisualReference: useDeleteInventoryVisualReferenceMock,
    useReplaceInventoryVisualReference: useReplaceInventoryVisualReferenceMock,
  };
});

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return {
    ...actual,
    exportInventoryResultsCsv: vi.fn(),
  };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={['/inventories/inv-1']}>
          <Routes>
            <Route path="/inventories/:inventoryId" element={<InventoryDetail />} />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('InventoryDetail', () => {
  beforeEach(() => {
    useInventoryVisualReferencesMock.mockReset();
    useUploadInventoryVisualReferencesMock.mockReset();
    useDeleteInventoryVisualReferenceMock.mockReset();
    useReplaceInventoryVisualReferenceMock.mockReset();
    useUploadInventoryVisualReferencesMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useDeleteInventoryVisualReferenceMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useReplaceInventoryVisualReferenceMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
  });

  it('keeps reference images lazy until the drawer opens', () => {
    useInventoryVisualReferencesMock.mockImplementation((_inventoryId, options) => ({
      data: {
        items: [
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      enabled: options?.enabled,
    }));

    renderPage();

    expect(useInventoryVisualReferencesMock).toHaveBeenCalled();
    expect(useInventoryVisualReferencesMock.mock.calls[0]?.[1]).toMatchObject({ enabled: false });

    fireEvent.click(screen.getByRole('button', { name: 'Reference images' }));

    const lastCall = useInventoryVisualReferencesMock.mock.calls.at(-1);
    expect(lastCall?.[1]).toMatchObject({ enabled: true });
  });

  it('keeps the page focused on header and aisles, with a header action for reference images', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: {
        items: [
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));

    renderPage();

    expect(screen.getByRole('heading', { name: 'Inventory One' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reference images' })).toBeInTheDocument();
    expect(screen.getByText('Aisles')).toBeInTheDocument();

    expect(screen.queryByText('Total aisles')).not.toBeInTheDocument();
    expect(screen.queryByText('Review completion rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Logs summary')).not.toBeInTheDocument();
    expect(screen.queryByText('front-pallet.jpg')).not.toBeInTheDocument();
  });

  it('opens the reference images drawer and renders inventory reference data there', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: {
        items: [
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));

    renderPage();

    expect(screen.queryByText('front-pallet.jpg')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reference images' }));

    expect(screen.getByRole('heading', { name: 'Reference images' })).toBeInTheDocument();
    expect(screen.getByText('front-pallet.jpg')).toBeInTheDocument();
    expect(
      screen.getByText(/reference images belong to this inventory and are used for future processing runs only\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/^management$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /close reference images drawer/i })).toBeInTheDocument();
  });
});
