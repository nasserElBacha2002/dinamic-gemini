import '@testing-library/jest-dom/vitest';
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
  useAisleJobsList: () => ({
    data: {
      jobs: [
        {
          id: 'job-1',
          status: 'succeeded',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T01:00:00Z',
          started_at: '2026-01-01T00:00:00Z',
          finished_at: '2026-01-01T01:00:00Z',
          provider_name: 'gemini',
          model_name: 'flash',
        },
      ],
    },
    isLoading: false,
    isError: false,
  }),
  useInventoryMetrics: () => ({
    data: { total_positions: 10, total_reviewed_positions: 8 },
    isLoading: false,
    isError: false,
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

const costSummaryData = {
  scope: {
    date_from: '2026-01-01',
    date_to: '2026-01-31',
    inventory_id: null,
    aisle_id: null,
    client_id: null,
    client_supplier_id: null,
    provider_name: null,
    model_name: null,
  },
  totals: {
    jobs_total: 20,
    jobs_with_cost: 18,
    jobs_without_cost: 2,
    jobs_with_exact_cost: 10,
    jobs_with_estimated_cost: 5,
    jobs_with_partial_cost: 2,
    jobs_with_unavailable_cost: 1,
    jobs_with_missing_cost: 2,
    total_cost: 24.82,
    total_counted_quantity: 1250,
    cost_per_counted_unit: 0.019856,
    total_execution_time_seconds: 3600,
    average_execution_time_seconds: 180,
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
  by_capture_status: [
    { capture_status: 'exact', jobs_total: 10, total_cost: 15 },
    { capture_status: 'estimated', jobs_total: 5, total_cost: 8 },
  ],
  warnings: ['PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE'],
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

function setupMocksWithDashboardData(overrides: Record<string, unknown> = {}) {
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
    ...overrides,
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

  it('renders hero KPI cards from observability mocked data', () => {
    renderPage();
    const hero = screen.getByTestId('analytics-executive-hero');
    expect(within(hero).getByText('Exitosos')).toBeInTheDocument();
    expect(within(hero).getByText('Tasa de error')).toBeInTheDocument();
    expect(screen.getAllByTestId(/analytics-hero-kpi-/).length).toBeLessThanOrEqual(6);
  });

  it('renders executive hero and compact summary panels on overview', () => {
    renderPage();
    expect(screen.getByTestId('analytics-overview-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-hero-title')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-executive-hero')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-cost-insight')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-cost-visual-section')).not.toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-cost-donut')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-cost-provider-bars')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-hero-kpi-total-cost')).toHaveTextContent(/24[,.]82/);
    expect(screen.queryByText('Producto sin identificar')).not.toBeInTheDocument();
    expect(screen.queryByText('Éxito de procesamiento')).not.toBeInTheDocument();
  });

  it('shows compact attention list with donut charts and section CTAs on overview', () => {
    renderPage();
    expect(screen.getByTestId('analytics-summary-attention-list')).toBeInTheDocument();
    expect(screen.getAllByTestId(/analytics-overview-aisle-/).length).toBeLessThanOrEqual(3);
    expect(screen.getByTestId('analytics-chart-processing-trend')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-quality-donut')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-panel-cost-cta')).toHaveAttribute('href', '/analitica?tab=costos');
    expect(screen.getByTestId('overview-aisle-drilldown-a-1')).toBeInTheDocument();
  });

  it('renders compact data quality summary when cost warnings exist', () => {
    renderPage();
    expect(screen.getByTestId('analytics-data-quality-summary')).toBeInTheDocument();
    expect(screen.getByText('Calidad de datos')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-dq-PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE')).toBeInTheDocument();
  });

  it('shows unavailable state for global cost metrics when cost summary missing', () => {
    setupMocksWithDashboardData({
      costSummary: { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    });
    renderPage();
    expect(screen.getByTestId('analytics-hero-kpi-total-cost')).toHaveTextContent('No disponible');
    expect(screen.queryByTestId('analytics-summary-panel-cost')).not.toBeInTheDocument();
  });

  it('shows cost partial failure without hiding position metrics', () => {
    setupMocksWithDashboardData({
      costSummaryError: new Error('cost failed'),
      costSummary: { data: undefined, isLoading: false, isError: true, error: new Error('cost failed'), refetch: vi.fn() },
      hasPartialFailure: true,
    });
    renderPage();
    expect(screen.getByTestId('analytics-dq-cost-failed')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-partial-cost-failed')).toBeInTheDocument();
    expect(screen.getByText('Posiciones procesadas')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
  });

  it('shows static filter scope note in the filter bar', () => {
    renderPage();
    expect(screen.getByTestId('analytics-filter-scope-note')).toHaveTextContent(
      /solo a métricas de posiciones o solo a métricas de corridas/i
    );
  });

  it('does not show mixed-loaded banner while either source is still loading', () => {
    setupMocksWithDashboardData({
      isAnalyticsLoading: true,
      isObservabilityLoading: false,
      analytics: { ...analyticsLoaded, summary: undefined },
    });
    renderPage();
    expect(screen.queryByTestId('analytics-mixed-loaded-data')).not.toBeInTheDocument();
  });

  it('shows analytics failure warning when observability loaded', () => {
    setupMocksWithDashboardData({
      analyticsError: new Error('analytics failed'),
      analytics: { ...analyticsLoaded, isError: true, summary: undefined },
    });
    renderPage();
    expect(screen.getByTestId('analytics-dq-analytics-failed')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-dq-observability-failed')).not.toBeInTheDocument();
    expect(screen.queryByTestId('analytics-mixed-loaded-data')).not.toBeInTheDocument();
  });

  it('shows observability failure warning when analytics loaded', () => {
    setupMocksWithDashboardData({
      observabilityError: new Error('observability failed'),
      observability: { data: undefined, isLoading: false, isError: true, error: new Error('observability failed'), refetch: vi.fn() },
    });
    renderPage();
    expect(screen.getByTestId('analytics-dq-observability-failed')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-dq-analytics-failed')).not.toBeInTheDocument();
    expect(screen.queryByTestId('analytics-mixed-loaded-data')).not.toBeInTheDocument();
  });

  it('shows mixed-loaded banner only after both sources finish with one empty', () => {
    setupMocksWithDashboardData({ hasMixedLoadedData: true });
    renderPage();
    expect(screen.getByTestId('analytics-mixed-loaded-data')).toBeInTheDocument();
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
    const invTable = screen.getByTestId('analytics-inventories-table');
    expect(invTable).toBeInTheDocument();
    expect(within(invTable).getByRole('link', { name: 'Test DC' })).toBeInTheDocument();
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

  it('compare tab shows select inventory hint without selected inventory', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-compare'));
    expect(screen.getByTestId('analytics-compare-tab')).toBeInTheDocument();
    expect(screen.getByText(/Seleccioná un inventario/i)).toBeInTheDocument();
    expect(screen.queryByTestId('compare-many-workspace-embedded')).not.toBeInTheDocument();
  });

  it('costs tab renders charts before detailed tables', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    expect(screen.getByTestId('analytics-costs-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-visual-section')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-by-provider-table')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-by-inventory-table')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-by-aisle-table')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-by-capture-table')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-warning-PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE')).toBeInTheDocument();
  });

  it('shows No disponible for null provider cost per unit without computing it', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    const providerTable = screen.getByTestId('analytics-cost-by-provider-table');
    expect(within(providerTable).getAllByText('No disponible').length).toBeGreaterThan(0);
  });

  it('shows cost load error on costs tab when endpoint fails', () => {
    setupMocksWithDashboardData({
      costSummaryError: new Error('cost failed'),
      costSummary: { data: undefined, isLoading: false, isError: true, error: new Error('cost failed'), refetch: vi.fn() },
    });
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    const costsTab = screen.getByTestId('analytics-costs-tab');
    expect(within(costsTab).getByText('No se pudieron cargar las métricas de costos.')).toBeInTheDocument();
  });

  it('shows empty state when jobs_total is zero and keeps compare CTA', () => {
    setupMocksWithDashboardData({
      costSummary: {
        data: {
          ...costSummaryData,
          totals: { ...costSummaryData.totals, jobs_total: 0, jobs_with_cost: 0, jobs_without_cost: 0 },
        },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      },
    });
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    expect(screen.getByTestId('analytics-costs-empty')).toHaveTextContent(/No hay jobs en el alcance/i);
    expect(screen.getByTestId('analytics-costs-go-compare')).toBeInTheDocument();
  });

  it('shows distinct empty state when jobs exist but none have cost snapshots', () => {
    setupMocksWithDashboardData({
      costSummary: {
        data: {
          ...costSummaryData,
          totals: { ...costSummaryData.totals, jobs_total: 5, jobs_with_cost: 0, jobs_without_cost: 5 },
        },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      },
    });
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    expect(screen.getByTestId('analytics-costs-empty')).toHaveTextContent(/ninguno tiene snapshot/i);
    expect(screen.getByTestId('analytics-costs-go-compare')).toBeInTheDocument();
  });

  it('shows global ErrorAlert when analytics and observability fail even if cost succeeds', () => {
    setupMocksWithDashboardData({
      analyticsError: new Error('analytics failed'),
      observabilityError: new Error('observability failed'),
      analytics: { ...analyticsLoaded, isError: true, summary: undefined },
      observability: { data: undefined, isLoading: false, isError: true, error: new Error('observability failed'), refetch: vi.fn() },
      costSummaryError: null,
    });
    renderPage();
    expect(screen.getByText('No se pudieron cargar las métricas')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-partial-cost-failed')).not.toBeInTheDocument();
  });

  it('shows Cargando in inventory cost cells while cost summary loads', () => {
    setupMocksWithDashboardData({ isCostSummaryLoading: true, costSummary: { data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() } });
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    expect(screen.getAllByText('Cargando…').length).toBeGreaterThan(0);
  });

  it('shows hero skeleton and cost panel loading on overview while cost summary loads', () => {
    setupMocksWithDashboardData({
      isCostSummaryLoading: true,
      costSummary: { data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() },
    });
    renderPage();
    expect(screen.getByTestId('analytics-executive-hero')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-panel-cost')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-cost-visual-section')).not.toBeInTheDocument();
  });

  it('shows cost chart loading on inventarios tab while cost summary loads', () => {
    setupMocksWithDashboardData({
      isCostSummaryLoading: true,
      costSummary: { data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() },
    });
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    expect(screen.getByTestId('analytics-inventories-cost-summary-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-inventories-cost-summary-empty')).not.toBeInTheDocument();
  });

  it('labels provider insight as run volume not reliability', () => {
    renderPage();
    const providerPanel = screen.getByTestId('analytics-summary-panel-provider');
    expect(within(providerPanel).getByText(/corridas \(volumen\)/i)).toBeInTheDocument();
    expect(within(providerPanel).queryByText(/confiabilidad/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('analytics-summary-provider-mini-bars')).toBeInTheDocument();
  });

  it('shows compare CTA on overview critical aisle for test inventory', () => {
    renderPage();
    const btn = screen.getByTestId('overview-aisle-compare-a-1');
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute('href', '/inventories/inv-test/analytics/compare-many?aisleId=a-1');
  });

  it('opens inventory drilldown drawer from inventarios tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    fireEvent.click(screen.getByTestId('inventory-drilldown-inv-test'));
    expect(screen.getByTestId('analytics-drilldown-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-drilldown-inventory-panel')).toBeInTheDocument();
    expect(screen.getByText(/Inventario: Test DC/)).toBeInTheDocument();
  });

  it('opens aisle drilldown drawer from pasillos tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-aisles'));
    fireEvent.click(screen.getByTestId('aisle-drilldown-a-1'));
    expect(screen.getByTestId('analytics-drilldown-aisle-panel')).toBeInTheDocument();
    expect(screen.getByText(/Pasillo: A-01/)).toBeInTheDocument();
  });

  it('closing drilldown drawer keeps active tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    fireEvent.click(screen.getByTestId('inventory-drilldown-inv-test'));
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    expect(screen.queryByTestId('analytics-drilldown-inventory-panel')).not.toBeInTheDocument();
    expect(screen.getByTestId('analytics-inventories-table')).toBeInTheDocument();
  });

  it('providers tab shows charts and does not recommend a best provider', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-providers'));
    expect(screen.getByTestId('analytics-providers-tab')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-providers-chart-run-volume')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-providers-cost-table')).toBeInTheDocument();
    expect(screen.queryByText(/mejor proveedor/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/proveedor recomendado/i)).not.toBeInTheDocument();
    const costTable = screen.getByTestId('analytics-providers-cost-table');
    expect(within(costTable).getAllByText('No disponible').length).toBeGreaterThan(0);
  });

  it('costs tab links to compare section', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-costs'));
    expect(screen.getByTestId('analytics-costs-tab')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('analytics-costs-go-compare'));
    expect(screen.getByTestId('analytics-compare-tab')).toBeInTheDocument();
  });

  it('navigates to compare-many without aisleId from inventarios tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-inventories'));
    fireEvent.click(screen.getByTestId('inventory-compare-inv-test'));
    expect(mockNavigate).toHaveBeenCalledWith('/inventories/inv-test/analytics/compare-many');
  });

  it('navigates to compare-many with aisleId from pasillos tab', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-tab-aisles'));
    fireEvent.click(screen.getByTestId('aisle-compare-a-1'));
    expect(mockNavigate).toHaveBeenCalledWith('/inventories/inv-test/analytics/compare-many?aisleId=a-1');
  });

  it('does not call refetchAll when applying filters', () => {
    const refetchAll = vi.fn();
    setupMocksWithDashboardData({ refetchAll });
    renderPage();
    fireEvent.click(screen.getByTestId('analytics-apply-filters'));
    expect(refetchAll).not.toHaveBeenCalled();
  });
});
