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

vi.mock('../src/api/clientPositionLabelsApi', () => ({
  listClientPositionLabels: (...args: unknown[]) => listMock(...args),
  createClientPositionLabel: (...args: unknown[]) => createMock(...args),
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

  it('shows empty state and create dialog with name field', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('position-label-new')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('position-label-new'));
    expect(screen.getByTestId('position-label-name-input')).toBeInTheDocument();
    expect(screen.queryByLabelText(/inventario/i)).toBeNull();
  });
});
