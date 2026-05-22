import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { EMPTY_ANALYTICS_COST_SCOPE } from './helpers/fixtures';
import {
  ANALYTICS_DRILLDOWN_DRAWER_WIDTH,
  AnalyticsDrilldownDrawer,
} from '../src/features/analytics-dashboard/components/drilldown/AnalyticsDrilldownDrawer';
import {
  buildAisleContributionRows,
  compareNullableCostDesc,
  mapJobsForDrilldownTable,
} from '../src/features/analytics-dashboard/adapters/analyticsDrilldownViewModel';
import type { AnalyticsCostSummaryResponse } from '../src/api/types';
import i18n from '../src/i18n';

const mockUseAisleJobsList = vi.fn();
const mockUseInventoryMetrics = vi.fn();

vi.mock('../src/hooks/useAisles', async () => {
  const actual = await vi.importActual<typeof import('../src/hooks/useAisles')>('../src/hooks/useAisles');
  return {
    ...actual,
    useAisleJobsList: (...args: unknown[]) => mockUseAisleJobsList(...args),
    useInventoryMetrics: (...args: unknown[]) => mockUseInventoryMetrics(...args),
  };
});

const analyticsBundle = {
  summary: null,
  trends: null,
  inventoryPerformance: {
    items: [
      {
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        inventory_created_at: '2026-01-01T00:00:00Z',
        total_aisles: 1,
        total_positions: 10,
        processed_positions: 8,
        auto_acceptance_rate: 0.6,
        manual_correction_rate: 0.1,
        invalid_traceability_rate: 0.05,
        average_processing_time_minutes: 9.5,
        processing_success_rate: 0.95,
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
        corrected_count: 1,
        unidentified_product_count: 0,
        invalid_traceability_count: 0,
        low_confidence_count: 0,
        most_common_issue: 'Pending review',
      },
      {
        aisle_id: 'a-2',
        aisle_code: 'A-02',
        inventory_id: 'inv-test',
        inventory_name: 'Test DC',
        total_results: 3,
        needs_review_count: 1,
        corrected_count: 0,
        unidentified_product_count: 0,
        invalid_traceability_count: 0,
        low_confidence_count: 0,
        most_common_issue: null,
      },
    ],
  },
  quality: null,
  manualInterventions: null,
  isLoading: false,
  isError: false,
  errors: [],
  refetchAll: vi.fn(),
};

const costSummary: AnalyticsCostSummaryResponse = {
  scope: EMPTY_ANALYTICS_COST_SCOPE,
  totals: {} as never,
  by_provider_model: [],
  by_inventory: [
    {
      inventory_id: 'inv-test',
      inventory_name: 'Test DC',
      jobs_total: 5,
      jobs_with_cost: 4,
      total_cost: 20.5,
      total_counted_quantity: 100,
      cost_per_counted_unit: 0.205,
      total_execution_time_seconds: 300,
    },
  ],
  by_aisle: [
    {
      inventory_id: 'inv-test',
      inventory_name: 'Test DC',
      aisle_id: 'a-1',
      aisle_code: 'A-01',
      jobs_total: 3,
      jobs_with_cost: 3,
      total_cost: 5.5,
      total_counted_quantity: 25,
      cost_per_counted_unit: 0.22,
      total_execution_time_seconds: 120,
    },
    {
      inventory_id: 'inv-test',
      inventory_name: 'Test DC',
      aisle_id: 'a-2',
      aisle_code: 'A-02',
      jobs_total: 2,
      jobs_with_cost: 0,
      total_cost: null,
      total_counted_quantity: null,
      cost_per_counted_unit: null,
      total_execution_time_seconds: null,
    },
  ],
  by_capture_status: [],
  warnings: ['PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE'],
};

function renderDrawer(
  state:
    | { type: 'inventory'; inventoryId: string }
    | { type: 'aisle'; inventoryId: string; aisleId: string }
    | null,
  options?: {
    processingModeById?: Map<string, string | undefined>;
    costSummaryOverride?: AnalyticsCostSummaryResponse;
  }
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const inventoriesById = new Map([
    ['inv-test', { id: 'inv-test', name: 'Test DC', processing_mode: 'test', status: 'active' }],
  ]);
  const processingModeById = options?.processingModeById ?? new Map([['inv-test', 'test']]);

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnalyticsDrilldownDrawer
          state={state}
          onClose={vi.fn()}
          analytics={analyticsBundle as never}
          costSummary={options?.costSummaryOverride ?? costSummary}
          isCostLoading={false}
          inventoryProcessingModeById={processingModeById}
          inventoriesById={inventoriesById as never}
          onOpenAisleDrilldown={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseInventoryMetrics.mockReturnValue({
    data: { total_positions: 10, total_reviewed_positions: 8 },
    isLoading: false,
    isError: false,
  });
  mockUseAisleJobsList.mockReturnValue({
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
  });
});

describe('analyticsDrilldownViewModel', () => {
  it('sorts aisle contribution rows with real cost before missing cost', () => {
    const rows = buildAisleContributionRows(analyticsBundle.aisleIssues.items, costSummary, 'inv-test');
    expect(rows[0]?.aisleId).toBe('a-1');
    expect(rows[1]?.aisleId).toBe('a-2');
    expect(compareNullableCostDesc(10, null)).toBeLessThan(0);
    expect(compareNullableCostDesc(null, 10)).toBeGreaterThan(0);
  });

  it('maps jobs with dash for missing or invalid dates', () => {
    const rows = mapJobsForDrilldownTable(
      [
        {
          id: 'job-invalid',
          status: 'succeeded',
          created_at: 'not-a-date',
          updated_at: '2026-01-01T01:00:00Z',
          started_at: null,
          finished_at: 'also-invalid',
          provider_name: 'gemini',
          model_name: 'flash',
        },
        {
          id: 'job-missing',
          status: 'queued',
          created_at: null as unknown as string,
          updated_at: '2026-01-01T00:00:00Z',
          started_at: null,
          finished_at: null,
          provider_name: null,
          model_name: null,
        },
      ],
      i18n.t
    );
    expect(rows[0]?.startedAt).toBe('—');
    expect(rows[0]?.finishedAt).toBe('—');
    expect(rows[0]?.duration).toBe('—');
    expect(rows[1]?.startedAt).toBe('—');
    expect(rows[1]?.finishedAt).toBe('—');
  });
});

describe('AnalyticsDrilldownDrawer', () => {
  it('renders drawer paper with responsive width configuration', () => {
    renderDrawer({ type: 'inventory', inventoryId: 'inv-test' });
    expect(screen.getByTestId('analytics-drilldown-drawer-paper')).toBeInTheDocument();
    expect(ANALYTICS_DRILLDOWN_DRAWER_WIDTH).toMatchObject({
      xs: '100vw',
      sm: '92vw',
      md: 860,
      lg: 960,
      xl: 1040,
    });
  });

  it('renders inventory drilldown with name, cost KPIs, and scope caption', () => {
    renderDrawer({ type: 'inventory', inventoryId: 'inv-test' });
    expect(screen.getByTestId('analytics-drilldown-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-drilldown-scope-caption')).toHaveTextContent(
      /alcance y los filtros aplicados en Analítica/i
    );
    expect(screen.getByText(/Inventario: Test DC/)).toBeInTheDocument();
    const panel = screen.getByTestId('analytics-drilldown-inventory-panel');
    expect(screen.getByTestId('analytics-drilldown-inventory-kpis')).toBeInTheDocument();
    expect(within(panel).getByText(/20[,.]50/)).toBeInTheDocument();
  });

  it('shows scope-level warning title in inventory drilldown', () => {
    renderDrawer({ type: 'inventory', inventoryId: 'inv-test' });
    expect(screen.getByText('Advertencias del alcance analítico')).toBeInTheDocument();
    expect(
      screen.getByText(/Estas advertencias corresponden al alcance y filtros aplicados en Analítica/i)
    ).toBeInTheDocument();
  });

  it('shows scope caption and jobs limit helper in aisle drilldown', () => {
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    expect(screen.getByTestId('analytics-drilldown-scope-caption')).toBeInTheDocument();
    expect(screen.getByText('Se muestran las últimas 20 corridas disponibles.')).toBeInTheDocument();
  });

  it('shows No disponible for null cost per unit on aisle drilldown when missing', () => {
    const summaryWithoutUnit = {
      ...costSummary,
      by_aisle: [{ ...costSummary.by_aisle[0]!, cost_per_counted_unit: null }],
    };
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' }, { costSummaryOverride: summaryWithoutUnit });
    expect(screen.getByText(/Pasillo: A-01/)).toBeInTheDocument();
    expect(screen.getAllByText('No disponible').length).toBeGreaterThan(0);
  });

  it('fetches aisle jobs only when aisle drawer is open with valid context', () => {
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    expect(mockUseAisleJobsList).toHaveBeenCalledWith('inv-test', 'a-1', expect.objectContaining({ enabled: true }));
    expect(screen.getByTestId('analytics-drilldown-jobs-table')).toBeInTheDocument();
    expect(screen.getByText('Requieren revisión')).toBeInTheDocument();
  });

  it('does not enable jobs query when drawer is closed', () => {
    renderDrawer(null);
    expect(mockUseAisleJobsList).not.toHaveBeenCalled();
  });

  it('does not enable jobs query in inventory drawer mode', () => {
    renderDrawer({ type: 'inventory', inventoryId: 'inv-test' });
    expect(mockUseAisleJobsList).not.toHaveBeenCalled();
  });

  it('does not enable jobs query when aisle has no analytics or cost context', () => {
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'missing-aisle' });
    expect(mockUseAisleJobsList).toHaveBeenCalledWith('inv-test', 'missing-aisle', expect.objectContaining({ enabled: false }));
    expect(screen.getByTestId('analytics-drilldown-aisle-empty')).toBeInTheDocument();
  });

  it('shows compare link for test inventory', () => {
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    const compare = screen.getByTestId('analytics-drilldown-compare');
    expect(compare).not.toBeDisabled();
    expect(compare).toHaveAttribute('href', '/inventories/inv-test/analytics/compare-many?aisleId=a-1');
  });

  it('shows unknown-mode tooltip on compare CTA when processing mode is missing', async () => {
    renderDrawer(
      { type: 'aisle', inventoryId: 'inv-unknown', aisleId: 'a-1' },
      {
        processingModeById: new Map(),
        costSummaryOverride: {
          ...costSummary,
          by_aisle: [
            {
              ...costSummary.by_aisle[0]!,
              inventory_id: 'inv-unknown',
            },
          ],
        },
      }
    );
    const compare = screen.getByTestId('analytics-drilldown-compare');
    expect(compare).toBeDisabled();
    expect(compare.closest('span')).toHaveAttribute(
      'aria-label',
      'No se pudo determinar si este inventario permite comparación.'
    );
  });

  it('shows jobs loading state', () => {
    mockUseAisleJobsList.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    expect(screen.getByTestId('analytics-drilldown-jobs-loading')).toBeInTheDocument();
  });
});
