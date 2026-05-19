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
  summary: {
    auto_acceptance_rate: 0.5,
    manual_correction_rate: 0.25,
    processed_positions_count: 16,
    reviewed_positions_count: 8,
    total_positions_in_scope: 20,
    notes: ['NOTE_TEST'],
  },
  quality: {
    items: [
      { issue_type: 'pending_review', count: 5, percentage: 0.5 },
      { issue_type: 'no_primary_issue', count: 2, percentage: 0.2 },
    ],
  },
  manualInterventions: {
    items: [
      { category: 'confirmed', count: 4, available: true, percentage: 0.5 },
      { category: 'qty_corrected', count: 2, available: true, percentage: 0.25 },
    ],
    reviewed_positions_count: 8,
    intervention_positions_count: 2,
  },
  aisleIssues: {
    items: [
      {
        aisle_id: 'a-1',
        aisle_code: 'A-01',
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        needs_review_count: 10,
        most_common_issue: 'Pending review',
      },
      {
        aisle_id: 'a-2',
        aisle_code: 'A-02',
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        needs_review_count: 3,
        most_common_issue: 'Zero quantity',
      },
    ],
  },
  trends: { reviewed_results_over_time: [], correction_rate_over_time: [], processing_success_over_time: [] },
  inventoryPerformance: { items: [] },
};

const observabilityData = {
  range: { from: '2026-01-01T00:00:00Z', to: '2026-01-31T00:00:00Z' },
  filters: {},
  totals: { runs_total: 1, runs_succeeded: 1, runs_failed: 0, failure_rate: 0 },
  by_client: [],
  by_supplier: [],
  by_provider_model: [],
  data_quality: {},
};

const costSummaryData = {
  scope: {},
  totals: { jobs_total: 0, jobs_with_cost: 0, total_cost: 0 },
  by_provider_model: [],
  by_inventory: [],
  by_aisle: [],
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

function renderQualityTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/analitica?tab=calidad']}>
        <AnalyticsDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMocks();
});

describe('AnalyticsQualityTab visual dashboard', () => {
  it('renders visual dashboard sections on Calidad tab', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-quality-panel-overview')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-quality-panel-resolution')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-quality-panel-issues')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-quality-panel-aisles')).toBeInTheDocument();
  });

  it('does not render the legacy aisle attention data table', () => {
    renderQualityTab();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/buscar pasillo/i)).not.toBeInTheDocument();
  });

  it('shows aisle attention as ranking with max 5 rows', () => {
    renderQualityTab();
    const ranking = screen.getByTestId('analytics-quality-aisle-ranking');
    const aisleCards = within(ranking).queryAllByTestId(/^analytics-quality-aisle-/);
    expect(aisleCards.length).toBeLessThanOrEqual(5);
    expect(aisleCards.length).toBeGreaterThan(0);
    expect(within(ranking).getByText(/A-01/i)).toBeInTheDocument();
  });

  it('shows manual intervention as segmented bar chart', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-manual-chart')).toBeInTheDocument();
  });

  it('shows resolution flow as funnel visual', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-resolution-funnel')).toBeInTheDocument();
    expect(screen.queryByText('Flujo de resolución')).not.toBeInTheDocument();
  });

  it('shows quality patterns as horizontal bars', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-issues-bars')).toBeInTheDocument();
  });

  it('labels pending review honestly', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-overview-kpi-pending')).toHaveTextContent('Pendientes de revisión');
    expect(screen.queryByText(/correcciones realizadas/i)).not.toBeInTheDocument();
    expect(screen.getByText(/10 pendientes/i)).toBeInTheDocument();
  });

  it('opens aisle drilldown from attention ranking', () => {
    renderQualityTab();
    fireEvent.click(screen.getByTestId('quality-aisle-drilldown-a-1'));
    expect(screen.getByTestId('analytics-drilldown-drawer')).toBeInTheDocument();
  });

  it('shows compare link when inventory is test mode', () => {
    renderQualityTab();
    const compare = screen.getByTestId('quality-aisle-compare-a-1');
    expect(compare).toHaveAttribute('href', '/inventories/inv-test/analytics/compare-many?aisleId=a-1');
  });

  it('shows quality overview donut', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-overview-donut')).toBeInTheDocument();
  });

  it('shows warnings when summary notes exist', () => {
    renderQualityTab();
    expect(screen.getByTestId('analytics-quality-warnings')).toBeInTheDocument();
  });

  it('links to aisles tab for tabular detail', () => {
    renderQualityTab();
    const cta = screen.getByTestId('analytics-quality-panel-aisles-cta');
    expect(cta).toHaveAttribute('href', expect.stringContaining('tab=pasillos'));
  });
});
