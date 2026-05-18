import { describe, it, expect } from 'vitest';
import {
  buildAutoVsManualSegments,
  buildCaptureStatusChartData,
  buildCostByProviderChartData,
  buildQualityIssueChartData,
} from '../src/features/analytics-dashboard/adapters/analyticsChartDatasets';
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
});
