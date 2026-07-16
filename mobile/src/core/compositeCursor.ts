/**
 * Composite gallery cursor: (dateAdded, mediaStoreId).
 *
 * Timestamps alone are not unique (a drone can write several photos within the same
 * second) and are subject to clock/timezone changes; MediaStore `_ID` is monotonic within
 * a device but can be reused after DB resets. Combining both gives a stable ordering key
 * for "everything after the session marker".
 */
import type { CaptureMarker } from '../domain/entities/captureMarker';
import type { GalleryImage } from '../domain/entities/galleryImage';

export interface CompositeCursor {
  readonly dateAdded: number;
  readonly mediaStoreId: number;
}

/** Total order over the composite cursor. Returns <0, 0, >0. */
export function compareCursor(a: CompositeCursor, b: CompositeCursor): number {
  if (a.dateAdded !== b.dateAdded) {
    return a.dateAdded - b.dateAdded;
  }
  return a.mediaStoreId - b.mediaStoreId;
}

export function cursorOf(image: GalleryImage): CompositeCursor {
  return { dateAdded: image.dateAdded, mediaStoreId: image.mediaStoreId };
}

/**
 * Build the ordering cursor from a session marker. An empty gallery at session start
 * yields the lowest possible cursor so that every later photo is considered "after".
 */
export function cursorFromMarker(marker: CaptureMarker): CompositeCursor {
  if (marker.mediaStoreId === null || marker.dateAdded === null) {
    return { dateAdded: -1, mediaStoreId: -1 };
  }
  return { dateAdded: marker.dateAdded, mediaStoreId: marker.mediaStoreId };
}

/**
 * True when `image` was added strictly after `cursor`:
 *   dateAdded > cursor.dateAdded
 *   OR (dateAdded == cursor.dateAdded AND mediaStoreId > cursor.mediaStoreId)
 */
export function isAfterCursor(image: GalleryImage, cursor: CompositeCursor): boolean {
  return compareCursor(cursorOf(image), cursor) > 0;
}

/** Pick the maximum cursor among a set of images (or the provided fallback when empty). */
export function maxCursor(
  images: readonly GalleryImage[],
  fallback: CompositeCursor,
): CompositeCursor {
  let best = fallback;
  for (const img of images) {
    const c = cursorOf(img);
    if (compareCursor(c, best) > 0) {
      best = c;
    }
  }
  return best;
}
