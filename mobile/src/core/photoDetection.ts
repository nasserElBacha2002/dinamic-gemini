/**
 * New-photo classification against a scan cursor (Fase 0 correction).
 *
 * Separates two cursor responsibilities:
 * - `nextScanCursor`: advances past EVERY newly inspected MediaStore row (admitted OR rejected)
 *   so the same reject is not re-classified on every scan.
 * - `lastValidPhotoCursor` is NOT updated here — only after stability succeeds in the app layer.
 *
 * Defensive video rejection still lives here for unit tests that inject video MIME candidates.
 * In production, MediaStore.Images queries should never surface videos.
 */
import type { GalleryImage } from '../domain/entities/galleryImage';
import { admitImage, type ImageRejectionReason } from './imageFilter';
import {
  compareCursor,
  type CompositeCursor,
  cursorOf,
  isAfterCursor,
  maxCursor,
} from './compositeCursor';

export interface RejectedPhoto {
  readonly assetId: string;
  readonly reason: ImageRejectionReason;
}

export interface DetectionResult {
  /** Admissible new photos pending stability, sorted ascending by cursor. */
  readonly admitted: readonly GalleryImage[];
  /** Rejected candidates (defensive video MIME, disallowed format, etc.). */
  readonly rejected: readonly RejectedPhoto[];
  /**
   * Scan cursor advanced past every newly inspected row (admitted + rejected).
   * Does not equal last-valid-photo cursor.
   */
  readonly nextScanCursor: CompositeCursor;
  /** Asset ids to add to the session inspected set (admitted + rejected). */
  readonly inspectedIds: readonly string[];
}

export interface DetectionInput {
  readonly candidates: readonly GalleryImage[];
  /** Last MediaStore row already inspected (scan cursor). */
  readonly scanCursor: CompositeCursor;
  /** Asset ids already inspected this session. */
  readonly inspectedIds: ReadonlySet<string>;
}

export function detectNewPhotos(input: DetectionInput): DetectionResult {
  const { candidates, scanCursor, inspectedIds } = input;

  const admitted: GalleryImage[] = [];
  const rejected: RejectedPhoto[] = [];
  const newlyInspected: Pick<GalleryImage, 'dateAdded' | 'assetId'>[] = [];
  const inspectedAdditions: string[] = [];

  for (const img of candidates) {
    if (inspectedIds.has(img.assetId)) {
      continue;
    }
    if (!isAfterCursor(img, scanCursor)) {
      continue;
    }

    newlyInspected.push(img);
    inspectedAdditions.push(img.assetId);

    const admission = admitImage(img);
    if (!admission.admitted) {
      rejected.push({ assetId: img.assetId, reason: admission.reason });
      continue;
    }
    admitted.push(img);
  }

  admitted.sort((a, b) => compareCursor(cursorOf(a), cursorOf(b)));

  // Rejects AND admits advance the scan cursor so we never re-walk the same rows.
  const nextScanCursor = maxCursor(newlyInspected, scanCursor);

  return {
    admitted,
    rejected,
    nextScanCursor,
    inspectedIds: inspectedAdditions,
  };
}
