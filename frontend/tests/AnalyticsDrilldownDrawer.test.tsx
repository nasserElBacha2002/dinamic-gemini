import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AnalyticsDrilldownDrawer } from '../src/features/analytics-dashboard/components/drilldown/AnalyticsDrilldownDrawer';
import type { AnalyticsCostSummaryResponse } from '../src/api/types';

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
        most_common_issue: 'Pending review',
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
  scope: {},
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
  ],
  by_capture_status: [],
  warnings: [],
};

function renderDrawer(state: { type: 'inventory'; inventoryId: string } | { type: 'aisle'; inventoryId: string; aisleId: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const inventoriesById = new Map([
    ['inv-test', { id: 'inv-test', name: 'Test DC', processing_mode: 'test', status: 'active' }],
  ]);
  const processingModeById = new Map([['inv-test', 'test']]);

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnalyticsDrilldownDrawer
          state={state}
          onClose={vi.fn()}
          analytics={analyticsBundle as never}
          costSummary={costSummary}
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

describe('AnalyticsDrilldownDrawer', () => {
  it('renders inventory drilldown with name and cost KPIs', () => {
    renderDrawer({ type: 'inventory', inventoryId: 'inv-test' });
    expect(screen.getByTestId('analytics-drilldown-drawer')).toBeInTheDocument();
    expect(screen.getByText(/Inventario: Test DC/)).toBeInTheDocument();
    const panel = screen.getByTestId('analytics-drilldown-inventory-panel');
    expect(within(panel).getByText(/20[,.]50/)).toBeInTheDocument();
  });

  it('shows No disponible for null cost per unit on aisle drilldown when missing', () => {
    const summaryWithoutUnit = {
      ...costSummary,
      by_aisle: [{ ...costSummary.by_aisle[0]!, cost_per_counted_unit: null }],
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AnalyticsDrilldownDrawer
            state={{ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' }}
            onClose={vi.fn()}
            analytics={analyticsBundle as never}
            costSummary={summaryWithoutUnit}
            isCostLoading={false}
            inventoryProcessingModeById={new Map([['inv-test', 'test']])}
            inventoriesById={new Map() as never}
            onOpenAisleDrilldown={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText(/Pasillo: A-01/)).toBeInTheDocument();
    expect(screen.getAllByText('No disponible').length).toBeGreaterThan(0);
  });

  it('fetches aisle jobs only when aisle drawer is open', () => {
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    expect(mockUseAisleJobsList).toHaveBeenCalledWith('inv-test', 'a-1', expect.objectContaining({ enabled: true }));
    expect(screen.getByTestId('analytics-drilldown-jobs-table')).toBeInTheDocument();
    expect(screen.getByText('Requieren revisión')).toBeInTheDocument();
  });

  it('shows compare link for test inventory', () => {
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    const compare = screen.getByTestId('analytics-drilldown-compare');
    expect(compare).not.toBeDisabled();
    expect(compare).toHaveAttribute('href', '/inventories/inv-test/analytics/compare-many?aisleId=a-1');
  });

  it('shows jobs loading state', () => {
    mockUseAisleJobsList.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderDrawer({ type: 'aisle', inventoryId: 'inv-test', aisleId: 'a-1' });
    expect(screen.getByTestId('analytics-drilldown-jobs-loading')).toBeInTheDocument();
  });
});
