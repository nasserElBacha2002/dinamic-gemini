import type { ObservabilityMetricsResponse } from '../../../../api/types';
import { formatMetricValue } from '../analyticsCostFormatters';
import { CHART_TOP_N, rankTopN, topByValue, type BarChartDatum } from './sharedChartBuilders';

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
  return rankTopN({
    items: data?.by_provider_model ?? [],
    getValue: (r) => r.failure_rate,
    getLabel: (r) => `${r.provider_name ?? '—'} / ${r.model_name ?? '—'}`,
    getId: (r, i) => `fail-${r.provider_name ?? ''}-${r.model_name ?? ''}-${i}`,
    formatDisplay: (v) => `${(v * 100).toFixed(1)} %`,
    limit,
  });
}

export function buildTopProviderInsight(
  data: ObservabilityMetricsResponse | null | undefined
): { label: string; runs: number } | null {
  const ranked = buildProviderRunVolumeChartData(data);
  const top = ranked[0];
  if (!top) return null;
  return { label: top.label, runs: top.value };
}
