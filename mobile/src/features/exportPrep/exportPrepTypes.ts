/** Durable export-preparation job states (independent of upload_status). */

export const EXPORT_PREP_STATUSES = [
  'QUEUED',
  'PREPARING',
  'SCANNING',
  'VALIDATING',
  'READY',
  'FAILED_RETRYABLE',
  'FAILED_TERMINAL',
  'EXCLUDED',
] as const;

export type ExportPrepStatus = (typeof EXPORT_PREP_STATUSES)[number];

export const EXPORT_PREP_TRANSIENT: ReadonlySet<ExportPrepStatus> = new Set([
  'QUEUED',
  'PREPARING',
  'SCANNING',
  'VALIDATING',
]);

export const EXPORT_PREP_PROCESSING: ReadonlySet<ExportPrepStatus> = new Set([
  'PREPARING',
  'SCANNING',
  'VALIDATING',
]);

export const EXPORT_PREP_FAILED: ReadonlySet<ExportPrepStatus> = new Set([
  'FAILED_RETRYABLE',
  'FAILED_TERMINAL',
]);

export interface ExportPrepJobRow {
  readonly capture_photo_id: string;
  readonly capture_session_id: string;
  readonly status: ExportPrepStatus;
  readonly source_uri: string;
  readonly staging_uri: string | null;
  readonly export_file_name: string | null;
  readonly size_bytes: number | null;
  readonly sha256: string | null;
  readonly source_fingerprint: string | null;
  readonly error_code: string | null;
  readonly error_message: string | null;
  readonly attempt_count: number;
  readonly max_attempts: number;
  readonly lease_token: string | null;
  readonly lease_expires_at: string | null;
  readonly queued_at: string;
  readonly started_at: string | null;
  readonly ready_at: string | null;
  readonly updated_at: string;
  readonly created_at: string;
}

export interface ExportPrepCounts {
  readonly queued: number;
  readonly preparing: number;
  readonly scanning: number;
  readonly validating: number;
  readonly ready: number;
  readonly failedRetryable: number;
  readonly failedTerminal: number;
  readonly excluded: number;
  /** QUEUED + PREPARING + SCANNING + VALIDATING */
  readonly pending: number;
  /** PREPARING + SCANNING + VALIDATING */
  readonly processing: number;
  readonly failed: number;
  readonly total: number;
}

export type ExportPrepEnsureReason =
  | 'PHOTO_STABLE'
  | 'FINISH'
  | 'REVIEW_OPEN'
  | 'EXPORT_PREFLIGHT'
  | 'RECOVERY';

export interface EnsureExportPrepJobsResult {
  readonly sessionId: string;
  readonly reason: ExportPrepEnsureReason;
  readonly eligiblePhotos: number;
  readonly existingJobs: number;
  readonly createdJobs: number;
  readonly requeuedJobs: number;
  readonly invalidatedReadyJobs: number;
  readonly excludedJobs: number;
  readonly missingSourcePhotos: number;
  readonly partialErrors: readonly string[];
  readonly durationMs: number;
  /**
   * READY completeness check mode used during ensure.
   * Phase 3B: EXPORT_PREFLIGHT uses `light` (existence/size/format); packaging
   * always performs `strong` native rehash once. Other ensure reasons keep light.
   */
  readonly readyValidationMode?: 'light' | 'strong';
  /** How many READY jobs were completeness-checked (ok or invalidate). */
  readonly readyValidatedCount?: number;
  /** True when caller supplied session+photos (skipped listCanonicalExportPhotos). */
  readonly reusedCanonicalPhotos?: boolean;
  /** True when jobs were loaded via a single listForSession instead of N getByPhotoId. */
  readonly batchedJobLookup?: boolean;
  /**
   * Session jobs snapshot from ensure (only when no create/requeue/invalidate
   * and no in-flight workers for the session). Export may reuse this to skip
   * a second listForSession when the fence token still matches.
   */
  readonly jobsSnapshot?: readonly ExportPrepJobRow[];
  /** FNV identity token over jobsSnapshot rows (required when snapshot is set). */
  readonly jobsSnapshotToken?: string;
  /** Session id the snapshot belongs to (fence against cross-session reuse). */
  readonly jobsSnapshotSessionId?: string;
  /** In-flight workers for this session when the snapshot was taken (must be 0). */
  readonly activeWorkersAtSnapshot?: number;
  /**
   * Session jobs mutation revision at attach time. Consume must see the same
   * revision (ExportPrepQueue.getSessionJobsRevision) or fall back to live list.
   */
  readonly jobsSnapshotRevision?: number;
}

export function emptyEnsureExportPrepJobsResult(
  sessionId: string,
  reason: ExportPrepEnsureReason,
): EnsureExportPrepJobsResult {
  return {
    sessionId,
    reason,
    eligiblePhotos: 0,
    existingJobs: 0,
    createdJobs: 0,
    requeuedJobs: 0,
    invalidatedReadyJobs: 0,
    excludedJobs: 0,
    missingSourcePhotos: 0,
    partialErrors: [],
    durationMs: 0,
    readyValidationMode: 'light',
    readyValidatedCount: 0,
    reusedCanonicalPhotos: false,
    batchedJobLookup: false,
  };
}

export function emptyExportPrepCounts(): ExportPrepCounts {
  return {
    queued: 0,
    preparing: 0,
    scanning: 0,
    validating: 0,
    ready: 0,
    failedRetryable: 0,
    failedTerminal: 0,
    excluded: 0,
    pending: 0,
    processing: 0,
    failed: 0,
    total: 0,
  };
}
