/**
 * Validate ZIP entry basenames — reject traversal / separators / control chars.
 */

import { ExportFromStagingError } from './exportFromStagingErrors';
import { exportPhotoFileName } from './exportPhotoFileName';

const MAX_EXPORT_FILE_NAME_LEN = 180;

/**
 * Throws ExportFromStagingError if name is unsafe or does not match deterministic rule.
 */
export function assertSafeExportFileName(
  fileName: string,
  photoId: string,
  sequence: number,
  displayName: string | null | undefined,
): void {
  if (!fileName || !fileName.trim()) {
    throw new ExportFromStagingError('PACKAGE_VALIDATION_FAILED', 'export_file_name vacío', {
      photoId,
    });
  }
  if (fileName.length > MAX_EXPORT_FILE_NAME_LEN) {
    throw new ExportFromStagingError(
      'PACKAGE_VALIDATION_FAILED',
      `export_file_name demasiado largo (${fileName.length})`,
      { photoId },
    );
  }
  if (fileName !== fileName.trim() || fileName.includes('\0')) {
    throw new ExportFromStagingError(
      'PACKAGE_VALIDATION_FAILED',
      'export_file_name con espacios/control inválidos',
      { photoId },
    );
  }
  for (let i = 0; i < fileName.length; i += 1) {
    const c = fileName.charCodeAt(i);
    if (c < 32 || c === 127) {
      throw new ExportFromStagingError(
        'PACKAGE_VALIDATION_FAILED',
        'export_file_name contiene caracteres de control',
        { photoId },
      );
    }
  }
  if (
    fileName.includes('/') ||
    fileName.includes('\\') ||
    fileName.includes('..') ||
    fileName.startsWith('.')
  ) {
    throw new ExportFromStagingError(
      'PACKAGE_VALIDATION_FAILED',
      `export_file_name inseguro: ${fileName}`,
      { photoId },
    );
  }
  // Must be a basename (no path segments) — already checked separators.
  const expected = exportPhotoFileName(photoId, sequence, displayName);
  if (fileName !== expected) {
    // Compatibility: allow exact expected only — do not silently normalize corrupt rows.
    throw new ExportFromStagingError(
      'PACKAGE_VALIDATION_FAILED',
      `export_file_name no coincide con regla determinista (got ${fileName}, expected ${expected})`,
      { photoId },
    );
  }
}
