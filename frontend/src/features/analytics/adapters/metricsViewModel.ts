import type { ReactNode } from 'react';
import type { TFunction } from 'i18next';

export interface MetricsKpiCardView {
  label: string;
  value: ReactNode;
  description?: string;
}
import type {
  AnalyticsSummaryResponse,
  InventoryPerformanceRow,
  ManualInterventionCategory,
  QualityPatternRow,
} from '../types';
import { compareValues, formatAvgProcessingMinutes, formatPct, numberOrZero, qualityPriority } from './metricsFormatters';

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

export function orderQualityRows(rows: readonly QualityPatternRow[]): QualityPatternRow[] {
  return [...rows].sort(
    (left, right) =>
      qualityPriority(left.issue_type) - qualityPriority(right.issue_type) ||
      numberOrZero(right.count) - numberOrZero(left.count)
  );
}

export interface ManualInterventionViewModel {
  supportedInterventions: ManualInterventionCategory[];
  unsupportedInterventions: ManualInterventionCategory[];
  orderedSupportedInterventions: ManualInterventionCategory[];
  manualCorrectionCount: number;
}

export function buildManualInterventionViewModel(
  items: readonly ManualInterventionCategory[] | undefined
): ManualInterventionViewModel {
  const source = items ?? [];
  const supportedInterventions = source.filter((item: ManualInterventionCategory) => item.available && (item.count ?? 0) > 0);
  const unsupportedInterventions = source.filter((item: ManualInterventionCategory) => !item.available);
  const orderedSupportedInterventions = [...supportedInterventions].sort(
    (left, right) =>
      interventionPriorityForViewModel(left.category) - interventionPriorityForViewModel(right.category) ||
      numberOrZero(right.count) - numberOrZero(left.count)
  );
  const manualCorrectionCount =
    numberOrZero(source.find((item: ManualInterventionCategory) => item.category === 'qty_corrected')?.count) +
    numberOrZero(source.find((item: ManualInterventionCategory) => item.category === 'sku_corrected')?.count);
  return {
    supportedInterventions,
    unsupportedInterventions,
    orderedSupportedInterventions,
    manualCorrectionCount,
  };
}

export interface ResolutionFlowStageViewModel {
  label: string;
  value: number;
  helper: string;
}

export function buildResolutionFlowStages(
  input: {
    totalPositionsCount: number;
    pendingReviewCount: number;
    processedPositionsCount: number;
    reviewedPositionsCount: number;
    interventionPositionsCount: number;
    operatorMarkedUnknownCount: number;
    hasOperatorUnknownRate: boolean;
  },
  t: TFunction
): ResolutionFlowStageViewModel[] {
  const stages: ResolutionFlowStageViewModel[] = [
    {
      label: t('analytics.positions_in_scope'),
      value: input.totalPositionsCount,
      helper: t('analytics.positions_in_scope_help'),
    },
    {
      label: t('analytics.pending_review'),
      value: input.pendingReviewCount,
      helper: t('analytics.pending_review_help'),
    },
    {
      label: t('analytics.processed'),
      value: input.processedPositionsCount,
      helper: t('analytics.processed_help'),
    },
    {
      label: t('analytics.reviewed'),
      value: input.reviewedPositionsCount,
      helper: t('analytics.reviewed_help'),
    },
    {
      label: t('analytics.manual_touch'),
      value: input.interventionPositionsCount,
      helper: t('analytics.manual_touch_help'),
    },
  ];
  if (input.hasOperatorUnknownRate) {
    stages.push({
      label: t('analytics.operator_unknown'),
      value: input.operatorMarkedUnknownCount,
      helper: t('analytics.operator_unknown_help'),
    });
  }
  return stages;
}

export interface MetricsKpiCardViewModel {
  label: string;
  value: string;
  description: string;
}

export function buildMetricsKpiCards(
  summary: AnalyticsSummaryResponse | null | undefined,
  hasUnidentifiedProductRate: boolean,
  t: TFunction
): MetricsKpiCardViewModel[] {
  return [
    {
      label: t('analytics.kpi_auto_accept_title'),
      value: formatPct(summary?.auto_acceptance_rate),
      description: summary?.reviewed_positions_count
        ? t('analytics.kpi_fraction_reviewed', {
            numerator: Math.round((summary.auto_acceptance_rate ?? 0) * summary.reviewed_positions_count),
            denominator: summary.reviewed_positions_count,
          })
        : t('analytics.kpi_auto_accept_desc'),
    },
    {
      label: t('analytics.kpi_manual_correction_title'),
      value: formatPct(summary?.manual_correction_rate),
      description: summary?.reviewed_positions_count
        ? t('analytics.kpi_fraction_reviewed', {
            numerator: Math.round((summary.manual_correction_rate ?? 0) * summary.reviewed_positions_count),
            denominator: summary.reviewed_positions_count,
          })
        : t('analytics.kpi_manual_correction_desc'),
    },
    ...(hasUnidentifiedProductRate
      ? [
          {
            label: t('analytics.kpi_unidentified_title'),
            value: formatPct(summary?.unidentified_product_rate),
            description:
              summary?.unidentified_product_count != null && summary?.total_positions_in_scope
                ? t('analytics.kpi_fraction_scope', {
                    numerator: summary.unidentified_product_count,
                    denominator: summary.total_positions_in_scope,
                  })
                : t('analytics.kpi_unidentified_desc'),
          },
        ]
      : []),
    {
      label: t('analytics.kpi_processing_success_title'),
      value: formatPct(summary?.processing_success_rate),
      description: t('analytics.kpi_processing_success_desc'),
    },
    {
      label: t('analytics.kpi_avg_processing_title'),
      value: formatAvgProcessingMinutes(summary?.average_processing_time_minutes, summary?.average_processing_time_seconds),
      description: t('analytics.kpi_avg_processing_desc'),
    },
    {
      label: t('analytics.kpi_invalid_tr_title'),
      value: formatPct(summary?.invalid_traceability_rate),
      description: summary?.total_positions_in_scope
        ? t('analytics.kpi_fraction_scope', {
            numerator: Math.round((summary.invalid_traceability_rate ?? 0) * summary.total_positions_in_scope),
            denominator: summary.total_positions_in_scope,
          })
        : t('analytics.kpi_invalid_tr_desc'),
    },
  ];
}

export interface ScopeSummaryViewModel {
  inventoryLabel: string;
  aisleLabel: string;
  positions: number | null | undefined;
}

export function buildScopeSummary(
  input: {
    summary: AnalyticsSummaryResponse | null | undefined;
    selectedInventoryName: string | null;
    selectedAisleCode: string | null;
    hasInventorySelected: boolean;
  },
  t: TFunction
): ScopeSummaryViewModel | null {
  if (!input.summary) return null;
  return {
    inventoryLabel: input.selectedInventoryName ?? t('analytics.scope_inventory_all'),
    aisleLabel: input.selectedAisleCode
      ? input.selectedAisleCode
      : input.hasInventorySelected
        ? t('analytics.scope_aisle_inventory')
        : t('analytics.scope_aisle_all'),
    positions: input.summary.total_positions_in_scope ?? input.summary.positions_in_scope,
  };
}

function interventionPriorityForViewModel(category: string): number {
  switch (category) {
    case 'operator_marked_unknown':
      return 0;
    case 'qty_corrected':
      return 1;
    case 'sku_corrected':
      return 2;
    case 'confirmed':
      return 3;
    case 'deleted':
      return 4;
    case 'invalid':
      return 5;
    default:
      return 50;
  }
}
