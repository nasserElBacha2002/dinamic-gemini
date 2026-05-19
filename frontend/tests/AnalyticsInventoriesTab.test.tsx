import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
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
  summary: { auto_acceptance_rate: 0.5 },
  trends: { reviewed_results_over_time: [] },
  inventoryPerformance: {
    items: [
      {
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        inventory_created_at: '2026-01-01T00:00:00Z',
        total_positions: 10,
        processed_positions: 8,
        auto_acceptance_rate: 0.6,
        average_processing_time_minutes: 5,
        processing_success_rate: 0.95,
      },
    ],
  },
  quality: { items: [] },
  aisleIssues: { items: [] },
};

const costSummaryData = {
  scope: {},
  totals: { jobs_total: 20, jobs_with_cost: 18, jobs_without_cost: 2, total_cost: 24.82 },
  by_inventory: [
    {
      inventory_id: 'inv-test',
      inventory_name: 'Test DC',
      jobs_total: 15,
      jobs_with_cost: 14,
      total_cost: 20.5,
      total_counted_quantity: 1000,
      cost_per_counted_unit: 0.0205,
      total_execution_time_seconds: 3000,
    },
  ],
  by_provider_model: [],
  by_aisle: [],
  by_capture_status: [],
  warnings: [],
};

function setupMocks(overrides: Record<string, unknown> = {}) {
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
    ...overrides,
  });
}

function renderInventoriesTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/analitica?tab=inventarios']}>
        <AnalyticsDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMocks();
});

describe('AnalyticsInventoriesTab', () => {
  it('renders ranking cards instead of a primary data table', () => {
    renderInventoriesTab();
    expect(screen.getByTestId('analytics-inventories-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-inventories-ranking')).toBeInTheDocument();
    expect(within(screen.getByTestId('analytics-inventories-ranking')).getByText('Test DC')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('opens inventory drilldown from ranking card action', () => {
    renderInventoriesTab();
    fireEvent.click(screen.getByTestId('inventory-drilldown-inv-test'));
    expect(screen.getByTestId('analytics-drilldown-drawer')).toBeInTheDocument();
  });

  it('shows compare link for test inventory', () => {
    renderInventoriesTab();
    const compare = screen.getByTestId('inventory-compare-inv-test');
    expect(compare).toHaveAttribute('href', '/inventories/inv-test/analytics/compare-many');
  });
});
