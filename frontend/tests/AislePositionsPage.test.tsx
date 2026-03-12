/**
 * Epic 3.1.B — AislePositionsPage traceability fallback test.
 * Ensures positions without traceability_status render "—" in Traceability column.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AislePositionsPage from '../src/pages/AislePositionsPage';

const mockPositions = [
  {
    id: 'pos-1',
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.9,
    needs_review: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    source_image_id: undefined,
    traceability_status: undefined,
  },
];

vi.mock('../src/hooks', () => ({
  useAislePositions: (inventoryId: string, aisleId: string) => ({
    data: inventoryId && aisleId ? { positions: mockPositions } : undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/inventories/inv-1/aisles/aisle-1/positions']}>
        <Routes>
          <Route
            path="/inventories/:inventoryId/aisles/:aisleId/positions"
            element={<AislePositionsPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AislePositionsPage traceability fallback', () => {
  it('shows em dash in Traceability column when traceability_status is absent', async () => {
    renderPage();
    await screen.findByText(/pos-1/);
    const cells = screen.getAllByRole('cell');
    const dashCells = cells.filter((c) => c.textContent === '—');
    expect(dashCells.length).toBeGreaterThanOrEqual(1);
  });
});
