/**
 * Sprint 4.1 — Aisle Results page tests.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AislePositionsPage from '../src/pages/AislePositionsPage';
import type { ResultSummary } from '../src/features/results/types';
import type { PositionSummary } from '../src/api/types';

const mockPositions: PositionSummary[] = [
  {
    id: 'pos-1',
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.9,
    needs_review: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sku: 'SKU-001',
    detected_quantity: 5,
    corrected_quantity: null,
    qty: 5,
    qtySource: 'detected',
    has_evidence: true,
  },
];

const mockResults: ResultSummary[] = [
  {
    id: 'pos-1',
    sku: 'SKU-001',
    detectedQty: 5,
    correctedQty: null,
    resolvedQty: null,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'UNVALIDATED',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    hasEvidence: true,
  },
];

vi.mock('../src/features/results', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/features/results')>();
  return {
    ...actual,
    useResultSummaries: () => ({
      results: mockResults,
      positions: mockPositions,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
  };
});

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => ({
      data: { id: 'inv-1', name: 'Test Inventory', status: 'draft', created_at: null },
      isLoading: false,
      isError: false,
      error: null,
    }),
    useAislesList: () => ({
      data: { items: [{ id: 'aisle-1', code: 'A-01', status: 'created' }] },
      isLoading: false,
      isError: false,
      error: null,
    }),
  };
});

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

describe('AislePositionsPage (Aisle Results)', () => {
  it('shows aisle title, inventory context, and workload KPIs', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'A-01' })).toBeInTheDocument();
    expect(screen.getAllByText('Test Inventory').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Total results')).toBeInTheDocument();
    expect(screen.getByText('Needs review')).toBeInTheDocument();
    expect(screen.getByText('Invalid traceability')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /missing evidence/i })).toBeInTheDocument();
  });

  it('shows operational columns including Priority and Review status', () => {
    renderPage();
    expect(screen.getByRole('columnheader', { name: /priority/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /SKU/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /quantity/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /review status/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /traceability/i })).toBeInTheDocument();
    expect(screen.getByText('SKU-001')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});
