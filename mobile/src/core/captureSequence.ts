/**
 * Client-assigned capture sequence helpers.
 *
 * Primary assignment happens when photos are first persisted into the capture
 * session (selection complete / direct capture). Upload-time assignment is
 * defensive recovery for legacy NULL rows only.
 *
 * Gallery order contract: date_added ASC, asset_id ASC (via compareCursor).
 * Existing sequence_number values are never recalculated.
 */
import { compareCursor, cursorOf } from './compositeCursor';

export function sortByGalleryOrder<T extends { readonly dateAdded: number; readonly assetId: string }>(
  items: readonly T[],
): T[] {
  return [...items].sort((a, b) => compareCursor(cursorOf(a), cursorOf(b)));
}

/**
 * Assign monotonic sequence_number values for photos that lack one.
 * Input must already be sorted by gallery order (date_added, asset_id).
 * Existing sequence_number values are never recalculated.
 */
export function nextSequenceAssignments(
  photos: readonly { readonly id: string; readonly sequence_number: number | null }[],
): readonly { readonly id: string; readonly sequenceNumber: number }[] {
  let next = 0;
  for (const photo of photos) {
    if (photo.sequence_number != null && photo.sequence_number > next) {
      next = photo.sequence_number;
    }
  }
  const assignments: { id: string; sequenceNumber: number }[] = [];
  for (const photo of photos) {
    if (photo.sequence_number != null) {
      continue;
    }
    next += 1;
    assignments.push({ id: photo.id, sequenceNumber: next });
  }
  return assignments;
}

/**
 * Allocate the next N sequence numbers after `currentMax` (transactional reserve helper).
 */
export function reserveSequenceRange(currentMax: number, count: number): readonly number[] {
  if (count <= 0) {
    return [];
  }
  const start = Math.max(0, currentMax);
  return Array.from({ length: count }, (_, i) => start + i + 1);
}
