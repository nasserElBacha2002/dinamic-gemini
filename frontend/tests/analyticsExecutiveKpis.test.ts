import { describe, it, expect } from 'vitest';
import {
  buildHeroExecutiveKpis,
  HERO_EXECUTIVE_KPI_LIMIT,
} from '../src/features/analytics-dashboard/adapters/analyticsDashboardViewModel';
import { buildTopAislesAttention, SUMMARY_ATTENTION_TOP_N } from '../src/features/analytics-dashboard/adapters/analyticsChartDatasets';
import i18n from '../src/i18n';
import { EMPTY_ANALYTICS_COST_SCOPE } from './helpers/fixtures';

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
  settling_actions_per_day: null,
  period_day_count: 7,
  settling_actions_count: 0,
  positions_in_scope: 20,
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

const costSummary = {
  scope: EMPTY_ANALYTICS_COST_SCOPE,
  totals: {
    total_cost: 24.82,
    total_counted_quantity: 100,
    cost_per_counted_unit: 0.25,
    jobs_with_cost: 5,
    jobs_without_cost: 1,
  },
  by_provider_model: [],
  by_inventory: [],
  by_aisle: [],
  by_capture_status: [],
  warnings: [],
};

describe('hero executive KPIs', () => {
  it('returns exactly six hero KPIs', () => {
    const hero = buildHeroExecutiveKpis(summary, observability as never, costSummary as never, i18n.t, {
      costAvailable: true,
    });
    expect(hero).toHaveLength(HERO_EXECUTIVE_KPI_LIMIT);
    expect(hero.filter((k) => k.tier === 'primary')).toHaveLength(3);
    expect(hero.filter((k) => k.tier === 'secondary')).toHaveLength(3);
  });

  it('excludes low-priority diagnostic KPIs from hero', () => {
    const hero = buildHeroExecutiveKpis(summary, observability as never, costSummary as never, i18n.t, {
      costAvailable: true,
    });
    const labels = hero.map((k) => k.label);
    expect(labels).not.toContain(i18n.t('analytics.kpi_unidentified_title'));
    expect(labels).not.toContain(i18n.t('analytics.kpi_invalid_tr_title'));
    expect(labels).not.toContain(i18n.t('observability.metrics.kpiLegacy'));
    expect(labels).not.toContain(i18n.t('analyticsDashboard.kpi_jobs_without_snapshot'));
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
      low_confidence_count: 0,
      most_common_issue: null,
    }));
    const top = buildTopAislesAttention(rows, SUMMARY_ATTENTION_TOP_N);
    expect(top).toHaveLength(SUMMARY_ATTENTION_TOP_N);
    expect(top[0]?.aisle_id).toBe('a-0');
  });
});
