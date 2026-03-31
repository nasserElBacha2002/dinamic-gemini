/**
 * Sprint 4.2 — Review Queue page structure and contracts.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import ReviewQueuePage from '../src/pages/ReviewQueuePage';
import { AppSnackbarProvider } from '../src/components/ui';

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
        items: [
          {
            inventory_id: 'inv-1',
            inventory_name: 'Test Inv',
            aisle_code: 'A-01',
            position: {
              id: 'pos-1',
              aisle_id: 'aisle-1',
              status: 'detected',
              confidence: 0.7,
              needs_review: true,
              primary_evidence_id: 'ev-1',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              sku: '',
              detected_quantity: 1,
              corrected_quantity: null,
              qty: 1,
              qtySource: 'detected',
              has_evidence: true,
              product: {
                sku: 'SKU-QUEUE-1',
                identity_source: 'primary_product',
              },
              quantity: {
                detected: 1,
                corrected: null,
                final: 1,
                source: 'detected',
                resolved: true,
              },
              traceability: {
                status: 'valid',
                has_evidence: true,
                primary_evidence_id: 'ev-1',
              },
            },
          },
        ],
        page: 1,
        page_size: 25,
        total_items: 1,
        total_pages: 1,
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
      <AppSnackbarProvider>
        <MemoryRouter>
          <ReviewQueuePage />
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('ReviewQueuePage', () => {
  it('renders header, KPI band, filters region, and queue table', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /review queue/i })).toBeInTheDocument();
    expect(screen.getByText('Pending review')).toBeInTheDocument();
    expect(screen.getByText('Invalid traceability')).toBeInTheDocument();
    expect(screen.getByText('Missing evidence')).toBeInTheDocument();
    expect(screen.getByLabelText(/filters/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Prioritized results' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /priority/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /SKU/i })).toBeInTheDocument();
  });

  it('uses SKU review button as primary navigation (no Actions column)', () => {
    renderPage();
    expect(screen.queryByRole('columnheader', { name: /^Actions$/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Review SKU-QUEUE-1/i })).toBeInTheDocument();
  });

  it('shows validation errors on both confidence fields when min > max', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/Min confidence/i), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText(/Max confidence/i), { target: { value: '0.1' } });
    expect(screen.getByText(/Cannot be greater than max/i)).toBeInTheDocument();
    expect(screen.getByText(/Must be greater than or equal to min/i)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Min confidence/i })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('textbox', { name: /Max confidence/i })).toHaveAttribute('aria-invalid', 'true');
  });
});
