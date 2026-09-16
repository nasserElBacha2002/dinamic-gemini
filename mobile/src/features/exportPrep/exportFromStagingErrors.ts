/**
 * Typed failures for ZIP export from staging (Phase 4).
 * Message prefix remains PACKAGE_* for existing UI mappers.
 */

export type ExportFromStagingFailure =
  | 'SESSION_MISSING'
  | 'FREEZE_MISSING'
  | 'FREEZE_CHANGED'
  | 'PREP_JOB_MISSING'
  | 'PREP_NOT_READY'
  | 'STAGING_FILE_MISSING'
  | 'STAGING_SIZE_MISMATCH'
  | 'STAGING_HASH_MISMATCH'
  | 'DUPLICATE_EXPORT_FILE_NAME'
  | 'PHOTO_SET_MISMATCH'
  | 'ORIGINAL_FALLBACK_NOT_ALLOWED'
  | 'PACKAGE_VALIDATION_FAILED'
  | 'PREP_TERMINAL'
  | 'PREP_FAILED_RETRYABLE'
  | 'EXPORT_TOO_LARGE'
  | 'STORAGE_INSUFFICIENT_FOR_EXPORT'
  | 'STORAGE_STATUS_UNKNOWN';

const CODE_TO_PREFIX: Record<ExportFromStagingFailure, string> = {
  SESSION_MISSING: 'PACKAGE_EXPORT_SESSION_MISSING',
  FREEZE_MISSING: 'PACKAGE_EXPORT_FREEZE_MISSING',
  FREEZE_CHANGED: 'PACKAGE_EXPORT_FREEZE_CHANGED',
  PREP_JOB_MISSING: 'PACKAGE_EXPORT_PREP_INCOMPLETE',
  PREP_NOT_READY: 'PACKAGE_EXPORT_PREP_PENDING',
  STAGING_FILE_MISSING: 'PACKAGE_STAGING_MISSING',
  STAGING_SIZE_MISMATCH: 'PACKAGE_STAGING_CHECKSUM',
  STAGING_HASH_MISMATCH: 'PACKAGE_STAGING_CHECKSUM',
  DUPLICATE_EXPORT_FILE_NAME: 'PACKAGE_EXPORT_DUPLICATE_FILE_NAME',
  PHOTO_SET_MISMATCH: 'PACKAGE_EXPORT_PHOTO_SET_MISMATCH',
  ORIGINAL_FALLBACK_NOT_ALLOWED: 'PACKAGE_EXPORT_FALLBACK_FORBIDDEN',
  PACKAGE_VALIDATION_FAILED: 'PACKAGE_VALIDATION_FAILED',
  PREP_TERMINAL: 'PACKAGE_EXPORT_PREP_TERMINAL',
  PREP_FAILED_RETRYABLE: 'PACKAGE_EXPORT_PREP_FAILED',
  EXPORT_TOO_LARGE: 'PACKAGE_EXPORT_TOO_LARGE',
  STORAGE_INSUFFICIENT_FOR_EXPORT: 'PACKAGE_STORAGE_INSUFFICIENT',
  STORAGE_STATUS_UNKNOWN: 'PACKAGE_STORAGE_UNKNOWN',
};

export class ExportFromStagingError extends Error {
  readonly code: ExportFromStagingFailure;
  readonly photoId: string | null;

  constructor(
    code: ExportFromStagingFailure,
    detail: string,
    options?: { readonly photoId?: string | null },
  ) {
    const prefix = CODE_TO_PREFIX[code];
    super(`${prefix}: ${detail}`);
    this.name = 'ExportFromStagingError';
    this.code = code;
    this.photoId = options?.photoId ?? null;
  }
}

export function isExportFromStagingError(error: unknown): error is ExportFromStagingError {
  return error instanceof ExportFromStagingError;
}
