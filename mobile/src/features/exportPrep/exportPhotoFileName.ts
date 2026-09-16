/**
 * Deterministic ZIP photo basename — shared by staging prep and local CSV export.
 * Format: `{sequence:04d}_{safeCapturePhotoId}{ext}`
 */
export function exportPhotoFileName(
  photoId: string,
  sequence: number,
  displayName: string | null | undefined,
): string {
  const safeId = photoId.replace(/[^a-zA-Z0-9_-]/g, '_');
  const ext = (displayName && /\.[a-z0-9]+$/i.exec(displayName)?.[0]) || '.jpg';
  return `${String(sequence).padStart(4, '0')}_${safeId}${ext}`;
}
