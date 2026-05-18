import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import {
  captureStatusLabel,
  formatMetricValue,
} from './analyticsCostFormatters';
import { mapCostWarnings, type AnalyticsCostWarningModel } from './analyticsCostWarnings';

export interface MetricCardModel {
  label: string;
  value: string;
  description?: string;
  unavailable?: boolean;
}

function unavailableCard(label: string, t: TFunction, description?: string): MetricCardModel {
  return {
    label,
    value: t('analyticsDashboard.costs.notAvailable'),
    description: description ?? t('analyticsDashboard.costs.notAvailableHelper'),
    unavailable: true,
  };
}

function isValidNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function numericCard(
  label: string,
  value: number | null | undefined,
  kind: 'cost' | 'quantity' | 'costPerUnit' | 'integer',
  t: TFunction,
  description?: string
): MetricCardModel {
  if (!isValidNumber(value)) {
    return unavailableCard(label, t, description);
  }
  return {
    label,
    value: formatMetricValue(value, kind),
    description,
  };
}

export function buildOverviewCostKpis(
  data: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
): MetricCardModel[] {
  const totals = data?.totals;
  return [
    numericCard(t('analyticsDashboard.costs.totalCost'), totals?.total_cost, 'cost', t, t('analyticsDashboard.costs.llmCostHint')),
    numericCard(t('analyticsDashboard.costs.totalQuantity'), totals?.total_counted_quantity, 'quantity', t),
    numericCard(t('analyticsDashboard.costs.costPerUnit'), totals?.cost_per_counted_unit, 'costPerUnit', t),
    numericCard(t('analyticsDashboard.costs.jobsWithCost'), totals?.jobs_with_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.jobsWithoutCost'), totals?.jobs_without_cost, 'integer', t),
  ];
}

export function buildCostExecutiveKpis(
  data: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
): MetricCardModel[] {
  const totals = data?.totals;
  return [
    numericCard(t('analyticsDashboard.costs.totalCost'), totals?.total_cost, 'cost', t, t('analyticsDashboard.costs.llmCostHint')),
    numericCard(t('analyticsDashboard.costs.totalQuantity'), totals?.total_counted_quantity, 'quantity', t),
    numericCard(t('analyticsDashboard.costs.costPerUnit'), totals?.cost_per_counted_unit, 'costPerUnit', t),
    numericCard(t('analyticsDashboard.costs.jobsWithCost'), totals?.jobs_with_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.jobsWithoutCost'), totals?.jobs_without_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.exactCostJobs'), totals?.jobs_with_exact_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.estimatedCostJobs'), totals?.jobs_with_estimated_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.partialCostJobs'), totals?.jobs_with_partial_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.unavailableCostJobs'), totals?.jobs_with_unavailable_cost, 'integer', t),
    numericCard(t('analyticsDashboard.costs.missingCostJobs'), totals?.jobs_with_missing_cost, 'integer', t),
  ];
}

export function buildCostWarnings(
  data: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
): AnalyticsCostWarningModel[] {
  return mapCostWarnings(data?.warnings ?? [], t);
}

export function buildCostByInventoryLookup(
  data: AnalyticsCostSummaryResponse | null | undefined
): Map<string, AnalyticsCostSummaryResponse['by_inventory'][number]> {
  const map = new Map<string, AnalyticsCostSummaryResponse['by_inventory'][number]>();
  for (const row of data?.by_inventory ?? []) {
    map.set(row.inventory_id, row);
  }
  return map;
}

export function buildCostByAisleLookup(
  data: AnalyticsCostSummaryResponse | null | undefined
): Map<string, AnalyticsCostSummaryResponse['by_aisle'][number]> {
  const map = new Map<string, AnalyticsCostSummaryResponse['by_aisle'][number]>();
  for (const row of data?.by_aisle ?? []) {
    map.set(row.aisle_id, row);
  }
  return map;
}

export function formatCostCell(
  value: number | null | undefined,
  kind: 'cost' | 'quantity' | 'costPerUnit' | 'duration',
  t: TFunction
): string {
  if (!isValidNumber(value)) {
    return t('analyticsDashboard.costs.notAvailable');
  }
  return formatMetricValue(value, kind);
}

export function formatCostCellWithLoading(
  isLoading: boolean,
  value: number | null | undefined,
  kind: 'cost' | 'quantity' | 'costPerUnit' | 'duration',
  t: TFunction
): string {
  if (isLoading) {
    return t('analyticsDashboard.costs.loading');
  }
  return formatCostCell(value, kind, t);
}

export function formatProviderUnitCost(
  value: number | null | undefined,
  t: TFunction
): { display: string; helper?: string } {
  if (!isValidNumber(value)) {
    return {
      display: t('analyticsDashboard.costs.notAvailable'),
      helper: t('analyticsDashboard.costs.providerUnitCostUnavailable'),
    };
  }
  return { display: formatMetricValue(value, 'costPerUnit') };
}

export type CostSummaryEmptyKind = 'no_jobs' | 'no_cost_snapshots';

export function getCostSummaryEmptyKind(
  data: AnalyticsCostSummaryResponse | null | undefined
): CostSummaryEmptyKind | null {
  const totals = data?.totals;
  if (!totals) return null;
  if (totals.jobs_total === 0) return 'no_jobs';
  if (totals.jobs_with_cost === 0) return 'no_cost_snapshots';
  return null;
}

export function costSummaryEmptyMessage(
  kind: CostSummaryEmptyKind,
  t: TFunction
): string {
  return kind === 'no_jobs'
    ? t('analyticsDashboard.costs.emptyNoJobs')
    : t('analyticsDashboard.costs.emptyNoCostSnapshots');
}

export function hasCostData(data: AnalyticsCostSummaryResponse | null | undefined): boolean {
  return Boolean(data?.totals);
}

export { captureStatusLabel };
