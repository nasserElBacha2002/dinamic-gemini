import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryScope } from '../../src/api/types/analyticsCost';
import type { ObservabilityMetricsFiltersState } from '../../src/api/types/responses';

export const EMPTY_ANALYTICS_COST_SCOPE: AnalyticsCostSummaryScope = {
  date_from: null,
  date_to: null,
  inventory_id: null,
  aisle_id: null,
  client_id: null,
  client_supplier_id: null,
  provider_name: null,
  model_name: null,
};

export const EMPTY_OBSERVABILITY_FILTERS: ObservabilityMetricsFiltersState = {
  client_id: null,
  client_supplier_id: null,
  provider_name: null,
  model_name: null,
};

/** Minimal i18n stub for view-model / formatter unit tests. */
export function mockT(): TFunction {
  return ((key: string) => key) as unknown as TFunction;
}
