import i18n from '../i18n';
import { MAX_FILES_PER_UPLOAD } from '../constants/uploads';

export type UploadFileLimitContext = 'generic' | 'aisle' | 'import';

export function isTooManyFilesForUpload(fileCount: number): boolean {
  return fileCount > MAX_FILES_PER_UPLOAD;
}

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
  return i18n.t('uploads.helper.maxFilesPerUpload');
}
