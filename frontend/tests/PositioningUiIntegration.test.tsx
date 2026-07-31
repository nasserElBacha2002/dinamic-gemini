/**
 * Positioning UI — client-scoped labels + inventory hub redirect.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AppSnackbarProvider } from '../src/components/ui';
import ClientPositionLabelsPage from '../src/pages/ClientPositionLabelsPage';
import InventoryPhysicalLocationsHubPage from '../src/pages/InventoryPhysicalLocationsHubPage';
import {
  pathToClientPhysicalLocations,
  pathToInventoryPhysicalLocations,
} from '../src/constants/appRoutes';

const inventoryDetailState = vi.hoisted(() => ({
  data: {
    id: 'inv-1',
    name: 'Inventario Central',
    client_id: 'client-1',
    status: 'active',
    processing_mode: 'production',
  },
  isLoading: false,
  isError: false,
  error: null as unknown,
  refetch: vi.fn(),
}));

const clientState = vi.hoisted(() => ({
  data: { id: 'client-1', name: 'Blestein' },
  isLoading: false,
  isError: false,
}));

const navigateMock = vi.hoisted(() => vi.fn());

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../src/hooks', () => ({
  useInventoryDetail: () => inventoryDetailState,
  useClient: () => clientState,
}));

vi.mock('../src/features/positionLabels/positionLabelCapabilities', () => ({
  getPositionLabelUiCapabilities: () => ({ labelsEnabled: true, renderEnabled: true }),
}));

const listMock = vi.fn();

vi.mock('../src/api/clientPositionLabelsApi', () => ({
  listClientPositionLabels: (...args: unknown[]) => listMock(...args),
  createClientPositionLabel: vi.fn(),
  downloadClientPositionLabelFile: vi.fn(),
  fetchClientPositionLabelPreviewBlob: vi.fn(async () => new Blob(['png'], { type: 'image/png' })),
  invalidateClientPositionLabel: vi.fn(),
}));

function renderAt(path: string, element: ReactNode, routePath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={routePath} element={element} />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('client-scoped positioning UI', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    listMock.mockReset();
    listMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, total_pages: 0 });
  });

  it('inventory hub redirects to client position labels', async () => {
    renderAt(
      pathToInventoryPhysicalLocations('inv-1'),
      <InventoryPhysicalLocationsHubPage />,
      '/inventories/:inventoryId/posiciones-fisicas'
    );
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith(pathToClientPhysicalLocations('client-1'), {
        replace: true,
      });
    });
  });

  it('client page has no inventory/aisle selectors and shows create CTA', async () => {
    renderAt(
      pathToClientPhysicalLocations('client-1'),
      <ClientPositionLabelsPage />,
      '/clientes/:clientId/posiciones-fisicas'
    );
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(screen.queryByTestId('client-hub-inventory-select')).toBeNull();
    expect(screen.queryByText(/Elegí un inventario/i)).toBeNull();
    expect(screen.getByTestId('position-label-new')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('position-label-new'));
    expect(screen.getByTestId('position-label-name-input')).toBeInTheDocument();
  });
});
