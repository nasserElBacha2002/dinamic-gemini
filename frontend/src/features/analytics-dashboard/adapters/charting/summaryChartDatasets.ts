import type { TFunction } from 'i18next';
import type { AnalyticsSummaryResponse } from '../../../analytics/types';
import type { DonutSegment } from '../../components/charts/DonutChart';
import type { SegmentDatum } from './sharedChartBuilders';

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
