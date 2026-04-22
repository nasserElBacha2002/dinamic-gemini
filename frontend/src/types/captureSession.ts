/**
 * Capture Session contracts for UI (R1).
 * Must stay aligned with backend/src/api/schemas/capture_schemas.py.
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
  aisle_id: string;
  status: CaptureSessionStatus | string;
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
  import_status: CaptureSessionItemImportStatus | string;
  assignment_status: CaptureSessionItemAssignmentStatus | string;
  content_hash?: string | null;
  effective_capture_time?: string | null;
  time_source?: CaptureTimeSource | string | null;
  time_confidence?: number | null;
  adjusted_capture_time?: string | null;
  assignment_reason?: string | null;
  preview_target_position_id?: string | null;
  linked_source_asset_id?: string | null;
  last_error_code?: string | null;
  last_error_detail?: string | null;
  original_filename?: string | null;
  updated_at: string;
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

export interface UploadCaptureSessionItemsResponse {
  items: CaptureSessionItemResponse[];
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
