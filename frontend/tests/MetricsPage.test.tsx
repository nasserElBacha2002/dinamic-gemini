import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import MetricsPage from '../src/features/analytics/MetricsPage';

vi.mock('../src/hooks/useInventories', () => ({
  useInventoriesList: () => ({
    data: { items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 },
    isLoading: false,
  }),
}));

vi.mock('../src/hooks/useAisles', () => ({
  useAislesList: () => ({
    data: { items: [] },
    isLoading: false,
  }),
}));

vi.mock('../src/features/analytics/hooks', () => ({
  useAnalyticsDashboard: () => ({
    summary: {
      auto_acceptance_rate: 0.5,
      manual_correction_rate: 0.25,
      invalid_traceability_rate: 0.1,
      processing_success_rate: 0.9,
      average_review_time_seconds: 120,
      reviewed_results_per_day: 4,
      notes: [],
      period_day_count: 7,
      settling_actions_count: 10,
      positions_in_scope: 20,
    },
    trends: {
      reviewed_results_over_time: [{ period: '2026-01-01', reviewed_results: 3, correction_rate: 0.1, processing_success_rate: null }],
      correction_rate_over_time: [],
      processing_success_over_time: [],
    },
    inventoryPerformance: { items: [] },
    aisleIssues: { items: [] },
    quality: { items: [] },
    isLoading: false,
    isError: false,
    errors: [],
    refetchAll: vi.fn(),
  }),
}));

function renderMetrics() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MetricsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('MetricsPage', () => {
  it('renders heading and KPI cards', () => {
    renderMetrics();
    expect(screen.getByRole('heading', { name: /Metrics & analytics/i })).toBeInTheDocument();
    expect(screen.getByText('Auto acceptance rate')).toBeInTheDocument();
    expect(screen.getByText('Inventory performance')).toBeInTheDocument();
  });
});
