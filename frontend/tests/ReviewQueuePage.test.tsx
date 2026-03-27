/**
 * Sprint 4.2 — Review Queue page structure and contracts.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import ReviewQueuePage from '../src/pages/ReviewQueuePage';

const mockRefetch = vi.fn();

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoriesList: () => ({
      data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
      isLoading: false,
      isError: false,
      error: null,
    }),
    useAislesList: () => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
    }),
    useReviewQueue: () => ({
      data: {
        summary: {
          pending_review: 2,
          low_confidence: 1,
          invalid_traceability: 0,
          qty_zero: 1,
          missing_evidence: 1,
        },
        items: [],
        page: 1,
        page_size: 25,
        total_items: 0,
        total_pages: 0,
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    }),
  };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReviewQueuePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ReviewQueuePage', () => {
  it('renders header, KPI band, filters region, and queue table', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Review Queue' })).toBeInTheDocument();
    expect(screen.getByText('Pending review')).toBeInTheDocument();
    expect(screen.getByText('Invalid traceability')).toBeInTheDocument();
    expect(screen.getByText('Missing evidence')).toBeInTheDocument();
    expect(screen.getByLabelText(/filters/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Prioritized results' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /priority/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /SKU/i })).toBeInTheDocument();
  });
});
