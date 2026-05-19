import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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

const observabilityData = {
  range: { from: '2026-01-01T00:00:00Z', to: '2026-01-31T00:00:00Z' },
  filters: {},
  totals: { runs_total: 10, runs_succeeded: 8, runs_failed: 2, failure_rate: 0.2 },
  by_client: [],
  by_supplier: [],
  by_provider_model: [
    {
      provider_name: 'gemini',
      model_name: 'flash',
      runs_total: 10,
      runs_succeeded: 8,
      runs_failed: 2,
      failure_rate: 0.2,
    },
  ],
  data_quality: {},
};

const costSummaryData = {
  scope: {},
  totals: {
    jobs_total: 20,
    jobs_with_cost: 18,
    jobs_without_cost: 2,
    total_cost: 24.82,
  },
  by_provider_model: [
    {
      provider_name: 'gemini',
      model_name: 'flash',
      jobs_total: 20,
      jobs_with_cost: 18,
      total_cost: 24.82,
      total_counted_quantity: null,
      cost_per_counted_unit: null,
      average_execution_time_seconds: 180,
    },
  ],
  by_inventory: [],
  by_aisle: [],
  by_capture_status: [],
  warnings: ['PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE'],
};

function setupMocks() {
  mockUseInventoriesList.mockReturnValue({ data: { items: [] }, isError: false });
  mockUseAnalyticsDashboardData.mockReturnValue({
    analytics: { summary: {}, trends: {}, inventoryPerformance: { items: [] }, quality: { items: [] }, aisleIssues: { items: [] } },
    observability: { data: observabilityData, isLoading: false, isError: false, error: null, refetch: vi.fn() },
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

function renderProvidersTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/analitica?tab=proveedores']}>
        <AnalyticsDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMocks();
});

describe('AnalyticsProvidersTab', () => {
  it('renders chart-first layout without default comparison tables', () => {
    renderProvidersTab();
    expect(screen.getByTestId('analytics-providers-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-providers-chart-run-volume-bars')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-providers-chart-cost-bars')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-providers-comparison-cards')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-providers-table')).not.toBeInTheDocument();
    expect(screen.queryByTestId('analytics-providers-cost-table')).not.toBeInTheDocument();
  });

  it('shows informational disclaimer and cost warnings', () => {
    renderProvidersTab();
    expect(screen.getAllByText(/Comparativo informativo/i).length).toBeGreaterThan(0);
    expect(screen.getByTestId('analytics-cost-warnings')).toBeInTheDocument();
    expect(screen.queryByText(/mejor proveedor/i)).not.toBeInTheDocument();
  });
});
