/** GET /api/v3/analytics/cost-summary — Phase 3 backend contract. */

export interface AnalyticsCostSummaryParams {
  date_from?: string;
  date_to?: string;
  inventory_id?: string;
  aisle_id?: string;
  client_id?: string;
  client_supplier_id?: string;
  provider_name?: string;
  model_name?: string;
}

export interface AnalyticsCostSummaryScope {
  date_from: string | null;
  date_to: string | null;
  inventory_id: string | null;
  aisle_id: string | null;
  client_id: string | null;
  client_supplier_id: string | null;
  provider_name: string | null;
  model_name: string | null;
}

export interface AnalyticsCostTotals {
  jobs_total: number;
  jobs_with_cost: number;
  jobs_without_cost: number;
  jobs_with_exact_cost: number;
  jobs_with_estimated_cost: number;
  jobs_with_partial_cost: number;
  jobs_with_unavailable_cost: number;
  jobs_with_missing_cost: number;
  total_cost: number | null;
  total_counted_quantity: number | null;
  cost_per_counted_unit: number | null;
  total_execution_time_seconds: number | null;
  average_execution_time_seconds: number | null;
}

export interface AnalyticsCostByProviderModel {
  provider_name: string | null;
  model_name: string | null;
  jobs_total: number;
  jobs_with_cost: number;
  total_cost: number | null;
  total_counted_quantity: number | null;
  cost_per_counted_unit: number | null;
  average_execution_time_seconds: number | null;
}

export interface AnalyticsCostByInventory {
  inventory_id: string;
  inventory_name: string | null;
  jobs_total: number;
  jobs_with_cost: number;
  total_cost: number | null;
  total_counted_quantity: number | null;
  cost_per_counted_unit: number | null;
  total_execution_time_seconds: number | null;
}

export interface AnalyticsCostByAisle {
  inventory_id: string;
  inventory_name: string | null;
  aisle_id: string;
  aisle_code: string | null;
  jobs_total: number;
  jobs_with_cost: number;
  total_cost: number | null;
  total_counted_quantity: number | null;
  cost_per_counted_unit: number | null;
  total_execution_time_seconds: number | null;
}

export interface AnalyticsCostByCaptureStatus {
  capture_status: string;
  jobs_total: number;
  total_cost: number | null;
}

export interface AnalyticsCostSummaryResponse {
  scope: AnalyticsCostSummaryScope;
  totals: AnalyticsCostTotals;
  by_provider_model: AnalyticsCostByProviderModel[];
  by_inventory: AnalyticsCostByInventory[];
  by_aisle: AnalyticsCostByAisle[];
  by_capture_status: AnalyticsCostByCaptureStatus[];
  warnings: string[];
}
