import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsDashboardPage from '../src/features/analytics-dashboard/AnalyticsDashboardPage';

const mockUseAnalyticsDashboardData = vi.fn();
const mockUseInventoriesList = vi.fn();

vi.mock('../src/features/analytics-dashboard/hooks/useAnalyticsDashboardData', () => ({
  useAnalyticsDashboardData: (...args: unknown[]) => mockUseAnalyticsDashboardData(...args),
}));

vi.mock('../src/hooks/useInventories', () => ({
  useInventoriesList: (...args: unknown[]) => mockUseInventoriesList(...args),
}));

vi.mock('../src/hooks/useAisles', () => ({
  useAislesList: () => ({ data: { items: [] }, isLoading: false }),
  useAisleJobsList: () => ({ data: { jobs: [] }, isLoading: false, isError: false }),
  useInventoryMetrics: () => ({ data: null, isLoading: false, isError: false }),
}));

const analyticsLoaded = {
  summary: {},
  trends: { reviewed_results_over_time: [] },
  inventoryPerformance: { items: [] },
  quality: { items: [] },
  aisleIssues: {
    items: [
      {
        aisle_id: 'a-1',
        aisle_code: 'A-01',
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        needs_review_count: 10,
        total_results: 5,
        most_common_issue: 'Pending review',
      },
    ],
  },
};

const costSummaryData = {
  scope: {},
  totals: { jobs_total: 5, jobs_with_cost: 5, total_cost: 5.5 },
  by_aisle: [
    {
      inventory_id: 'inv-test',
      inventory_name: 'Test DC',
      aisle_id: 'a-1',
      aisle_code: 'A-01',
      jobs_total: 5,
      jobs_with_cost: 5,
      total_cost: 5.5,
      total_counted_quantity: 250,
      cost_per_counted_unit: 0.022,
      total_execution_time_seconds: 600,
    },
  ],
  by_provider_model: [],
  by_inventory: [],
  by_capture_status: [],
  warnings: [],
};

function setupMocks() {
  mockUseInventoriesList.mockReturnValue({
    data: { items: [{ id: 'inv-test', name: 'Test DC', processing_mode: 'test' }] },
    isError: false,
  });
  mockUseAnalyticsDashboardData.mockReturnValue({
    analytics: analyticsLoaded,
    observability: { data: { by_provider_model: [], totals: {}, range: {}, filters: {}, by_client: [], by_supplier: [], data_quality: {} }, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    costSummary: { data: costSummaryData, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    isLoading: false,
    isAnalyticsLoading: false,
    isObservabilityLoading: false,
    isCostSummaryLoading: false,
    analyticsError: null,
    observabilityError: null,
    costSummaryError: null,
    hasPartialFailure: false,
    hasMixedLoadedData: false,
    refetchAll: vi.fn(),
  });
}

function renderAislesTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/analitica?tab=pasillos']}>
        <AnalyticsDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMocks();
});

describe('AnalyticsAislesTab', () => {
  it('renders visual ranking instead of a primary data table', () => {
    renderAislesTab();
    expect(screen.getByTestId('analytics-aisles-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-aisles-ranking')).toBeInTheDocument();
    expect(screen.getByText('A-01')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('opens aisle drilldown from ranking card', () => {
    renderAislesTab();
    fireEvent.click(screen.getByTestId('aisle-drilldown-a-1'));
    expect(screen.getByTestId('analytics-drilldown-aisle-panel')).toBeInTheDocument();
  });

  it('shows compare link when eligible', () => {
    renderAislesTab();
    expect(screen.getByTestId('aisle-compare-a-1')).toHaveAttribute(
      'href',
      '/inventories/inv-test/analytics/compare-many?aisleId=a-1'
    );
  });
});
