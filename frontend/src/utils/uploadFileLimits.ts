import { UPLOAD_LIMITS } from '../features/uploads/bulkUpload.config';
import i18n from '../i18n';

export type UploadFileLimitContext = 'generic' | 'aisle' | 'import';

/** True when a **single HTTP request** would exceed the per-request file cap. */
export function isTooManyFilesForUpload(fileCount: number): boolean {
  return fileCount > UPLOAD_LIMITS.maxFilesPerRequest;
}

/**
 * Selection size is no longer capped by maxFilesPerRequest — bulk uploader auto-batches.
 * Kept for API clients that still send one non-batched request.
 */
export function tooManyFilesMessage(context: UploadFileLimitContext = 'generic'): string {
  if (context === 'aisle') {
    return i18n.t('aisles.uploads.errors.tooManyImages');
  }
  if (context === 'import') {
    return i18n.t('imports.uploads.errors.tooManyFiles');
  }
  return i18n.t('uploads.errors.tooManyFiles');
}

export function maxFilesPerUploadHelperText(): string {
  return i18n.t('uploads.helper.maxFilesPerUpload', {
    count: UPLOAD_LIMITS.maxFilesPerRequest,
  });
}
