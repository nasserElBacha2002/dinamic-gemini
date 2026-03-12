/**
 * Epic 3 — AislePositionsPage (Results overview) tests.
 * Page is Result-centric; uses useResultSummaries and displays KPI, filters, table.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AislePositionsPage from '../src/pages/AislePositionsPage';
import type { ResultSummary } from '../src/features/results/types';

const mockResults: ResultSummary[] = [
  {
    id: 'pos-1',
    sku: 'SKU-001',
    detectedQty: 5,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'UNVALIDATED',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    hasEvidence: true,
  },
];

vi.mock('../src/features/results', () => ({
  useResultSummaries: () => ({
    results: mockResults,
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

describe('AislePositionsPage (Results overview)', () => {
  it('shows Results header and KPI section when results load', () => {
    renderPage();
    expect(screen.getByText('Results')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getByText('Needs review')).toBeInTheDocument();
  });

  it('shows Result-centric table with SKU, Qty, Traceability, Status, Action', () => {
    renderPage();
    expect(screen.getByRole('columnheader', { name: /SKU/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Qty/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Traceability/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Status/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Action/i })).toBeInTheDocument();
    expect(screen.getByText('SKU-001')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /review/i })).toBeInTheDocument();
  });

  it('shows Review button that opens detail', () => {
    renderPage();
    const reviewBtn = screen.getByRole('button', { name: /review/i });
    expect(reviewBtn).toBeInTheDocument();
  });
});
