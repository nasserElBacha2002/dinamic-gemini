import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import MetricsPage from '../src/features/analytics/MetricsPage';
import { ApiError } from '../src/api/types';

const mockUseAnalyticsDashboard = vi.fn();

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
  useAnalyticsDashboard: (params: unknown, enabled?: boolean) =>
    mockUseAnalyticsDashboard(params, enabled),
}));

const dashboardLoaded = {
  summary: {
    auto_acceptance_rate: 0.5,
    manual_correction_rate: 0.25,
    invalid_traceability_rate: 0.1,
    processing_success_rate: 0.9,
    average_review_time_seconds: 120,
    settling_actions_per_day: 4,
    notes: [],
    period_day_count: 7,
    settling_actions_count: 10,
    positions_in_scope: 20,
  },
  trends: {
    reviewed_results_over_time: [
      { period: '2026-01-01', reviewed_results: 3, correction_rate: 0.1, processing_success_rate: null },
    ],
    correction_rate_over_time: [],
    processing_success_over_time: [{ period: '2026-01-01', reviewed_results: 2, correction_rate: null, processing_success_rate: 1 }],
  },
  inventoryPerformance: {
    items: [
      {
        inventory_id: 'inv-1',
        inventory_name: 'North DC',
        inventory_created_at: '2026-01-01T00:00:00Z',
        total_aisles: 2,
        total_positions: 10,
        processed_positions: 8,
        review_rate: 0.4,
        correction_rate: 0.1,
        invalid_traceability_rate: 0.05,
        avg_confidence: 0.82,
        processing_success_rate: 0.95,
      },
    ],
  },
  aisleIssues: {
    items: [
      {
        aisle_id: 'a-1',
        aisle_code: 'A-01',
        inventory_id: 'inv-1',
        inventory_name: 'North DC',
        total_results: 5,
        needs_review_count: 2,
        corrected_count: 0,
        invalid_traceability_count: 0,
        low_confidence_count: 1,
        most_common_issue: 'Pending review',
      },
    ],
  },
  quality: {
    items: [{ issue_type: 'Low confidence', count: 2, percentage: 0.4, notes: 'test note' }],
  },
  isLoading: false,
  isError: false,
  errors: [],
  refetchAll: vi.fn(),
};

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
  beforeEach(() => {
    mockUseAnalyticsDashboard.mockReturnValue(dashboardLoaded);
  });

  it('renders heading, settling-actions KPI, and quality copy aligned with backend buckets', () => {
    renderMetrics();
    expect(screen.getByRole('heading', { name: /Metrics & analytics/i })).toBeInTheDocument();
    expect(screen.getByText('Settling actions / day')).toBeInTheDocument();
    expect(screen.getByText('4.0')).toBeInTheDocument();
    expect(
      screen.getByText(/Each position counts once: one primary issue bucket by priority/i)
    ).toBeInTheDocument();
    expect(screen.getByText('Inventory performance')).toBeInTheDocument();
  });

  it('renders KPI percentages from summary', () => {
    renderMetrics();
    expect(screen.getByText('50.0%')).toBeInTheDocument(); // auto_acceptance_rate
  });

  it('shows skeleton KPI band while loading without summary', () => {
    mockUseAnalyticsDashboard.mockReturnValue({
      ...dashboardLoaded,
      summary: undefined,
      isLoading: true,
    });
    const { container } = renderMetrics();
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
    expect(screen.queryByText('Settling actions / day')).not.toBeInTheDocument();
  });

  it('shows error alert when a query fails', () => {
    mockUseAnalyticsDashboard.mockReturnValue({
      ...dashboardLoaded,
      isError: true,
      errors: [new ApiError('Server error', 500)],
    });
    renderMetrics();
    expect(screen.getByText(/Server error|Failed to load metrics/i)).toBeInTheDocument();
  });

  it('renders inventory performance link and aisle issue link', () => {
    renderMetrics();
    const invLink = screen.getByRole('link', { name: 'North DC' });
    expect(invLink).toHaveAttribute('href', '/inventories/inv-1');
    const aisleLink = screen.getByRole('link', { name: 'A-01' });
    expect(aisleLink).toHaveAttribute('href', '/inventories/inv-1/aisles/a-1/positions');
  });

  it('shows empty quality message when there are no pattern rows', () => {
    mockUseAnalyticsDashboard.mockReturnValue({
      ...dashboardLoaded,
      quality: { items: [] },
    });
    renderMetrics();
    expect(screen.getByText('No positions in scope for this filter.')).toBeInTheDocument();
  });

  it('does not expose a redundant Actions column on inventory or aisle analytics tables', () => {
    renderMetrics();
    expect(screen.queryByRole('columnheader', { name: /^Actions$/i })).not.toBeInTheDocument();
  });
});
