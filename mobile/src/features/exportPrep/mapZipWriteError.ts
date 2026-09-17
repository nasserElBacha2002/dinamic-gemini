/**
 * Map ZipWriteError → ExportFromStagingError (Phase 5).
 */

import { ZipWriteError, type ZipWriteFailure } from './zipWriteError';
import { ExportFromStagingError, type ExportFromStagingFailure } from './exportFromStagingErrors';

const ZIP_TO_EXPORT: Record<ZipWriteFailure, ExportFromStagingFailure> = {
  ZIP_ENTRY_TOO_LARGE: 'EXPORT_TOO_LARGE',
  ZIP_TOTAL_TOO_LARGE: 'EXPORT_TOO_LARGE',
  ZIP_TOO_MANY_ENTRIES: 'EXPORT_TOO_LARGE',
  ZIP_OFFSET_OVERFLOW: 'EXPORT_TOO_LARGE',
  ZIP_UNSUPPORTED_ZIP64: 'PACKAGE_VALIDATION_FAILED',
  ZIP_SOURCE_CHANGED: 'STAGING_HASH_MISMATCH',
  ZIP_SOURCE_READ_FAILED: 'PACKAGE_VALIDATION_FAILED',
  ZIP_WRITE_FAILED: 'PACKAGE_VALIDATION_FAILED',
  ZIP_CANCELLED: 'PACKAGE_VALIDATION_FAILED',
  ZIP_VALIDATION_FAILED: 'PACKAGE_VALIDATION_FAILED',
};

export function mapZipWriteError(error: ZipWriteError): ExportFromStagingError {
  const code = ZIP_TO_EXPORT[error.code] ?? 'PACKAGE_VALIDATION_FAILED';
  return new ExportFromStagingError(code, error.message);
}

export function isZipWriteError(error: unknown): error is ZipWriteError {
  return error instanceof ZipWriteError;
}

/** Preserve ExportFromStagingError; map ZipWriteError; rethrow others. */
export function rethrowExportOrZip(error: unknown): never {
  if (error instanceof ExportFromStagingError) {
    throw error;
  }
  if (error instanceof ZipWriteError) {
    throw mapZipWriteError(error);
  }
  // getBytes may throw ExportFromStagingError wrapped only by message name.
  if (
    error instanceof Error &&
    error.name === 'ExportFromStagingError' &&
    'code' in error
  ) {
    throw error;
  }
  throw error;
}
