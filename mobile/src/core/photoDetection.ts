/**
 * New-photo detection (Fase 0, §12).
 *
 * Given a batch of MediaStore.Images rows, the session cursor and the set of already-seen
 * MediaStore ids, return only the admissible NEW photos plus the advanced cursor.
 *
 * A photo is "new" when it is after the cursor (composite comparison) AND its MediaStore id
 * has not been seen in this session. The seen-set makes repeated scans idempotent even if
 * the cursor has not advanced yet (e.g. same-second writes processed across two polls).
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
  readonly mediaStoreId: number;
  readonly reason: ImageRejectionReason;
}

export interface DetectionResult {
  /** Admissible new photos, sorted by (dateAdded, mediaStoreId) ascending. */
  readonly newPhotos: readonly GalleryImage[];
  /** Rejected candidates (e.g. a video that appeared in the album). */
  readonly rejected: readonly RejectedPhoto[];
  /** Cursor advanced past every ADMITTED new photo (rejects never move it). */
  readonly nextCursor: CompositeCursor;
  /** MediaStore ids to add to the session seen-set (admitted photos only). */
  readonly seenAdditions: readonly number[];
}

export interface DetectionInput {
  readonly candidates: readonly GalleryImage[];
  readonly cursor: CompositeCursor;
  readonly seenIds: ReadonlySet<number>;
}

export function detectNewPhotos(input: DetectionInput): DetectionResult {
  const { candidates, cursor, seenIds } = input;

  const newPhotos: GalleryImage[] = [];
  const rejected: RejectedPhoto[] = [];
  const seenAdditions: number[] = [];

  for (const img of candidates) {
    const isNew = isAfterCursor(img, cursor) && !seenIds.has(img.mediaStoreId);
    if (!isNew) {
      continue;
    }
    const admission = admitImage(img);
    if (!admission.admitted) {
      // Rejected candidates (e.g. a new .mp4) never enter the queue and never move the cursor.
      rejected.push({ mediaStoreId: img.mediaStoreId, reason: admission.reason });
      continue;
    }
    newPhotos.push(img);
    seenAdditions.push(img.mediaStoreId);
  }

  newPhotos.sort((a, b) => compareCursor(cursorOf(a), cursorOf(b)));

  // Only admitted photos advance the cursor. This guarantees a rejected video cannot
  // move the "last valid photo" marker forward.
  const nextCursor = maxCursor(newPhotos, cursor);

  return { newPhotos, rejected, nextCursor, seenAdditions };
}
