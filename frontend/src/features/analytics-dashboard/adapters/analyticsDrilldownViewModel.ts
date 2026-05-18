import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryResponse, Inventory, JobSummary } from '../../../api/types';
import type { AisleIssueRow, InventoryPerformanceRow } from '../../analytics/types';
import { formatAvgProcessingMinutes, formatPct } from '../../analytics/adapters/metricsFormatters';
import {
  buildCostByAisleLookup,
  buildCostByInventoryLookup,
  buildCostWarnings,
  formatCostCell,
  type MetricCardModel,
} from './analyticsCostViewModel';
import { CHART_TOP_N } from './analyticsChartDatasets';
import { getCompareEligibility, type CompareEligibility } from '../types';

export const DRILLDOWN_AISLE_TOP_N = CHART_TOP_N;

export interface AisleContributionRow {
  aisleId: string;
  aisleCode: string;
  inventoryId: string;
  inventoryName: string;
  needsReviewCount: number;
  correctedCount: number;
  totalCost: number | null | undefined;
  totalQuantity: number | null | undefined;
  costPerUnit: number | null | undefined;
  totalExecutionSeconds: number | null | undefined;
  attentionStatus: string | null;
  unidentifiedCount: number;
  invalidTraceabilityCount: number;
}

export function findInventoryPerformanceRow(
  items: readonly InventoryPerformanceRow[] | undefined,
  inventoryId: string
): InventoryPerformanceRow | undefined {
  return items?.find((r) => r.inventory_id === inventoryId);
}

export function findAisleIssueRow(
  items: readonly AisleIssueRow[] | undefined,
  inventoryId: string,
  aisleId: string
): AisleIssueRow | undefined {
  return items?.find((r) => r.inventory_id === inventoryId && r.aisle_id === aisleId);
}

export function filterAislesForInventory(
  aisleIssues: readonly AisleIssueRow[] | undefined,
  inventoryId: string
): AisleIssueRow[] {
  return (aisleIssues ?? []).filter((r) => r.inventory_id === inventoryId);
}

export function buildAisleContributionRows(
  aisleIssues: readonly AisleIssueRow[],
  costSummary: AnalyticsCostSummaryResponse | null | undefined,
  inventoryId: string
): AisleContributionRow[] {
  const costByAisle = buildCostByAisleLookup(costSummary);
  return filterAislesForInventory(aisleIssues, inventoryId)
    .map((row) => {
      const cost = costByAisle.get(row.aisle_id);
      return {
        aisleId: row.aisle_id,
        aisleCode: row.aisle_code,
        inventoryId: row.inventory_id,
        inventoryName: row.inventory_name,
        needsReviewCount: row.needs_review_count,
        correctedCount: row.corrected_count,
        totalCost: cost?.total_cost,
        totalQuantity: cost?.total_counted_quantity,
        costPerUnit: cost?.cost_per_counted_unit,
        totalExecutionSeconds: cost?.total_execution_time_seconds,
        attentionStatus: row.most_common_issue,
        unidentifiedCount: row.unidentified_product_count ?? 0,
        invalidTraceabilityCount: row.invalid_traceability_count,
      };
    })
    .sort((a, b) => (b.totalCost ?? 0) - (a.totalCost ?? 0) || b.needsReviewCount - a.needsReviewCount)
    .slice(0, DRILLDOWN_AISLE_TOP_N);
}

export function buildInventoryDrilldownKpis(
  performance: InventoryPerformanceRow | undefined,
  costRow: AnalyticsCostSummaryResponse['by_inventory'][number] | undefined,
  aisleCount: number,
  t: TFunction,
  isCostLoading: boolean
): MetricCardModel[] {
  const unavailable = t('analyticsDashboard.costs.notAvailable');
  const loading = t('analyticsDashboard.costs.loading');

  const costValue = (
    value: number | null | undefined,
    kind: 'cost' | 'quantity' | 'costPerUnit' | 'integer' | 'duration'
  ) => {
    if (isCostLoading) return loading;
    if (value == null || !Number.isFinite(value)) return unavailable;
    return formatCostCell(value, kind, t);
  };

  return [
    {
      label: t('analyticsDashboard.costs.totalCost'),
      value: costValue(costRow?.total_cost, 'cost'),
      unavailable: !isCostLoading && costRow?.total_cost == null,
    },
    {
      label: t('analyticsDashboard.costs.totalQuantity'),
      value: costValue(costRow?.total_counted_quantity, 'quantity'),
      unavailable: !isCostLoading && costRow?.total_counted_quantity == null,
    },
    {
      label: t('analyticsDashboard.costs.costPerUnit'),
      value: costValue(costRow?.cost_per_counted_unit, 'costPerUnit'),
      unavailable: !isCostLoading && costRow?.cost_per_counted_unit == null,
    },
    {
      label: t('analyticsDashboard.drilldown.aisleCount'),
      value: String(aisleCount),
    },
    {
      label: t('analytics.column_positions'),
      value: String(performance?.positions_count ?? performance?.total_positions ?? '—'),
    },
    {
      label: t('analytics.column_auto_accept'),
      value: formatPct(performance?.auto_acceptance_rate),
    },
    {
      label: t('analytics.kpi_manual_correction_title'),
      value: formatPct(performance?.manual_correction_rate),
    },
    {
      label: t('analytics.column_unidentified_product'),
      value: formatPct(performance?.unidentified_product_rate),
    },
    {
      label: t('analytics.column_invalid_traceability'),
      value: formatPct(performance?.invalid_traceability_rate),
    },
    {
      label: t('analytics.column_avg_processing'),
      value: formatAvgProcessingMinutes(performance?.average_processing_time_minutes, null),
    },
    {
      label: t('analyticsDashboard.costs.jobsWithCost'),
      value: costValue(costRow?.jobs_with_cost, 'integer'),
      unavailable: !isCostLoading && costRow?.jobs_with_cost == null,
    },
  ];
}

export function buildAisleDrilldownKpis(
  aisle: AisleIssueRow | undefined,
  costRow: AnalyticsCostSummaryResponse['by_aisle'][number] | undefined,
  t: TFunction,
  isCostLoading: boolean
): MetricCardModel[] {
  const unavailable = t('analyticsDashboard.costs.notAvailable');
  const loading = t('analyticsDashboard.costs.loading');

  const costValue = (
    value: number | null | undefined,
    kind: 'cost' | 'quantity' | 'costPerUnit' | 'integer' | 'duration'
  ) => {
    if (isCostLoading) return loading;
    if (value == null || !Number.isFinite(value)) return unavailable;
    return formatCostCell(value, kind, t);
  };

  return [
    {
      label: t('analyticsDashboard.costs.totalCost'),
      value: costValue(costRow?.total_cost, 'cost'),
      unavailable: !isCostLoading && costRow?.total_cost == null,
    },
    {
      label: t('analyticsDashboard.costs.totalQuantity'),
      value: costValue(costRow?.total_counted_quantity, 'quantity'),
      unavailable: !isCostLoading && costRow?.total_counted_quantity == null,
    },
    {
      label: t('analyticsDashboard.costs.costPerUnit'),
      value: costValue(costRow?.cost_per_counted_unit, 'costPerUnit'),
      unavailable: !isCostLoading && costRow?.cost_per_counted_unit == null,
    },
    {
      label: t('analytics.column_total'),
      value: String(aisle?.total_results ?? '—'),
    },
    {
      label: t('analyticsDashboard.drilldown.reviewRequired'),
      value: String(aisle?.needs_review_count ?? '—'),
    },
    {
      label: t('analyticsDashboard.drilldown.correctedCount'),
      value: String(aisle?.corrected_count ?? '—'),
    },
    {
      label: t('analytics.column_unidentified_product'),
      value: String(aisle?.unidentified_product_count ?? 0),
    },
    {
      label: t('analytics.column_invalid_traceability'),
      value: String(aisle?.invalid_traceability_count ?? 0),
    },
    {
      label: t('analyticsDashboard.costs.totalExecutionTime'),
      value: costValue(costRow?.total_execution_time_seconds, 'duration'),
      unavailable: !isCostLoading && costRow?.total_execution_time_seconds == null,
    },
    {
      label: t('analyticsDashboard.costs.jobsWithCost'),
      value: costValue(costRow?.jobs_with_cost, 'integer'),
      unavailable: !isCostLoading && costRow?.jobs_with_cost == null,
    },
  ];
}

export function buildDrilldownWarnings(
  costSummary: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction
) {
  return buildCostWarnings(costSummary, t);
}

export function getCompareEligibilityForInventory(
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>,
  inventoryId: string
): CompareEligibility {
  return getCompareEligibility(inventoryProcessingModeById.get(inventoryId));
}

export function processingModeLabel(mode: string | undefined, t: TFunction): string {
  if (mode === 'test') return t('inventories.processing_mode_test');
  if (mode === 'production') return t('inventories.processing_mode_production');
  return t('common.em_dash');
}

export function filterCostAislesForInventory(
  costSummary: AnalyticsCostSummaryResponse | null | undefined,
  inventoryId: string
) {
  return (costSummary?.by_aisle ?? []).filter((r) => r.inventory_id === inventoryId);
}

export function lookupInventoryCost(
  costSummary: AnalyticsCostSummaryResponse | null | undefined,
  inventoryId: string
) {
  return buildCostByInventoryLookup(costSummary).get(inventoryId);
}

export function lookupAisleCost(
  costSummary: AnalyticsCostSummaryResponse | null | undefined,
  aisleId: string
) {
  return buildCostByAisleLookup(costSummary).get(aisleId);
}

export type DrilldownJobRow = {
  id: string;
  provider: string;
  model: string;
  status: string;
  startedAt: string;
  finishedAt: string;
  duration: string;
};

export function mapJobsForDrilldownTable(jobs: readonly JobSummary[], t: TFunction): DrilldownJobRow[] {
  return jobs.map((job) => {
    const started = job.started_at ?? job.created_at;
    const finished = job.finished_at ?? '—';
    let duration = '—';
    if (job.started_at && job.finished_at) {
      const ms = Date.parse(job.finished_at) - Date.parse(job.started_at);
      if (Number.isFinite(ms) && ms >= 0) {
        const mins = Math.round(ms / 60000);
        duration = `${mins} min`;
      }
    }
    return {
      id: job.id,
      provider: job.provider_name ?? t('observability.metrics.unknownId'),
      model: job.model_name ?? t('observability.metrics.unknownId'),
      status: job.status,
      startedAt: started,
      finishedAt: finished,
      duration,
    };
  });
}

export function resolveInventoryDisplayName(
  performance: InventoryPerformanceRow | undefined,
  inventoryMeta: Inventory | undefined,
  inventoryId: string
): string {
  return performance?.inventory_name ?? inventoryMeta?.name ?? inventoryId;
}
