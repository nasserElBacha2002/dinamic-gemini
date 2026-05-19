import type { TFunction } from 'i18next';
import type { AisleIssueRow, ManualInterventionCategory, QualityPatternRow } from '../../../analytics/types';
import { translateQualityIssueType } from '../../../analytics/adapters/metricsFormatters';
import { numberOrZero } from '../../../analytics/adapters/metricsFormatters';
import { formatMetricValue } from '../analyticsCostFormatters';
import { buildAisleEntityKey } from '../aisleEntityKeys';
import {
  CHART_TOP_N,
  QUALITY_AISLE_ATTENTION_TOP_N,
  topByValue,
  type BarChartDatum,
  type SegmentDatum,
} from './sharedChartBuilders';

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
    id: buildAisleEntityKey(row.inventory_id, row.aisle_id),
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

export function buildTopAislesAttention(
  rows: readonly AisleIssueRow[],
  limit = CHART_TOP_N
): AisleIssueRow[] {
  return [...rows]
    .sort((a, b) => b.needs_review_count - a.needs_review_count)
    .slice(0, limit);
}

export function buildPrimaryQualityIssue(rows: readonly QualityPatternRow[]): string | null {
  const ranked = buildQualityIssueChartData(rows);
  return ranked[0]?.label ?? null;
}
