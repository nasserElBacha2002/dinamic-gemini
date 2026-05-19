import { describe, it, expect } from 'vitest';
import type { AisleBenchmarkCompareManyResponse, BenchmarkRunCompareSide, LlmCostSnapshot } from '../src/api/types';
import {
  buildCompareBenchmarkCharts,
  buildCompareExecutiveSummary,
  buildDeltaKpiModels,
  buildRunBenchmarkCards,
  formatRunCostPerUnit,
  getRunCostPerUnitAmount,
  hasValidRunCost,
} from '../src/features/analytics/compare/compareBenchmarkViewModel';

const t = (key: string) => key;

function costSnapshot(
  total = '1.5',
  status: LlmCostSnapshot['capture_status'] = 'exact',
  currency = 'USD'
): LlmCostSnapshot {
  return {
    provider: 'p',
    model: 'm',
    billing_currency: currency,
    pricing_available: true,
    usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
    pricing_snapshot: { billing_currency: currency, pricing_source: 'test' },
    computed_cost: { total_cost: total, currency },
    capture_status: status,
    capture_notes: [],
  };
}

function job(
  id: string,
  qty: number,
  cost?: LlmCostSnapshot | null,
  execSeconds?: number | null
): BenchmarkRunCompareSide {
  return {
    job_id: id,
    status: 'succeeded',
    provider_name: 'prov',
    model_name: id,
    created_at: '2026-01-01T00:00:00Z',
    execution_time_seconds: execSeconds ?? 10,
    metrics: {
      raw_rows_considered: 1,
      consolidated_positions: 5,
      total_quantity: qty,
      unknown_internal_code_count: 0,
      needs_review_count: 1,
    },
    llm_cost_snapshot: cost ?? null,
  };
}

function compareData(overrides?: Partial<AisleBenchmarkCompareManyResponse>): AisleBenchmarkCompareManyResponse {
  return {
    inventory_id: 'inv-1',
    aisle_id: 'aisle-1',
    workflow: 'benchmark_compare_many',
    read_only: true,
    baseline_job_id: 'job-1',
    jobs: [job('job-1', 10, costSnapshot('1.0')), job('job-2', 0, costSnapshot('2.0')), job('job-3', 5, null)],
    comparisons: [
      {
        baseline_job_id: 'job-1',
        target_job_id: 'job-2',
        diff_summary: {
          keys_only_in_a: 0,
          keys_only_in_b: 0,
          keys_in_both: 1,
          quantity_changed: 1,
          sku_changed: 0,
          position_code_changed: 0,
        },
        delta: {
          total_quantity_diff: 5,
          consolidated_positions_diff: 0,
          unknown_internal_code_diff: 0,
          needs_review_diff: 1,
          execution_time_delta: 5,
        },
        diff_rows: [],
        diff_rows_truncated: false,
      },
    ],
    summary: {
      job_count: 3,
      baseline_job_id: 'job-1',
      max_total_quantity: 10,
      min_total_quantity: 0,
      max_needs_review: 1,
      min_needs_review: 1,
      max_consolidated_positions: 5,
      min_consolidated_positions: 5,
      max_unknown_internal_code_count: 0,
      min_unknown_internal_code_count: 0,
      min_execution_time_seconds: 10,
      max_execution_time_seconds: 10,
    },
    raw_fetch_truncated: [],
    ...overrides,
  };
}

describe('compareBenchmarkViewModel', () => {
  it('unknown capture_status with numeric cost does not count as valid run cost', () => {
    const snap = costSnapshot('9.99', 'exact');
    snap.capture_status = 'legacy' as LlmCostSnapshot['capture_status'];
    const unknownStatusJob = job('j', 10, snap);
    expect(hasValidRunCost(unknownStatusJob)).toBe(false);
    expect(getRunCostPerUnitAmount(unknownStatusJob)).toBeNull();
  });

  it('buildCompareExecutiveSummary omits aggregate cost when no run has valid cost', () => {
    const data = compareData({
      jobs: [job('job-1', 10, null), job('job-2', 10, null)],
    });
    const model = buildCompareExecutiveSummary(data, t);
    expect(model.selectedRunsCostValue).toBe('compare_many.benchmark.notAvailable');
  });

  it('same currency displays total and range with currency', () => {
    const data = compareData({
      jobs: [job('job-1', 10, costSnapshot('1.0', 'exact', 'USD')), job('job-2', 8, costSnapshot('2.0', 'exact', 'USD'))],
    });
    const model = buildCompareExecutiveSummary(data, t);
    expect(model.selectedRunsCostValue).toContain('USD');
    expect(model.costRangeValue).toContain('USD');
    expect(model.mixedCurrencyHelper).toBeNull();
  });

  it('mixed currencies make selected total and range unavailable', () => {
    const data = compareData({
      jobs: [
        job('job-1', 10, costSnapshot('1.0', 'exact', 'USD')),
        job('job-2', 10, costSnapshot('2.0', 'exact', 'EUR')),
      ],
    });
    const model = buildCompareExecutiveSummary(data, t);
    expect(model.selectedRunsCostValue).toBe('compare_many.benchmark.notAvailable');
    expect(model.costRangeValue).toBe('compare_many.benchmark.notAvailable');
    expect(model.mixedCurrencyHelper).toBe('compare_many.benchmark.mixedCurrencyHelper');
  });

  it('formatRunCostPerUnit is not available when cost missing', () => {
    expect(formatRunCostPerUnit(job('j', 10, null), t)).toBe('compare_many.benchmark.notAvailable');
    expect(hasValidRunCost(job('j', 10, null))).toBe(false);
  });

  it('formatRunCostPerUnit is not available when quantity is zero', () => {
    expect(formatRunCostPerUnit(job('j', 0, costSnapshot()), t)).toBe('compare_many.benchmark.notAvailable');
    expect(getRunCostPerUnitAmount(job('j', 0, costSnapshot()))).toBeNull();
  });

  it('formatRunCostPerUnit computes when cost and quantity are valid', () => {
    const amount = getRunCostPerUnitAmount(job('j', 10, costSnapshot('2.0')));
    expect(amount).toBeCloseTo(0.2, 5);
  });

  it('buildDeltaKpiModels uses human duration for time delta', () => {
    const data = compareData();
    const jobsById = new Map(data.jobs.map((j) => [j.job_id, j]));
    const rows = buildDeltaKpiModels(data, jobsById, data.comparisons, t);
    const timeKpi = rows[0]?.kpis.find((k) => k.id === 'time');
    expect(timeKpi?.value).toBe('+5s');
  });

  it('buildDeltaKpiModels marks lower cost delta as positive and higher as negative', () => {
    const data = compareData({
      jobs: [job('job-1', 10, costSnapshot('2.0')), job('job-2', 10, costSnapshot('3.0'))],
    });
    const jobsById = new Map(data.jobs.map((j) => [j.job_id, j]));
    const rows = buildDeltaKpiModels(data, jobsById, data.comparisons, t);
    const costKpi = rows[0]?.kpis.find((k) => k.id === 'cost');
    expect(costKpi?.tone).toBe('negative');

    const cheaper = compareData({
      jobs: [job('job-1', 10, costSnapshot('3.0')), job('job-2', 10, costSnapshot('1.0'))],
      comparisons: [
        {
          ...data.comparisons[0],
          target_job_id: 'job-2',
        },
      ],
    });
    const cheaperRows = buildDeltaKpiModels(
      cheaper,
      new Map(cheaper.jobs.map((j) => [j.job_id, j])),
      cheaper.comparisons,
      t
    );
    expect(cheaperRows[0]?.kpis.find((k) => k.id === 'cost')?.tone).toBe('positive');
  });

  it('quantity and consolidated deltas are neutral', () => {
    const data = compareData();
    const jobsById = new Map(data.jobs.map((j) => [j.job_id, j]));
    const rows = buildDeltaKpiModels(data, jobsById, data.comparisons, t);
    const qty = rows[0]?.kpis.find((k) => k.id === 'quantity');
    const consolidated = rows[0]?.kpis.find((k) => k.id === 'consolidated');
    expect(qty?.tone).toBe('neutral');
    expect(consolidated?.tone).toBe('neutral');
  });

  it('review delta includes contextual helper', () => {
    const data = compareData();
    const jobsById = new Map(data.jobs.map((j) => [j.job_id, j]));
    const rows = buildDeltaKpiModels(data, jobsById, data.comparisons, t);
    const review = rows[0]?.kpis.find((k) => k.id === 'review');
    expect(review?.helper).toBe('compare_many.benchmark.contextualReviewHelper');
  });

  it('buildRunBenchmarkCards exposes cost per unit unavailable for zero quantity', () => {
    const data = compareData();
    const cards = buildRunBenchmarkCards(data, ['job-1', 'job-2', 'job-3'], t);
    const zeroQty = cards.find((c) => c.jobId === 'job-2');
    expect(zeroQty?.costPerUnitValue).toBe('compare_many.benchmark.notAvailable');
  });

  it('buildCompareBenchmarkCharts returns empty costPerRun when all costs are missing', () => {
    const data = compareData({
      jobs: [job('job-1', 10, null), job('job-2', 10, null)],
    });
    const charts = buildCompareBenchmarkCharts(data, ['job-1', 'job-2'], t);
    expect(charts.costPerRun.data).toHaveLength(0);
    expect(charts.costPerUnit.data).toHaveLength(0);
  });

  it('buildCompareBenchmarkCharts returns empty costPerUnit when quantity is zero', () => {
    const data = compareData({
      jobs: [job('job-1', 0, costSnapshot('1.0')), job('job-2', 10, costSnapshot('2.0'))],
    });
    const charts = buildCompareBenchmarkCharts(data, ['job-1', 'job-2'], t);
    expect(charts.costPerRun.data.length).toBeGreaterThan(0);
    expect(charts.costPerUnit.data).toHaveLength(1);
    expect(charts.costPerUnit.data[0]?.id).toBe('job-2');
  });
});
