import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { AnalyticsCostsTab } from '../src/features/analytics-dashboard/components/AnalyticsCostsTab';
import type { AnalyticsCostSummaryResponse } from '../src/api/types';

const costSummaryData: AnalyticsCostSummaryResponse = {
  scope: {},
  totals: {
    jobs_total: 3,
    jobs_with_cost: 2,
    jobs_without_cost: 1,
    jobs_with_exact_cost: 1,
    jobs_with_estimated_cost: 1,
    jobs_with_partial_cost: 0,
    jobs_with_unavailable_cost: 0,
    jobs_with_missing_cost: 0,
    total_cost: 12.5,
    total_counted_quantity: 40,
    cost_per_counted_unit: 0.3125,
    total_execution_time_seconds: 90,
  } as never,
  by_provider_model: [
    {
      provider_name: 'gemini',
      model_name: 'flash',
      jobs_total: 3,
      jobs_with_cost: 2,
      total_cost: 12.5,
      total_counted_quantity: null,
      cost_per_counted_unit: null,
      average_execution_time_seconds: 90,
    },
  ],
  by_inventory: [
    {
      inventory_id: 'inv-1',
      inventory_name: 'Test DC',
      jobs_total: 2,
      jobs_with_cost: 2,
      total_cost: 10,
      total_counted_quantity: 30,
      cost_per_counted_unit: 0.33,
      total_execution_time_seconds: 60,
    },
  ],
  by_aisle: [
    {
      inventory_id: 'inv-1',
      inventory_name: 'Test DC',
      aisle_id: 'a-1',
      aisle_code: 'A-01',
      jobs_total: 1,
      jobs_with_cost: 1,
      total_cost: 5,
      total_counted_quantity: 10,
      cost_per_counted_unit: 0.5,
      total_execution_time_seconds: 30,
    },
  ],
  by_capture_status: [
    { capture_status: 'exact', jobs_total: 1, total_cost: 8 },
    { capture_status: 'estimated', jobs_total: 1, total_cost: 4 },
  ],
  warnings: ['PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE'],
};

const drilldown = {
  onOpenInventoryDrilldown: vi.fn(),
  onOpenAisleDrilldown: vi.fn(),
};

describe('AnalyticsCostsTab', () => {
  it('shows executive KPIs without duplicated visual summary block', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-costs-executive-kpis')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-cost-visual-section')).not.toBeInTheDocument();
    const kpiPanel = screen.getByTestId('analytics-costs-executive-kpis');
    expect(kpiPanel.querySelectorAll('[data-testid^="analytics-costs-executive-kpis-cost-kpi"]').length).toBe(5);
  });

  it('shows compact warnings summary', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-cost-warnings-summary')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-warning-PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE')).toBeInTheDocument();
  });

  it('renders chart-first sections and hides tables by default', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-costs-capture-donut')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-costs-jobs-coverage-donut')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-costs-chart-provider-bars')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-inventory-ranking')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-aisle-ranking')).toBeInTheDocument();
    expect(screen.queryByTestId('analytics-cost-by-provider-table')).not.toBeInTheDocument();
  });

  it('shows tabular detail only after toggle', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    fireEvent.click(screen.getByTestId('analytics-costs-toggle-tabular'));
    expect(screen.getByTestId('analytics-cost-by-provider-table')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-by-inventory-table')).toBeInTheDocument();
  });

  it('opens inventory drilldown from ranking card', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    fireEvent.click(screen.getByTestId('cost-drilldown-inventory-inv-1'));
    expect(drilldown.onOpenInventoryDrilldown).toHaveBeenCalledWith('inv-1');
  });

  it('shows empty state when no jobs in scope', () => {
    render(
      <AnalyticsCostsTab
        costSummary={{
          ...costSummaryData,
          totals: { ...costSummaryData.totals, jobs_total: 0, jobs_with_cost: 0 },
        }}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-costs-empty')).toHaveTextContent(/No hay jobs en el alcance/i);
  });

  it('does not show disabled compare in cost ranking cards', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    const inventoryRanking = screen.getByTestId('analytics-cost-inventory-ranking');
    const aisleRanking = screen.getByTestId('analytics-cost-aisle-ranking');
    expect(within(inventoryRanking).queryByText(/comparar corridas/i)).not.toBeInTheDocument();
    expect(within(aisleRanking).queryByText(/comparar corridas/i)).not.toBeInTheDocument();
  });

  it('calls onGoToCompare from CTA', () => {
    const onGoToCompare = vi.fn();
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={onGoToCompare}
        drilldown={drilldown}
      />
    );
    fireEvent.click(screen.getByTestId('analytics-costs-go-compare'));
    expect(onGoToCompare).toHaveBeenCalledTimes(1);
  });

  it('shows loading skeleton on executive panel while loading', () => {
    const { container } = render(
      <AnalyticsCostsTab
        costSummary={undefined}
        isLoading
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-costs-panel-executive')).toBeInTheDocument();
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });
});
