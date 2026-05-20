/** v3 aisle code scan API types — aligned with backend code_scan_schemas. */

export type CodeScanRunStatus =
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed';

export type CodeScanCodeType = 'qr' | 'barcode' | 'datamatrix' | 'unknown';

export type CodeScanDetectionStatus =
  | 'detected'
  | 'duplicate'
  | 'low_confidence'
  | 'error';

export type CodeScanMatchStatus =
  | 'not_evaluated'
  | 'matched'
  | 'no_match'
  | 'multiple_candidates'
  | 'conflict'
  | 'mixed';

export interface CodeScanBoundingBoxRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CodeScanBoundingBox {
  format: 'rect' | 'rect_polygon';
  unit: 'pixel' | 'normalized';
  x?: number | null;
  y?: number | null;
  width?: number | null;
  height?: number | null;
  rect?: CodeScanBoundingBoxRect | null;
  polygon?: number[][] | null;
}

export interface CodeScanRunSummary {
  id: string;
  status: CodeScanRunStatus | string;
  total_assets: number;
  processed_assets: number;
  failed_assets: number;
  total_codes_found: number;
  total_qr_found: number;
  total_barcodes_found: number;
  started_at: string;
  finished_at: string | null;
  scanner_engine: string;
  error_message: string | null;
  warnings: string[];
  metadata_json?: Record<string, unknown> | null;
}

export interface CodeScanDetection {
  id: string;
  run_id: string;
  asset_id: string;
  code_type: CodeScanCodeType | string;
  code_value: string;
  normalized_code_value: string;
  detection_status: CodeScanDetectionStatus | string;
  confidence: number | null;
  bounding_box_json: CodeScanBoundingBox | null;
  scanner_engine: string;
  created_at: string;
  metadata_json: Record<string, unknown> | null;
  matched_position_id: string | null;
  match_status: CodeScanMatchStatus | string | null;
  match_type: string | null;
  match_confidence: number | null;
  match_metadata_json: Record<string, unknown> | null;
  matched_at: string | null;
}

export interface CodeScanSummaryItem {
  code_value: string;
  normalized_code_value: string;
  code_type: CodeScanCodeType | string;
  occurrences: number;
  asset_ids: string[];
  first_seen_at: string;
  match_status?: CodeScanMatchStatus | string | null;
  matched_position_ids?: string[];
  match_types?: string[];
  match_status_counts?: Record<string, number> | null;
}

export interface RunAisleCodeScanResponse {
  run: CodeScanRunSummary;
}

export interface ListAisleCodeScansResponse {
  latest_run: CodeScanRunSummary | null;
  detections: CodeScanDetection[];
}

export interface SummarizeAisleCodeScansResponse {
  latest_run: CodeScanRunSummary | null;
  items: CodeScanSummaryItem[];
}

export interface PositionCodeScanEvidenceSummary {
  total_detections: number;
  source_assets_count: number;
  code_types: Record<string, number>;
}

export interface PositionCodeScanEvidenceResponse {
  latest_run: CodeScanRunSummary | null;
  summary: PositionCodeScanEvidenceSummary;
  detections: CodeScanDetection[];
}

export type CodeScanSignalSeverity = 'info' | 'warning' | 'attention';

export type CodeScanSignalType =
  | 'code_match_found'
  | 'code_no_match'
  | 'code_multiple_candidates'
  | 'code_conflict'
  | 'code_detected_without_result'
  | 'result_has_code_evidence'
  | 'result_without_code_evidence'
  | 'many_unmatched_codes_in_aisle'
  | 'many_multiple_candidate_codes_in_aisle'
  | 'matching_not_evaluated';

export interface CodeScanReviewSignalsSummary {
  total_signals: number;
  info: number;
  warning: number;
  attention: number;
  unmatched_codes: number;
  multiple_candidates: number;
  matched_codes: number;
}

export interface CodeScanReviewSignal {
  id: string;
  type: CodeScanSignalType | string;
  severity: CodeScanSignalSeverity | string;
  message: string;
  detection_id: string | null;
  position_id: string | null;
  asset_id: string | null;
  code_value: string | null;
  code_type: string | null;
}

export interface AisleCodeScanReviewSignalsResponse {
  latest_run: CodeScanRunSummary | null;
  summary: CodeScanReviewSignalsSummary;
  signals: CodeScanReviewSignal[];
}

export type CodeScanExportType = 'detections' | 'unmatched' | 'summary';
