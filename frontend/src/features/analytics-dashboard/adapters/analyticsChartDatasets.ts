import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type {
  AnalyticsSummaryResponse,
  AisleIssueRow,
  InventoryPerformanceRow,
  ManualInterventionCategory,
  QualityPatternRow,
} from '../../analytics/types';
import { translateQualityIssueType } from '../../analytics/adapters/metricsFormatters';
import type { DonutSegment } from '../components/charts/DonutChart';
import { captureStatusLabel } from './analyticsCostFormatters';
import { formatLlmCostAmount, formatMetricValue } from './analyticsCostFormatters';
import { numberOrZero } from '../../analytics/adapters/metricsFormatters';

export const CHART_TOP_N = 5;

/** Top aisles shown on the Summary tab attention panel (progressive disclosure). */
export const SUMMARY_ATTENTION_TOP_N = 3;

/** Top aisles ranked on the Quality tab. */
export const QUALITY_AISLE_ATTENTION_TOP_N = 5;

export interface BarChartDatum {
  id: string;
  label: string;
  value: number;
  displayValue: string;
}

function topByValue<T>(
  items: readonly T[],
  getValue: (item: T) => number | null | undefined,
  getLabel: (item: T) => string,
  getId: (item: T, index: number) => string,
  formatDisplay: (value: number) => string,
  limit = CHART_TOP_N
): BarChartDatum[] {
  return items
    .map((item, index) => {
      const value = getValue(item);
      if (value == null || !Number.isFinite(value) || value <= 0) return null;
      return {
        id: getId(item, index),
        label: getLabel(item),
        value,
        displayValue: formatDisplay(value),
      };
    })
    .filter((x): x is BarChartDatum => x != null)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

export function buildCostByProviderChartData(
  data: AnalyticsCostSummaryResponse | null | undefined
): BarChartDatum[] {
  return topByValue(
    data?.by_provider_model ?? [],
    (r) => r.total_cost,
    (r) => `${r.provider_name ?? '—'} / ${r.model_name ?? '—'}`,
    (r, i) => `provider-${r.provider_name ?? ''}-${r.model_name ?? ''}-${i}`,
    formatLlmCostAmount
  );
}

export function buildCostByInventoryChartData(
  data: AnalyticsCostSummaryResponse | null | undefined
): BarChartDatum[] {
  return topByValue(
    data?.by_inventory ?? [],
    (r) => r.total_cost,
    (r) => r.inventory_name ?? r.inventory_id,
    (r) => r.inventory_id,
    formatLlmCostAmount
  );
}

export function buildCostByAisleChartData(
  data: AnalyticsCostSummaryResponse | null | undefined
): BarChartDatum[] {
  return topByValue(
    data?.by_aisle ?? [],
    (r) => r.total_cost,
    (r) => `${r.aisle_code ?? r.aisle_id} (${r.inventory_name ?? r.inventory_id})`,
    (r) => r.aisle_id,
    formatLlmCostAmount
  );
}

export function buildCaptureStatusChartData(
  data: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
): BarChartDatum[] {
  return (data?.by_capture_status ?? [])
    .map((row) => {
      if (!Number.isFinite(row.jobs_total) || row.jobs_total <= 0) return null;
      return {
        id: row.capture_status,
        label: captureStatusLabel(row.capture_status, t),
        value: row.jobs_total,
        displayValue: formatMetricValue(row.jobs_total, 'integer'),
      };
    })
    .filter((x): x is BarChartDatum => x != null);
}

export function buildQualityIssueChartData(rows: readonly QualityPatternRow[]): BarChartDatum[] {
  return topByValue(
    rows,
    (r) => r.count,
    (r) => r.issue_type,
    (r) => r.issue_type,
    (v) => formatMetricValue(v, 'integer'),
    CHART_TOP_N
  );
}

export function buildLocalizedQualityIssueChartData(
  rows: readonly QualityPatternRow[],
  t: TFunction
): BarChartDatum[] {
  return topByValue(
    rows,
    (r) => r.count,
    (r) => translateQualityIssueType(r.issue_type, t),
    (r) => r.issue_type,
    (v) => formatMetricValue(v, 'integer'),
    CHART_TOP_N
  ).map((bar) => {
    const row = rows.find((r) => r.issue_type === bar.id);
    if (row?.percentage != null && Number.isFinite(row.percentage)) {
      return { ...bar, displayValue: `${bar.displayValue} · ${(row.percentage * 100).toFixed(1)} %` };
    }
    return bar;
  });
}

export function buildAislePendingReviewChartData(
  rows: readonly AisleIssueRow[],
  t: TFunction,
  limit = QUALITY_AISLE_ATTENTION_TOP_N
): BarChartDatum[] {
  return buildTopAislesAttention(rows, limit).map((row) => ({
    id: `${row.inventory_id}-${row.aisle_id}`,
    label: `${row.aisle_code} · ${row.inventory_name}`,
    value: numberOrZero(row.needs_review_count),
    displayValue: t('analyticsDashboard.quality.aislePending', { count: row.needs_review_count }),
  }));
}

export function buildManualInterventionSegments(
  items: readonly ManualInterventionCategory[] | undefined,
  t: TFunction
): SegmentDatum[] {
  const source = items ?? [];
  const confirmed = numberOrZero(source.find((item) => item.category === 'confirmed')?.count);
  const corrected =
    numberOrZero(source.find((item) => item.category === 'qty_corrected')?.count) +
    numberOrZero(source.find((item) => item.category === 'sku_corrected')?.count);
  const segments: SegmentDatum[] = [];
  if (confirmed > 0) {
    segments.push({
      id: 'confirmed',
      label: t('analytics.category_confirmed'),
      value: confirmed,
      pct: 0,
    });
  }
  if (corrected > 0) {
    segments.push({
      id: 'corrected',
      label: t('analyticsDashboard.quality.manualCorrected'),
      value: corrected,
      pct: 0,
    });
  }
  const total = segments.reduce((sum, seg) => sum + seg.value, 0);
  if (total <= 0) return [];
  return segments.map((seg) => ({
    ...seg,
    pct: (seg.value / total) * 100,
  }));
}

export function buildProcessingTimeByInventoryData(
  rows: readonly InventoryPerformanceRow[]
): BarChartDatum[] {
  return topByValue(
    rows,
    (r) => r.average_processing_time_minutes,
    (r) => r.inventory_name,
    (r) => r.inventory_id,
    (v) => `${v.toFixed(1)} min`
  );
}

export interface SegmentDatum {
  id: string;
  label: string;
  value: number;
  pct: number;
}

export function buildAutoVsManualSegments(
  summary: AnalyticsSummaryResponse | null | undefined,
  t: TFunction
): SegmentDatum[] {
  const auto = summary?.auto_acceptance_rate;
  const manual = summary?.manual_correction_rate;
  if (auto == null && manual == null) return [];
  const segments: SegmentDatum[] = [];
  if (auto != null && Number.isFinite(auto)) {
    segments.push({
      id: 'auto',
      label: t('analytics.kpi_auto_acceptance'),
      value: auto,
      pct: auto * 100,
    });
  }
  if (manual != null && Number.isFinite(manual)) {
    segments.push({
      id: 'manual',
      label: t('analytics.kpi_manual_correction'),
      value: manual,
      pct: manual * 100,
    });
  }
  const remainder = Math.max(0, 1 - segments.reduce((s, x) => s + x.value, 0));
  if (remainder > 0.001) {
    segments.push({
      id: 'other',
      label: t('analyticsDashboard.visual.otherOutcomes'),
      value: remainder,
      pct: remainder * 100,
    });
  }
  return segments;
}

export function buildTopAislesAttention(
  rows: readonly AisleIssueRow[],
  limit = CHART_TOP_N
): AisleIssueRow[] {
  return [...rows]
    .sort((a, b) => b.needs_review_count - a.needs_review_count)
    .slice(0, limit);
}

export function buildProviderRunVolumeChartData(
  data: ObservabilityMetricsResponse | null | undefined,
  limit = CHART_TOP_N
): BarChartDatum[] {
  return topByValue(
    data?.by_provider_model ?? [],
    (r) => r.runs_total,
    (r) => `${r.provider_name ?? '—'} / ${r.model_name ?? '—'}`,
    (r, i) => `vol-${r.provider_name ?? ''}-${r.model_name ?? ''}-${i}`,
    (v) => formatMetricValue(v, 'integer'),
    limit
  );
}

export function buildProviderFailureRateChartData(
  data: ObservabilityMetricsResponse | null | undefined,
  limit = CHART_TOP_N
): BarChartDatum[] {
  return topByValue(
    data?.by_provider_model ?? [],
    (r) => r.failure_rate,
    (r) => `${r.provider_name ?? '—'} / ${r.model_name ?? '—'}`,
    (r, i) => `fail-${r.provider_name ?? ''}-${r.model_name ?? ''}-${i}`,
    (v) => `${(v * 100).toFixed(1)} %`,
    limit
  );
}

export function buildInventoryAutoAcceptChartData(
  rows: readonly InventoryPerformanceRow[],
  limit = CHART_TOP_N
): BarChartDatum[] {
  return topByValue(
    rows,
    (r) => r.auto_acceptance_rate,
    (r) => r.inventory_name ?? r.inventory_id,
    (r) => r.inventory_id,
    (v) => `${(v * 100).toFixed(1)} %`,
    limit
  );
}

export function buildInventoryCostPerUnitChartData(
  data: AnalyticsCostSummaryResponse | null | undefined,
  limit = CHART_TOP_N
): BarChartDatum[] {
  return topByValue(
    data?.by_inventory ?? [],
    (r) => r.cost_per_counted_unit,
    (r) => r.inventory_name ?? r.inventory_id,
    (r) => r.inventory_id,
    (v) => formatLlmCostAmount(v),
    limit
  );
}

export function buildProviderCostDonutSegments(
  data: AnalyticsCostSummaryResponse | null | undefined
): DonutSegment[] {
  return buildCostByProviderChartData(data).map((row) => ({
    id: row.id,
    label: row.label,
    value: row.value,
    displayValue: row.displayValue,
  }));
}

export function buildFastestInventoryInsight(
  rows: readonly InventoryPerformanceRow[]
): { name: string; minutes: number } | null {
  const ranked = [...rows]
    .filter((r) => r.average_processing_time_minutes != null && Number.isFinite(r.average_processing_time_minutes))
    .sort((a, b) => (a.average_processing_time_minutes ?? 0) - (b.average_processing_time_minutes ?? 0));
  const fastest = ranked[0];
  if (!fastest) return null;
  return {
    name: fastest.inventory_name,
    minutes: fastest.average_processing_time_minutes ?? 0,
  };
}

export function buildTopInventoryPerformanceRows(
  rows: readonly InventoryPerformanceRow[],
  limit = CHART_TOP_N
): InventoryPerformanceRow[] {
  return [...rows]
    .sort(
      (a, b) =>
        numberOrZero(b.processed_count ?? b.processed_positions) -
        numberOrZero(a.processed_count ?? a.processed_positions)
    )
    .slice(0, limit);
}

export function buildJobsCoverageDonutSegments(
  data: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
): DonutSegment[] {
  const totals = data?.totals;
  if (!totals) return [];
  const segments: DonutSegment[] = [];
  const withCost = numberOrZero(totals.jobs_with_cost);
  const without = numberOrZero(totals.jobs_without_cost);
  if (withCost > 0) {
    segments.push({
      id: 'with_cost',
      label: t('analyticsDashboard.costs.jobsWithCost'),
      value: withCost,
      displayValue: formatMetricValue(withCost, 'integer'),
    });
  }
  if (without > 0) {
    segments.push({
      id: 'without_cost',
      label: t('analyticsDashboard.costs.jobsWithoutCost'),
      value: without,
      displayValue: formatMetricValue(without, 'integer'),
    });
  }
  return segments;
}

export function buildTopCostInventoryRows(
  data: AnalyticsCostSummaryResponse | null | undefined,
  limit = CHART_TOP_N
): AnalyticsCostSummaryResponse['by_inventory'] {
  return [...(data?.by_inventory ?? [])]
    .filter((r) => r.total_cost != null && Number.isFinite(r.total_cost) && r.total_cost > 0)
    .sort((a, b) => (b.total_cost ?? 0) - (a.total_cost ?? 0))
    .slice(0, limit);
}

export function buildTopCostAisleRows(
  data: AnalyticsCostSummaryResponse | null | undefined,
  limit = CHART_TOP_N
): AnalyticsCostSummaryResponse['by_aisle'] {
  return [...(data?.by_aisle ?? [])]
    .filter((r) => r.total_cost != null && Number.isFinite(r.total_cost) && r.total_cost > 0)
    .sort((a, b) => (b.total_cost ?? 0) - (a.total_cost ?? 0))
    .slice(0, limit);
}

export function buildCaptureStatusDonutSegments(
  data: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
): DonutSegment[] {
  return buildCaptureStatusChartData(data, t).map((row) => ({
    id: row.id,
    label: row.label,
    value: row.value,
    displayValue: row.displayValue,
  }));
}

export function buildAutoVsManualDonutSegments(
  summary: AnalyticsSummaryResponse | null | undefined,
  t: TFunction
): DonutSegment[] {
  return buildAutoVsManualSegments(summary, t).map((seg) => ({
    id: seg.id,
    label: seg.label,
    value: seg.value,
    displayValue: `${seg.pct.toFixed(1)} %`,
  }));
}

export function buildTopProviderInsight(
  data: ObservabilityMetricsResponse | null | undefined
): { label: string; runs: number } | null {
  const ranked = buildProviderRunVolumeChartData(data);
  const top = ranked[0];
  if (!top) return null;
  return { label: top.label, runs: top.value };
}

export function buildSlowestInventoryInsight(
  rows: readonly InventoryPerformanceRow[]
): { name: string; minutes: number } | null {
  const ranked = buildProcessingTimeByInventoryData(rows);
  const top = ranked[0];
  if (!top) return null;
  const minutes = parseFloat(top.displayValue.replace(/[^\d.]/g, ''));
  return { name: top.label, minutes: Number.isFinite(minutes) ? minutes : 0 };
}

export function buildPrimaryQualityIssue(
  rows: readonly QualityPatternRow[]
): string | null {
  const ranked = buildQualityIssueChartData(rows);
  return ranked[0]?.label ?? null;
}
