import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsSummaryResponse, AisleIssueRow, InventoryPerformanceRow, QualityPatternRow } from '../../analytics/types';
import type { DonutSegment } from '../components/charts/DonutChart';
import { captureStatusLabel } from './analyticsCostFormatters';
import { formatLlmCostAmount, formatMetricValue } from './analyticsCostFormatters';

export const CHART_TOP_N = 5;

/** Top aisles shown on the Summary tab attention panel (progressive disclosure). */
export const SUMMARY_ATTENTION_TOP_N = 3;

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
  data: ObservabilityMetricsResponse | null | undefined
): BarChartDatum[] {
  return topByValue(
    data?.by_provider_model ?? [],
    (r) => r.runs_total,
    (r) => `${r.provider_name ?? '—'} / ${r.model_name ?? '—'}`,
    (r, i) => `vol-${r.provider_name ?? ''}-${r.model_name ?? ''}-${i}`,
    (v) => formatMetricValue(v, 'integer'),
    3
  );
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
