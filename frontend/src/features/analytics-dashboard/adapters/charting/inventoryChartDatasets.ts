import type { InventoryPerformanceRow } from '../../../analytics/types';
import { numberOrZero } from '../../../analytics/adapters/metricsFormatters';
import { CHART_TOP_N, rankTopN, topByValue, type BarChartDatum } from './sharedChartBuilders';

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

export function buildInventoryAutoAcceptChartData(
  rows: readonly InventoryPerformanceRow[],
  limit = CHART_TOP_N
): BarChartDatum[] {
  return rankTopN({
    items: rows,
    getValue: (r) => r.auto_acceptance_rate,
    getLabel: (r) => r.inventory_name ?? r.inventory_id,
    getId: (r) => r.inventory_id,
    formatDisplay: (v) => `${(v * 100).toFixed(1)} %`,
    limit,
  });
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

export function buildSlowestInventoryInsight(
  rows: readonly InventoryPerformanceRow[]
): { name: string; minutes: number } | null {
  const ranked = buildProcessingTimeByInventoryData(rows);
  const top = ranked[0];
  if (!top) return null;
  const minutes = parseFloat(top.displayValue.replace(/[^\d.]/g, ''));
  return { name: top.label, minutes: Number.isFinite(minutes) ? minutes : 0 };
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
