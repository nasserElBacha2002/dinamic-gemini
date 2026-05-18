import type { AnalyticsQueryParams } from '../analytics/types';
import type { ObservabilityMetricsQueryParams } from '../../api/observabilityApi';

export type AnalyticsDashboardTab =
  | 'summary'
  | 'quality'
  | 'time'
  | 'providers'
  | 'inventories'
  | 'aisles'
  | 'compare'
  | 'costs';

export interface AnalyticsDashboardFilters {
  dateFrom: string;
  dateTo: string;
  inventoryId: string;
  aisleId: string;
  clientId: string;
  clientSupplierId: string;
  providerName: string;
  modelName: string;
}

export interface AnalyticsDashboardFilterParams {
  analytics: AnalyticsQueryParams;
  observability: ObservabilityMetricsQueryParams;
}

export function buildFilterParams(filters: AnalyticsDashboardFilters): AnalyticsDashboardFilterParams {
  const fromIso = filters.dateFrom ? `${filters.dateFrom}T00:00:00.000Z` : undefined;
  const toIso = filters.dateTo ? `${filters.dateTo}T23:59:59.999Z` : undefined;
  return {
    analytics: {
      date_from: filters.dateFrom || undefined,
      date_to: filters.dateTo || undefined,
      inventory_id: filters.inventoryId || undefined,
      aisle_id: filters.aisleId || undefined,
    },
    observability: {
      from: fromIso,
      to: toIso,
      clientId: filters.clientId.trim() || undefined,
      clientSupplierId: filters.clientSupplierId.trim() || undefined,
      providerName: filters.providerName.trim() || undefined,
      modelName: filters.modelName.trim() || undefined,
    },
  };
}

export type CompareEligibility =
  | { allowed: true }
  | { allowed: false; reason: 'unknown_mode' | 'test_only' };

export function getCompareEligibility(processingMode: string | undefined): CompareEligibility {
  if (processingMode === 'test') return { allowed: true };
  if (processingMode === undefined) return { allowed: false, reason: 'unknown_mode' };
  return { allowed: false, reason: 'test_only' };
}

export function compareEligibilityTooltipKey(reason: 'unknown_mode' | 'test_only'): string {
  return reason === 'unknown_mode'
    ? 'analyticsDashboard.compare.unknownModeTooltip'
    : 'analyticsDashboard.compare.testOnlyTooltip';
}
