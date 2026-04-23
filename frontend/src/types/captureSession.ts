/**
 * Capture Session API contract mirror for UI usage (R1).
 * This module intentionally lives in frontend/src/types as a feature-facing contract surface,
 * while remaining 1:1 with backend/src/api/schemas/capture_schemas.py.
 * Runtime tolerance/parsing should be handled in adapters, not in these contract types.
 */

export type CaptureSessionStatus =
  | 'draft'
  | 'importing'
  | 'ready_for_review'
  | 'assignment_proposed'
  | 'confirming'
  | 'confirmed'
  | 'cancelled'
  | 'failed';

export type CaptureSessionItemImportStatus =
  | 'pending_import'
  | 'importing'
  | 'imported'
  | 'import_failed';

export type CaptureSessionItemAssignmentStatus = 'pending' | 'proposed' | 'conflict' | 'unassigned';

export type CaptureTimeSource = 'exif' | 'file_mtime' | 'fallback_clock';

export interface CaptureSessionResponse {
  id: string;
  inventory_id: string;
  aisle_id: string | null;
  status: CaptureSessionStatus;
  created_at: string;
  updated_at: string;
  opened_at?: string | null;
  closed_at?: string | null;
  clock_offset_seconds: number;
}

export interface CaptureSessionItemResponse {
  id: string;
  session_id: string;
  staging_storage_key: string;
  import_status: CaptureSessionItemImportStatus;
  assignment_status: CaptureSessionItemAssignmentStatus;
  content_hash?: string | null;
  effective_capture_time?: string | null;
  time_source?: CaptureTimeSource | null;
  time_confidence?: number | null;
  adjusted_capture_time?: string | null;
  assignment_reason?: string | null;
  preview_target_position_id?: string | null;
  linked_source_asset_id?: string | null;
  last_error_code?: string | null;
  last_error_detail?: string | null;
  original_filename?: string | null;
  /** G3 temporal group; null until compute-groups runs or after clear. */
  group_id?: string | null;
  updated_at: string;
}

export interface CaptureSessionGroupSummaryResponse {
  group_id: string;
  group_index: number;
  item_count: number;
  start_time: string;
  end_time: string;
  /** G3 algorithm tag (e.g. `time_gap_v1`); mirrors persisted `capture_session_groups.algorithm_version`. */
  algorithm_version: string;
}

export interface CaptureSessionGroupsListResponse {
  groups: CaptureSessionGroupSummaryResponse[];
}

export interface CaptureSessionDetailResponse {
  session: CaptureSessionResponse;
  items: CaptureSessionItemResponse[];
}

export interface PaginatedCaptureSessionListResponse {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  items: CaptureSessionResponse[];
}

export interface CaptureSessionStagingUploadFileError {
  filename: string;
  code: string;
  detail: string;
  file_index: number;
}

export interface UploadCaptureSessionItemsResponse {
  items: CaptureSessionItemResponse[];
  errors: CaptureSessionStagingUploadFileError[];
}

export interface CaptureSessionClockOffsetUpdateRequest {
  clock_offset_seconds: number;
}

export interface CaptureSessionMaterializeRequest {
  idempotency_key: string;
}

export interface MaterializeCaptureSessionResponse extends CaptureSessionDetailResponse {
  created_assets_count: number;
}
