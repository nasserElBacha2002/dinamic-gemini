/**
 * Composite gallery cursor: (dateAdded, assetId).
 *
 * Timestamps alone are not unique; asset ids alone are not a total order across time.
 * Combining both gives a stable ordering key. assetId is compared lexicographically when
 * dates tie (documented, deterministic). Numeric MediaStore ids are NOT required.
 */
import type { CaptureMarker } from '../domain/entities/captureMarker';
import type { GalleryImage } from '../domain/entities/galleryImage';
import { parseMediaStoreNumericId } from '../domain/entities/galleryImage';

export interface CompositeCursor {
  readonly dateAdded: number;
  /** Stable library asset id (string). Empty string only for the sentinel empty-gallery cursor. */
  readonly assetId: string;
}

/**
 * Compare asset ids: numeric MediaStore ids use integer order; otherwise lexicographic.
 * Documented so same-second ties stay deterministic on Android.
 */
export function compareAssetId(a: string, b: string): number {
  const an = parseMediaStoreNumericId(a);
  const bn = parseMediaStoreNumericId(b);
  if (an !== undefined && bn !== undefined) {
    return an - bn;
  }
  if (a < b) {
    return -1;
  }
  if (a > b) {
    return 1;
  }
  return 0;
}

/** Total order over the composite cursor. Returns <0, 0, >0. */
export function compareCursor(a: CompositeCursor, b: CompositeCursor): number {
  if (a.dateAdded !== b.dateAdded) {
    return a.dateAdded - b.dateAdded;
  }
  return compareAssetId(a.assetId, b.assetId);
}

export function cursorOf(image: Pick<GalleryImage, 'dateAdded' | 'assetId'>): CompositeCursor {
  return { dateAdded: image.dateAdded, assetId: image.assetId };
}

/**
 * Empty-gallery / session-start sentinel. Every real MediaStore row is strictly after this.
 */
export const EMPTY_CURSOR: CompositeCursor = { dateAdded: -1, assetId: '' };

/**
 * Build the ordering cursor from a session marker.
 */
export function cursorFromMarker(marker: CaptureMarker): CompositeCursor {
  if (marker.assetId === null || marker.dateAdded === null) {
    return EMPTY_CURSOR;
  }
  return { dateAdded: marker.dateAdded, assetId: marker.assetId };
}

/**
 * True when `image` was added strictly after `cursor`.
 */
export function isAfterCursor(
  image: Pick<GalleryImage, 'dateAdded' | 'assetId'>,
  cursor: CompositeCursor,
): boolean {
  return compareCursor(cursorOf(image), cursor) > 0;
}

/** True when image is at or before cursor (used as stop condition when scanning newest-first). */
export function isAtOrBeforeCursor(
  image: Pick<GalleryImage, 'dateAdded' | 'assetId'>,
  cursor: CompositeCursor,
): boolean {
  return compareCursor(cursorOf(image), cursor) <= 0;
}

/** Pick the maximum cursor among a set (or the provided fallback when empty). */
export function maxCursor(
  items: readonly Pick<GalleryImage, 'dateAdded' | 'assetId'>[],
  fallback: CompositeCursor,
): CompositeCursor {
  let best = fallback;
  for (const img of items) {
    const c = cursorOf(img);
    if (compareCursor(c, best) > 0) {
      best = c;
    }
  }
  return best;
}
