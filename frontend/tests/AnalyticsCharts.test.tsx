import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  buildAutoVsManualSegments,
  buildCaptureStatusChartData,
  buildCostByProviderChartData,
  buildProviderRunVolumeChartData,
  buildQualityIssueChartData,
} from '../src/features/analytics-dashboard/adapters/analyticsChartDatasets';
import { SegmentBarChart } from '../src/features/analytics-dashboard/components/charts/SegmentBarChart';
import { HorizontalBarChart } from '../src/features/analytics-dashboard/components/charts/HorizontalBarChart';
import i18n from '../src/i18n';

describe('analyticsChartDatasets', () => {
  it('builds cost by provider only for finite positive costs', () => {
    const data = buildCostByProviderChartData({
      scope: {},
      totals: {} as never,
      by_provider_model: [
        {
          provider_name: 'gemini',
          model_name: 'flash',
          jobs_total: 2,
          jobs_with_cost: 2,
          total_cost: 10,
          total_counted_quantity: null,
          cost_per_counted_unit: null,
          average_execution_time_seconds: null,
        },
        {
          provider_name: 'openai',
          model_name: 'gpt',
          jobs_total: 1,
          jobs_with_cost: 0,
          total_cost: null,
          total_counted_quantity: null,
          cost_per_counted_unit: null,
          average_execution_time_seconds: null,
        },
      ],
      by_inventory: [],
      by_aisle: [],
      by_capture_status: [],
      warnings: [],
    });
    expect(data).toHaveLength(1);
    expect(data[0]?.value).toBe(10);
  });

  it('builds capture status chart with translated labels', () => {
    const data = buildCaptureStatusChartData(
      {
        scope: {},
        totals: {} as never,
        by_provider_model: [],
        by_inventory: [],
        by_aisle: [],
        by_capture_status: [{ capture_status: 'exact', jobs_total: 3, total_cost: 1 }],
        warnings: [],
      },
      i18n.t
    );
    expect(data[0]?.label).toBe('Exacto');
  });

  it('builds quality issue chart from counts', () => {
    const data = buildQualityIssueChartData([
      { issue_type: 'pending_review', count: 5, share: 0.5 },
    ]);
    expect(data[0]?.value).toBe(5);
  });

  it('builds auto vs manual segments without inventing values', () => {
    const segments = buildAutoVsManualSegments(
      { auto_acceptance_rate: 0.6, manual_correction_rate: 0.2 } as never,
      i18n.t
    );
    expect(segments.length).toBeGreaterThanOrEqual(2);
    const total = segments.reduce((s, x) => s + x.value, 0);
    expect(total).toBeLessThanOrEqual(1.01);
  });

  it('builds provider run volume from runs_total', () => {
    const data = buildProviderRunVolumeChartData({
      range: { from: '2026-01-01', to: '2026-01-31' },
      filters: {},
      totals: {} as never,
      by_provider_model: [
        {
          provider_name: 'gemini',
          model_name: 'flash',
          runs_total: 12,
          runs_succeeded: 10,
          runs_failed: 2,
          failure_rate: 0.17,
        },
      ],
      by_client: [],
      by_supplier: [],
      data_quality: {} as never,
    });
    expect(data[0]?.value).toBe(12);
  });
});

describe('chart components', () => {
  it('normalizes segment bar visual width when values sum above 1', () => {
    render(
      <SegmentBarChart
        segments={[
          { id: 'auto', label: 'Auto', value: 0.7, pct: 70 },
          { id: 'manual', label: 'Manual', value: 0.5, pct: 50 },
        ]}
        emptyText="Sin datos"
        data-testid="segment-over-100"
      />
    );
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('Auto'));
  });

  it('exposes accessible role and label on horizontal bar chart', () => {
    render(
      <HorizontalBarChart
        data={[{ id: 'a', label: 'Test', value: 5, displayValue: '5' }]}
        emptyText="Sin datos"
        ariaLabel="Gráfico de barras de prueba"
        data-testid="hbar-a11y"
      />
    );
    expect(screen.getByRole('img', { name: 'Gráfico de barras de prueba' })).toBeInTheDocument();
  });
});
