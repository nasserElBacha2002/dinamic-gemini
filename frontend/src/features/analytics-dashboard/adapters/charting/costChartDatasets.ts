import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryResponse } from '../../../../api/types';
import type { DonutSegment } from '../../components/charts/DonutChart';
import { buildAisleEntityKey } from '../aisleEntityKeys';
import { captureStatusLabel, formatLlmCostAmount, formatMetricValue } from '../analyticsCostFormatters';
import { numberOrZero } from '../../../analytics/adapters/metricsFormatters';
import { CHART_TOP_N, rankTopN, topByValue, type BarChartDatum } from './sharedChartBuilders';

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
    (r) => buildAisleEntityKey(r.inventory_id, r.aisle_id),
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

export function buildInventoryCostPerUnitChartData(
  data: AnalyticsCostSummaryResponse | null | undefined,
  limit = CHART_TOP_N
): BarChartDatum[] {
  return rankTopN({
    items: data?.by_inventory ?? [],
    getValue: (r) => r.cost_per_counted_unit,
    getLabel: (r) => r.inventory_name ?? r.inventory_id,
    getId: (r) => r.inventory_id,
    formatDisplay: (v) => formatLlmCostAmount(v),
    limit,
  });
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
