import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import InventoryDetail from '../src/pages/InventoryDetail';
import { AppSnackbarProvider } from '../src/components/ui';

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
    useInventoryVisualReferences: () => ({
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
    }),
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
  it('keeps the page focused on header, reference images, and aisles', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Inventory One' })).toBeInTheDocument();
    expect(screen.getByText('Reference images')).toBeInTheDocument();
    expect(screen.getByText('Aisles')).toBeInTheDocument();

    expect(screen.queryByText('Total aisles')).not.toBeInTheDocument();
    expect(screen.queryByText('Review completion rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Logs summary')).not.toBeInTheDocument();
  });

  it('renders real inventory reference data from the existing contract', () => {
    renderPage();

    expect(screen.getByText('front-pallet.jpg')).toBeInTheDocument();
    expect(screen.getByText(/future processing runs only/i)).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Aisle code/i })).toBeInTheDocument();
    expect(screen.getByText('A-01')).toBeInTheDocument();
  });
});
