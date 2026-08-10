/**
 * Client position labels page — no inventory/aisle selectors.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppSnackbarProvider } from '../src/components/ui';
import ClientPositionLabelsPage from '../src/pages/ClientPositionLabelsPage';

vi.mock('../src/hooks', () => ({
  useClient: () => ({
    data: { id: 'c1', name: 'Blestein' },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('../src/features/positionLabels/positionLabelCapabilities', () => ({
  getPositionLabelUiCapabilities: () => ({ labelsEnabled: true, renderEnabled: true }),
}));

const listMock = vi.fn();
const createMock = vi.fn();
const createMarkerSetMock = vi.fn();

vi.mock('../src/api/clientPositionLabelsApi', () => ({
  listClientPositionLabels: (...args: unknown[]) => listMock(...args),
  createClientPositionLabel: (...args: unknown[]) => createMock(...args),
  createClientPositionMarkerSet: (...args: unknown[]) => createMarkerSetMock(...args),
  downloadClientPositionLabelFile: vi.fn(),
  fetchClientPositionLabelPreviewBlob: vi.fn(async () => new Blob(['x'], { type: 'image/png' })),
  invalidateClientPositionLabel: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={['/clientes/c1/posiciones-fisicas']}>
          <Routes>
            <Route
              path="/clientes/:clientId/posiciones-fisicas"
              element={<ClientPositionLabelsPage />}
            />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('ClientPositionLabelsPage', () => {
  beforeEach(() => {
    listMock.mockReset();
    createMock.mockReset();
    createMarkerSetMock.mockReset();
    listMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, total_pages: 0 });
  });

  it('opens from client route without inventory or aisle selectors', async () => {
    renderPage();
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(screen.queryByLabelText(/inventario/i)).toBeNull();
    expect(screen.queryByLabelText(/pasillo/i)).toBeNull();
    expect(screen.queryByText(/Elegí un inventario/i)).toBeNull();
    expect(screen.getByTestId('position-label-new')).toBeInTheDocument();
  });

  it('shows empty state and create dialog with hierarchy fields by default', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('position-label-new')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('position-label-new'));
    expect(screen.getByTestId('position-label-pallet-input')).toBeInTheDocument();
    expect(screen.queryByLabelText(/inventario/i)).toBeNull();
  });

  it('lists labels without crashing snackbar helpers', async () => {
    listMock.mockResolvedValue({
      items: [
        {
          id: 'lbl-1',
          public_identifier: 'DINAMIC_POSITION:x',
          client_id: 'c1',
          name: '01',
          description: null,
          status: 'ACTIVE',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          available_formats: ['PNG', 'PDF'],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
      total_pages: 1,
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('position-labels-table')).toBeInTheDocument());
    expect(screen.getByText('01')).toBeInTheDocument();
    expect(screen.queryByText(/No se pudieron cargar/i)).toBeNull();
  });

  it('creates marker-set with stable Idempotency-Key and previews 01/03…03/03', async () => {
    createMarkerSetMock.mockResolvedValue({
      items: [
        {
          id: 'a',
          public_identifier: 'p1',
          client_id: 'c1',
          name: 'P12 LEFT N3 01/03',
          description: null,
          status: 'ACTIVE',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          available_formats: ['PNG'],
          marker: '01/03',
          marker_index: 1,
          marker_total: 3,
        },
        {
          id: 'b',
          public_identifier: 'p2',
          client_id: 'c1',
          name: 'P12 LEFT N3 02/03',
          description: null,
          status: 'ACTIVE',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          available_formats: ['PNG'],
          marker: '02/03',
          marker_index: 2,
          marker_total: 3,
        },
        {
          id: 'c',
          public_identifier: 'p3',
          client_id: 'c1',
          name: 'P12 LEFT N3 03/03',
          description: null,
          status: 'ACTIVE',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          available_formats: ['PNG'],
          marker: '03/03',
          marker_index: 3,
          marker_total: 3,
        },
      ],
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('position-label-new')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('position-label-new'));
    fireEvent.change(screen.getByTestId('position-label-pallet-input'), {
      target: { value: 'P12' },
    });
    fireEvent.change(screen.getByTestId('position-label-marker-total-input'), {
      target: { value: '3' },
    });
    fireEvent.click(screen.getByTestId('position-label-create-submit'));
    await waitFor(() => expect(createMarkerSetMock).toHaveBeenCalled());
    const [, , opts] = createMarkerSetMock.mock.calls[0];
    expect(opts?.idempotencyKey).toMatch(/^pos-marker-set-/);
    await waitFor(() => expect(screen.getByTestId('position-label-result-set')).toBeInTheDocument());
    const markers = screen.getAllByTestId('position-label-result-set-marker').map((el) => el.textContent);
    expect(markers.some((m) => m?.includes('01/03'))).toBe(true);
    expect(markers.some((m) => m?.includes('02/03'))).toBe(true);
    expect(markers.some((m) => m?.includes('03/03'))).toBe(true);
  });
});
