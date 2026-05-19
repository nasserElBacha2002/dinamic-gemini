import { describe, it, expect } from 'vitest';
import {
  buildExecutivePositionKpis,
  buildExecutiveRunKpis,
  buildRunSummaryKpis,
  buildPositionSummaryKpis,
  EXECUTIVE_SUMMARY_KPI_LIMIT,
} from '../src/features/analytics-dashboard/adapters/analyticsDashboardViewModel';
import { buildTopAislesAttention, SUMMARY_ATTENTION_TOP_N } from '../src/features/analytics-dashboard/adapters/analyticsChartDatasets';
import i18n from '../src/i18n';

const summary = {
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
};

const observability = {
  totals: {
    runs_total: 10,
    runs_succeeded: 8,
    runs_failed: 2,
    failure_rate: 0.2,
    legacy_runs: 0,
    missing_reference_runs: 0,
    missing_prompt_config_runs: 0,
  },
  data_quality: { jobs_without_audit_snapshot: 1 },
  by_provider_model: [],
};

describe('executive summary KPI limits', () => {
  it('limits position executive KPIs to four tiles', () => {
    const executive = buildExecutivePositionKpis(summary, true, i18n.t);
    const full = buildPositionSummaryKpis(summary, true, i18n.t);
    expect(executive.length).toBeLessThanOrEqual(EXECUTIVE_SUMMARY_KPI_LIMIT);
    expect(full.length).toBeGreaterThan(executive.length);
    expect(executive.map((k) => k.label)).toContain(i18n.t('analyticsDashboard.kpi_positions_processed'));
  });

  it('limits run executive KPIs to four tiles', () => {
    const executive = buildExecutiveRunKpis(observability as never, i18n.t);
    const full = buildRunSummaryKpis(observability as never, i18n.t);
    expect(executive).toHaveLength(EXECUTIVE_SUMMARY_KPI_LIMIT);
    expect(full.length).toBeGreaterThan(executive.length);
  });

  it('limits summary attention aisles to top three', () => {
    const rows = Array.from({ length: 8 }, (_, i) => ({
      aisle_id: `a-${i}`,
      aisle_code: `A-${i}`,
      inventory_id: 'inv-1',
      inventory_name: 'DC',
      total_results: 5,
      needs_review_count: 10 - i,
      corrected_count: 0,
      unidentified_product_count: 0,
      invalid_traceability_count: 0,
      most_common_issue: null,
    }));
    const top = buildTopAislesAttention(rows, SUMMARY_ATTENTION_TOP_N);
    expect(top).toHaveLength(SUMMARY_ATTENTION_TOP_N);
    expect(top[0]?.aisle_id).toBe('a-0');
  });
});
