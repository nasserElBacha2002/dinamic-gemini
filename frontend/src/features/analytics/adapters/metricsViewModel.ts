import type { InventoryPerformanceRow } from '../types';
import { compareValues } from './metricsFormatters';

export function sortInventoryRows(
  rows: readonly InventoryPerformanceRow[],
  sortBy: string,
  sortDir: 'asc' | 'desc'
): InventoryPerformanceRow[] {
  const direction = sortDir === 'asc' ? 1 : -1;
  const getValue = (row: InventoryPerformanceRow): number | string | null | undefined => {
    switch (sortBy) {
      case 'created':
        return row.inventory_created_at;
      case 'aisles':
        return row.aisles_count ?? row.total_aisles;
      case 'positions':
        return row.positions_count ?? row.total_positions;
      case 'processed':
        return row.processed_count ?? row.processed_positions;
      case 'auto_accept':
        return row.auto_acceptance_rate ?? null;
      case 'manual_correction':
        return row.manual_correction_rate ?? row.correction_rate;
      case 'unidentified_product':
        return row.unidentified_product_rate ?? null;
      case 'invalid_tr':
        return row.invalid_traceability_rate;
      case 'avg_conf':
        return row.avg_confidence;
      case 'avg_processing':
        return row.average_processing_time_minutes ?? null;
      case 'proc':
        return row.processing_success_rate;
      case 'name':
      default:
        return row.inventory_name;
    }
  };
  return [...rows].sort((left, right) => {
    const result = compareValues(getValue(left), getValue(right));
    if (result !== 0) return result * direction;
    return left.inventory_name.localeCompare(right.inventory_name) * direction;
  });
}
