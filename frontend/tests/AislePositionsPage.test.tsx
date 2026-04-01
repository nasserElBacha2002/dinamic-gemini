/**
 * Sprint 4.1 — Aisle Results page tests.
 */

import React from 'react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AislePositionsPage from '../src/pages/AislePositionsPage';
import { AppSnackbarProvider } from '../src/components/ui';
import type { ResultSummary } from '../src/features/results/types';
import type { PositionSummary } from '../src/api/types';

const { useRunAisleMergeMock } = vi.hoisted(() => ({
  useRunAisleMergeMock: vi.fn(),
}));
const { resultSummariesState } = vi.hoisted(() => ({
  resultSummariesState: {
    results: [] as ResultSummary[],
    positions: [] as PositionSummary[],
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
}));
const { aislesListState } = vi.hoisted(() => ({
  aislesListState: {
    data: { items: [{ id: 'aisle-1', code: 'A-01', status: 'created' }] },
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
}));

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
      ...resultSummariesState,
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
    useAislesList: () => aislesListState,
    useRunAisleMerge: useRunAisleMergeMock,
  };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={['/inventories/inv-1/aisles/aisle-1/positions']}>
          <Routes>
            <Route
              path="/inventories/:inventoryId/aisles/:aisleId/positions"
              element={<AislePositionsPage />}
            />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('AislePositionsPage (Aisle Results)', () => {
  beforeEach(() => {
    resultSummariesState.results = mockResults;
    resultSummariesState.positions = mockPositions;
    resultSummariesState.isLoading = false;
    resultSummariesState.isError = false;
    resultSummariesState.error = null;
    resultSummariesState.refetch = vi.fn();
    aislesListState.refetch = vi.fn();
    useRunAisleMergeMock.mockReset();
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({
        operation_mode: 'manual_authoritative',
        authoritative_quantity_updated: true,
        raw_count: 3,
        normalized_count: 1,
        final_count: 1,
        product_records_updated: 1,
      }),
      isPending: false,
    });
  });

  it('shows aisle title, inventory context, and workload KPIs', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'A-01' })).toBeTruthy();
    expect(screen.getAllByText('Test Inventory')).toHaveLength(2);
    expect(screen.getByText('Counted total')).toBeTruthy();
    expect(screen.getByRole('button', { name: /merge repeated labels/i })).toBeTruthy();
  });

  it('shows operational columns including Priority and Review status', () => {
    renderPage();
    expect(screen.getByRole('columnheader', { name: /priority/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /SKU/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /quantity/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /review status/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /traceability/i })).toBeTruthy();
    expect(screen.getByText('SKU-001')).toBeTruthy();
    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
  });

  it('opens review via SKU control without an Actions column', () => {
    renderPage();
    expect(screen.queryByRole('columnheader', { name: /^Actions$/i })).toBeNull();
    expect(screen.getByRole('button', { name: /Review SKU-001/i })).toBeTruthy();
  });

  it('runs manual merge from the header and refreshes the visible results queries', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      operation_mode: 'manual_authoritative',
      authoritative_quantity_updated: true,
      raw_count: 3,
      normalized_count: 1,
      final_count: 1,
      product_records_updated: 1,
    });
    const resultsRefetch = vi.fn().mockResolvedValue(undefined);
    const aislesRefetch = vi.fn().mockResolvedValue(undefined);
    resultSummariesState.refetch = resultsRefetch;
    aislesListState.refetch = aislesRefetch;
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /merge repeated labels/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith('aisle-1');
      expect(resultsRefetch).toHaveBeenCalled();
      expect(aislesRefetch).toHaveBeenCalled();
    });
  });

  it('shows a disabled pending merge button while the merge mutation is running', () => {
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
    });

    renderPage();

    const button = screen.getByRole('button', { name: /merging/i });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Merging…');
  });

  it('hides merge action when there are no results to consolidate', () => {
    resultSummariesState.results = [];
    resultSummariesState.positions = [];

    renderPage();

    expect(screen.queryByRole('button', { name: /merge repeated labels/i })).toBeNull();
  });
});
