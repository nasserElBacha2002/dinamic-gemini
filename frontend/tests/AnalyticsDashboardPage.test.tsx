import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsDashboardPage from '../src/features/analytics-dashboard/AnalyticsDashboardPage';

const mockUseAnalyticsDashboardData = vi.fn();
const mockUseInventoriesList = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../src/features/analytics-dashboard/hooks/useAnalyticsDashboardData', () => ({
  useAnalyticsDashboardData: (...args: unknown[]) => mockUseAnalyticsDashboardData(...args),
}));

vi.mock('../src/hooks/useInventories', () => ({
  useInventoriesList: (...args: unknown[]) => mockUseInventoriesList(...args),
}));

vi.mock('../src/hooks/useAisles', () => ({
  useAislesList: () => ({
    data: { items: [{ id: 'a-1', code: 'A-01' }] },
    isLoading: false,
  }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const analyticsLoaded = {
  summary: {
    auto_acceptance_rate: 0.5,
    manual_correction_rate: 0.25,
    unidentified_product_rate: 0.15,
    invalid_traceability_rate: 0.1,
    processing_success_rate: 0.9,
    average_processing_time_seconds: 120,
    average_processing_time_minutes: 2,
    processed_positions_count: 16,
    reviewed_positions_count: 8,
    total_positions_in_scope: 20,
    notes: [],
  },
  trends: {
    reviewed_results_over_time: [{ period: '2026-01-01', reviewed_results: 3 }],
    correction_rate_over_time: [],
    processing_success_over_time: [],
  },
  inventoryPerformance: {
    items: [
      {
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        inventory_created_at: '2026-01-01T00:00:00Z',
        total_positions: 10,
        processed_positions: 8,
        auto_acceptance_rate: 0.6,
        manual_correction_rate: 0.1,
        unidentified_product_rate: 0.2,
        invalid_traceability_rate: 0.05,
        average_processing_time_minutes: 9.5,
        processing_success_rate: 0.95,
      },
      {
        inventory_id: 'inv-prod',
        inventory_name: 'Prod DC',
        inventory_created_at: '2026-01-02T00:00:00Z',
        total_positions: 5,
        processed_positions: 4,
        auto_acceptance_rate: 0.4,
        manual_correction_rate: 0.2,
        unidentified_product_rate: 0.1,
        invalid_traceability_rate: 0.02,
        average_processing_time_minutes: 5,
        processing_success_rate: 0.8,
      },
    ],
  },
  aisleIssues: {
    items: [
      {
        aisle_id: 'a-1',
        aisle_code: 'A-01',
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        total_results: 5,
        needs_review_count: 2,
        corrected_count: 0,
        unidentified_product_count: 1,
        invalid_traceability_count: 0,
        most_common_issue: 'Pending review',
      },
    ],
  },
  quality: { items: [{ issue_type: 'pending_review', count: 2, share: 0.4 }] },
  manualInterventions: {
    items: [{ category: 'qty_corrected', count: 1, available: true }],
    reviewed_positions_count: 8,
    intervention_positions_count: 1,
  },
  isLoading: false,
  isError: false,
  errors: [],
  refetchAll: vi.fn(),
};

const observabilityData = {
  range: { from: '2026-01-01T00:00:00Z', to: '2026-01-31T00:00:00Z' },
  filters: {},
  totals: {
    runs_total: 10,
    runs_succeeded: 8,
    runs_failed: 2,
    failure_rate: 0.2,
    fallback_runs: 1,
    missing_prompt_config_runs: 1,
    missing_reference_runs: 2,
    legacy_runs: 1,
  },
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
  data_quality: {
    jobs_with_audit_snapshot: 9,
    jobs_without_audit_snapshot: 1,
    jobs_with_missing_metadata: 0,
    artifact_dependent_jobs: 0,
  },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnalyticsDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function setupMocks() {
  mockUseInventoriesList.mockReturnValue({
    data: {
      items: [
        { id: 'inv-test', name: 'Test DC', processing_mode: 'test' },
        { id: 'inv-prod', name: 'Prod DC', processing_mode: 'production' },
      ],
    },
    isError: false,
  });
  mockUseAnalyticsDashboardData.mockReturnValue({
    analytics: analyticsLoaded,
    observability: { data: observabilityData, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    isLoading: false,
    isAnalyticsLoading: false,
    isObservabilityLoading: false,
    analyticsError: null,
    observabilityError: null,
    hasPartialData: false,
    refetchAll: vi.fn(),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMocks();
});

describe('AnalyticsDashboardPage', () => {
  it('renders title Analítica', () => {
    renderPage();
    expect(screen.getByTestId('analytics-dashboard-title')).toHaveTextContent('Analítica');
  });

  it('renders all tabs', () => {
    renderPage();
    const tabs = ['summary', 'quality', 'time', 'providers', 'inventories', 'aisles', 'compare', 'costs'];
    for (const tab of tabs) {
      expect(screen.getByTestId(`analytics-tab-${tab}`)).toBeInTheDocument();
    }
    expect(screen.getByRole('tab', { name: 'Resumen' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Costos' })).toBeInTheDocument();
  });

  it('renders KPI cards from analytics mocked data', () => {
    renderPage();
    expect(screen.getByText('Posiciones procesadas')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('Tasa de autoaceptación')).toBeInTheDocument();
  });

  it('renders KPI cards from observability mocked data', () => {
    renderPage();
    expect(screen.getByText('Procesamientos')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('Tasa de error')).toBeInTheDocument();
  });

  it('shows unavailable state for global cost metrics', () => {
    renderPage();
    expect(screen.getByTestId('global-cost-unavailable-note')).toBeInTheDocument();
    expect(screen.getAllByText('Pendiente de backend').length).toBeGreaterThan(0);
    expect(screen.getByText('Costo total')).toBeInTheDocument();
  });

  it('does not show fake global cost values', () => {
    renderPage();
    const body = document.body.textContent ?? '';
    expect(body).not.toMatch(/\$[\d,]+/);
    expect(body).not.toMatch(/USD\s*[\d,]+/);
    expect(screen.queryByText(/999/)).toBeNull();
  });

  it('shows helper note explaining partial filter scope', () => {
    renderPage();
    expect(screen.getByTestId('analytics-filter-scope-note')).toHaveTextContent(
      /solo a métricas de posiciones o solo a métricas de corridas/i
    );
  });

  it('shows provider/model section using observability data', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-providers'));
    const table = screen.getByTestId('analytics-providers-table');
    expect(within(table).getByText('gemini')).toBeInTheDocument();
    expect(within(table).getByText('flash')).toBeInTheDocument();
  });

  it('shows inventory performance table', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    expect(screen.getByTestId('analytics-inventories-table')).toBeInTheDocument();
    expect(screen.getByText('Test DC')).toBeInTheDocument();
  });

  it('shows aisle table', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-aisles'));
    expect(screen.getByTestId('analytics-aisles-table')).toBeInTheDocument();
    expect(screen.getByText('A-01')).toBeInTheDocument();
  });

  it('shows enabled compare CTA for test inventory row', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    const btn = screen.getByTestId('inventory-compare-inv-test');
    expect(btn).not.toBeDisabled();
  });

  it('shows disabled compare CTA for production inventory row', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    const btn = screen.getByTestId('inventory-compare-inv-prod');
    expect(btn).toBeDisabled();
  });

  it('compare tab exists with entry point to existing compare route', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-compare'));
    expect(screen.getByTestId('analytics-compare-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-open-compare-flow')).toBeInTheDocument();
    expect(within(screen.getByTestId('analytics-compare-tab')).getByText('Comparación de corridas')).toBeInTheDocument();
  });

  it('costs tab links to compare section', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    expect(screen.getByTestId('analytics-costs-tab')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('analytics-costs-go-compare'));
    expect(screen.getByTestId('analytics-compare-tab')).toBeInTheDocument();
  });
});
