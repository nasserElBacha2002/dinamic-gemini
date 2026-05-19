import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AnalyticsCostsTab } from '../src/features/analytics-dashboard/components/AnalyticsCostsTab';
import type { AnalyticsCostSummaryResponse } from '../src/api/types';

const costSummaryData: AnalyticsCostSummaryResponse = {
  scope: {},
  totals: {
    jobs_total: 3,
    jobs_with_cost: 2,
    jobs_without_cost: 1,
    jobs_with_partial_cost: 0,
    total_cost: 12.5,
    total_counted_quantity: 40,
    cost_per_counted_unit: 0.3125,
    total_execution_time_seconds: 90,
  } as never,
  by_provider_model: [],
  by_inventory: [],
  by_aisle: [],
  by_capture_status: [],
  warnings: ['PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE'],
};

const drilldown = {
  onOpenInventoryDrilldown: vi.fn(),
  onOpenAisleDrilldown: vi.fn(),
};

describe('AnalyticsCostsTab', () => {
  it('shows KPI skeletons while cost summary loads', () => {
    const { container } = render(
      <AnalyticsCostsTab
        costSummary={undefined}
        isLoading
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-costs-tab')).toBeInTheDocument();
    expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });

  it('shows backend cost warnings without inventing provider unit cost', () => {
    render(
      <AnalyticsCostsTab
        costSummary={costSummaryData}
        isLoading={false}
        isError={false}
        onGoToCompare={vi.fn()}
        drilldown={drilldown}
      />
    );
    expect(screen.getByTestId('analytics-cost-warnings')).toBeInTheDocument();
    expect(screen.getByTestId('analytics-cost-warning-PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE')).toBeInTheDocument();
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
});
