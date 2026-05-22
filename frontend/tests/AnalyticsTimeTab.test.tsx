import '@testing-library/jest-dom/vitest';
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

const analyticsLoaded = {
  summary: {
    average_processing_time_minutes: 2,
    average_processing_time_seconds: 120,
  },
  trends: { reviewed_results_over_time: [{ period: '2026-01-01', reviewed_results: 3 }] },
  inventoryPerformance: {
    items: [
      {
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        average_processing_time_minutes: 9.5,
        processing_success_rate: 0.95,
        processed_positions: 8,
      },
      {
        inventory_id: 'inv-fast',
        inventory_name: 'Fast DC',
        average_processing_time_minutes: 2,
        processing_success_rate: 0.9,
        processed_positions: 4,
      },
    ],
  },
  quality: { items: [] },
  manualInterventions: { items: [], intervention_positions_count: 0 },
  aisleIssues: { items: [] },
};

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

function setupMocks() {
  mockUseInventoriesList.mockReturnValue({ data: { items: [] }, isError: false });
  mockUseAnalyticsDashboardData.mockReturnValue({
    analytics: analyticsLoaded,
    observability: { data: observabilityData, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    costSummary: { data: null, isLoading: false, isError: false, error: null, refetch: vi.fn() },
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

function renderTimeTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/analitica?tab=tiempos']}>
        <AnalyticsDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMocks();
});

describe('AnalyticsTimeTab', () => {
  it('renders visual sections without default inventory/provider tables', () => {
    renderTimeTab();
    expect(screen.getByTestId('analytics-time-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-time-overview-kpis')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-time-chart-inventory-bars')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-time-chart-trend')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-time-chart-provider-bars')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-time-inventories-table')).not.toBeInTheDocument();
    expect(screen.queryByTestId('analytics-time-provider-table')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
