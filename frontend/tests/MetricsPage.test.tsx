import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import MetricsPage from '../src/features/analytics/MetricsPage';
import { ApiError } from '../src/api/types';

const mockUseAnalyticsDashboard = vi.fn();
const mockUseInventoriesList = vi.fn();

vi.mock('../src/hooks/useInventories', () => ({
  useInventoriesList: (...args: unknown[]) => mockUseInventoriesList(...args),
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
    operator_marked_unknown_rate: null,
    operator_marked_unknown_count: 0,
    unidentified_product_rate: 0.15,
    unidentified_product_count: 3,
    invalid_traceability_rate: 0.1,
    processing_success_rate: 0.9,
    average_processing_time_seconds: 120,
    average_processing_time_minutes: 2,
    settling_actions_per_day: 4,
    notes: ['Current-state metrics use entity scope.'],
    period_day_count: 7,
    settling_actions_count: 10,
    positions_in_scope: 20,
    total_positions_in_scope: 20,
    processed_positions_count: 16,
    reviewed_positions_count: 8,
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
        aisles_count: 2,
        total_positions: 10,
        positions_count: 10,
        processed_positions: 8,
        processed_count: 8,
        review_rate: 0.4,
        correction_rate: 0.1,
        auto_acceptance_rate: 0.6,
        manual_correction_rate: 0.1,
        operator_marked_unknown_rate: null,
        unidentified_product_rate: 0.2,
        invalid_traceability_rate: 0.05,
        avg_confidence: 0.82,
        processing_success_rate: 0.95,
        average_processing_time_minutes: 9.5,
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
        operator_marked_unknown_count: 0,
        unidentified_product_count: 1,
        invalid_traceability_count: 0,
        low_confidence_count: 1,
        most_common_issue: 'Pending review',
      },
    ],
  },
  quality: {
    items: [{ issue_type: 'Low confidence', count: 2, percentage: 0.4, notes: 'test note' }],
  },
  manualInterventions: {
    reviewed_positions_count: 8,
    intervention_positions_count: 5,
    items: [
      { category: 'confirmed', count: 2, percentage: 0.4, available: true, notes: null },
      { category: 'qty_corrected', count: 1, percentage: 0.2, available: true, notes: null },
      { category: 'sku_corrected', count: 1, percentage: 0.2, available: true, notes: null },
      { category: 'invalid', count: null, percentage: null, available: false, notes: 'not available' },
      { category: 'operator_marked_unknown', count: null, percentage: null, available: false, notes: 'not persisted' },
      { category: 'deleted', count: 1, percentage: 0.2, available: true, notes: null },
    ],
    notes: ['unknown category unavailable'],
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
      <MemoryRouter initialEntries={['/metrics']}>
        <Routes>
          <Route path="/metrics" element={<MetricsPage />} />
          <Route
            path="/inventories/:inventoryId/analytics/compare"
            element={<div data-testid="metrics-compare-route">compare</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('MetricsPage', () => {
  beforeEach(() => {
    mockUseInventoriesList.mockReturnValue({
      data: {
        items: [
          {
            id: 'inv-1',
            name: 'North DC',
            status: 'active',
            processing_mode: 'test',
            aisles_count: 2,
            pending_review_count: 1,
            last_activity_at: null,
          },
          {
            id: 'inv-2',
            name: 'South DC',
            status: 'active',
            processing_mode: 'production',
            aisles_count: 3,
            pending_review_count: 0,
            last_activity_at: null,
          },
        ],
        page: 1,
        page_size: 25,
        total_items: 2,
        total_pages: 1,
      },
      isLoading: false,
      isError: false,
    });
    mockUseAnalyticsDashboard.mockReturnValue(dashboardLoaded);
  });

  it('renders the new operational hierarchy and removes low-value legacy blocks', () => {
    renderMetrics();
    expect(screen.getByRole('heading', { name: /page a11y/i })).toBeInTheDocument();
    expect(screen.getByText('Kpi auto accept title')).toBeInTheDocument();
    expect(screen.getByText('Manual intervention title')).toBeInTheDocument();
    expect(screen.getByText('Resolution flow title')).toBeInTheDocument();
    expect(screen.getByText('Inventory performance title')).toBeInTheDocument();
    expect(screen.getByText('Aisles attention title')).toBeInTheDocument();
    expect(screen.queryByText('Settling actions / day')).not.toBeInTheDocument();
    expect(screen.queryByText('Review activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Processing outcomes')).not.toBeInTheDocument();
  });

  it('renders KPI values from truthful backend fields and surfaces unidentified product as the KPI concept', () => {
    renderMetrics();
    expect(screen.getByText('50.0%')).toBeInTheDocument(); // auto_acceptance_rate
    expect(screen.getByText('2.0 min')).toBeInTheDocument();
    expect(screen.getAllByText('Kpi unidentified title').length).toBeGreaterThan(0);
  });

  it('shows skeleton KPI band while loading without summary', () => {
    mockUseAnalyticsDashboard.mockReturnValue({
      ...dashboardLoaded,
      summary: undefined,
      isLoading: true,
    });
    const { container } = renderMetrics();
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
    expect(screen.queryByText('Kpi unidentified title')).not.toBeInTheDocument();
  });

  it('shows error alert when a query fails', () => {
    mockUseAnalyticsDashboard.mockReturnValue({
      ...dashboardLoaded,
      isError: true,
      errors: [new ApiError('Server error', 500)],
    });
    renderMetrics();
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
    expect(screen.getByText(/something went wrong|server error|load metrics|request failed|unexpected/i)).toBeInTheDocument();
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
    expect(screen.getByText('Empty quality filter')).toBeInTheDocument();
  });

  it('shows unavailable intervention categories without fabricating backend support', () => {
    renderMetrics();
    expect(screen.getAllByText('Intervention unavailable chip').length).toBeGreaterThan(0);
  });

  it('does not expose a redundant Actions column on inventory or aisle analytics tables', () => {
    renderMetrics();
    expect(screen.queryByRole('columnheader', { name: /^Actions$/i })).not.toBeInTheDocument();
  });

  it('renders the global inventory option plus fetched inventory options', () => {
    renderMetrics();
    const select = screen.getByRole('combobox', { name: 'Inventory', hidden: true });
    fireEvent.mouseDown(select);

    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getByText('Scope inventory all')).toBeInTheDocument();
    expect(within(listbox).getByText('North DC')).toBeInTheDocument();
    expect(within(listbox).getByText('South DC')).toBeInTheDocument();
  });

  it('shows a Compare runs control in the filter toolbar', () => {
    renderMetrics();
    expect(screen.getByTestId('metrics-compare-runs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /compare runs/i })).toBeDisabled();
  });

  it('enables Compare runs for a selected test inventory and navigates to analytics compare', async () => {
    renderMetrics();
    const invSelect = screen.getByRole('combobox', { name: 'Inventory', hidden: true });
    fireEvent.mouseDown(invSelect);
    fireEvent.click(within(screen.getByRole('listbox')).getByText('North DC'));

    const compareBtn = screen.getByTestId('metrics-compare-runs');
    expect(compareBtn).not.toBeDisabled();
    fireEvent.click(compareBtn);

    await waitFor(() => {
      expect(screen.getByTestId('metrics-compare-route')).toBeInTheDocument();
    });
  });

  it('keeps Compare runs disabled when the selected inventory is production', () => {
    renderMetrics();
    const invSelect = screen.getByRole('combobox', { name: 'Inventory', hidden: true });
    fireEvent.mouseDown(invSelect);
    fireEvent.click(within(screen.getByRole('listbox')).getByText('South DC'));

    expect(screen.getByTestId('metrics-compare-runs')).toBeDisabled();
  });

  it('renders the finished operational visuals, compact aisle columns, and ordered quality patterns when truthful data exists', () => {
    mockUseAnalyticsDashboard.mockReturnValue({
      ...dashboardLoaded,
      summary: {
        ...dashboardLoaded.summary,
        operator_marked_unknown_rate: 0.125,
        operator_marked_unknown_count: 1,
        unidentified_product_rate: 0.25,
        unidentified_product_count: 2,
        unknown_rate: 0.125,
        unknown_count: 1,
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
            corrected_count: 1,
            operator_marked_unknown_count: 1,
            unidentified_product_count: 2,
            unknown_count: 1,
            manual_corrections_count: 2,
            invalid_traceability_count: 1,
            low_confidence_count: 1,
            most_common_issue: 'Unidentified product',
          },
        ],
      },
      quality: {
        items: [
          { issue_type: 'Low confidence', count: 2, percentage: 0.2, notes: 'Below threshold' },
          { issue_type: 'Unidentified product', count: 1, percentage: 0.1, notes: 'Display-primary product SKU is persisted as UNKNOWN' },
          { issue_type: 'Pending review', count: 3, percentage: 0.3, notes: 'Needs review flag set' },
        ],
      },
      manualInterventions: {
        reviewed_positions_count: 8,
        intervention_positions_count: 5,
        items: [
          { category: 'confirmed', count: 2, percentage: 0.25, available: true, notes: null },
          { category: 'qty_corrected', count: 2, percentage: 0.25, available: true, notes: null },
          { category: 'sku_corrected', count: 1, percentage: 0.125, available: true, notes: null },
          { category: 'invalid', count: null, percentage: null, available: false, notes: 'not available' },
          { category: 'operator_marked_unknown', count: 1, percentage: 0.125, available: true, notes: 'Explicit terminal unknown outcome' },
          { category: 'deleted', count: 1, percentage: 0.125, available: true, notes: null },
        ],
        notes: [],
      },
    });

    renderMetrics();

    expect(screen.getByText('Reviewed positions label')).toBeInTheDocument();
    expect(screen.getByText('Awaiting backend support')).toBeInTheDocument();
    expect(screen.getByText('Positions in scope')).toBeInTheDocument();
    expect(screen.getAllByText('Pending review').length).toBeGreaterThan(0);
    expect(screen.getByText('Manual touch')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Column unidentified product' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Column manual corrections' })).toBeInTheDocument();
    expect(screen.getAllByText('Category operator unknown').length).toBeGreaterThan(0);

    expect(screen.getAllByText('Unidentified product').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Pending review').length).toBeGreaterThan(0);
  });
});
