/** Phase 5.1 — /api/v3/analytics responses. */

export interface AnalyticsSummaryResponse {
  auto_acceptance_rate: number | null;
  manual_correction_rate: number | null;
  invalid_traceability_rate: number | null;
  processing_success_rate: number | null;
  average_review_time_seconds: number | null;
  reviewed_results_per_day: number | null;
  notes: string[];
  period_day_count: number;
  settling_actions_count: number;
  positions_in_scope: number;
}

export interface AnalyticsTrendPoint {
  period: string;
  reviewed_results: number;
  correction_rate: number | null;
  processing_success_rate: number | null;
}

export interface AnalyticsTrendsResponse {
  reviewed_results_over_time: AnalyticsTrendPoint[];
  correction_rate_over_time: AnalyticsTrendPoint[];
  processing_success_over_time: AnalyticsTrendPoint[];
}

export interface InventoryPerformanceRow {
  inventory_id: string;
  inventory_name: string;
  inventory_created_at: string;
  total_aisles: number;
  total_positions: number;
  processed_positions: number;
  review_rate: number | null;
  correction_rate: number | null;
  invalid_traceability_rate: number | null;
  avg_confidence: number | null;
  processing_success_rate: number | null;
}

export interface InventoryPerformanceListResponse {
  items: InventoryPerformanceRow[];
}

export interface AisleIssueRow {
  aisle_id: string;
  aisle_code: string;
  inventory_id: string;
  inventory_name: string;
  total_results: number;
  needs_review_count: number;
  corrected_count: number;
  invalid_traceability_count: number;
  low_confidence_count: number;
  most_common_issue: string | null;
}

export interface AisleIssueListResponse {
  items: AisleIssueRow[];
}

export interface QualityPatternRow {
  issue_type: string;
  count: number;
  percentage: number | null;
  notes: string | null;
}

export interface QualityPatternListResponse {
  items: QualityPatternRow[];
}
