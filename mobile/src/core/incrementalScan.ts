/**
 * Incremental newest-first scan helpers (device-independent).
 *
 * Expo MediaLibrary with `sortBy: [[creationTime, false]]` returns newest first
 * (descending by creationTime). When scanning that order:
 * 1. Hydrate / classify only rows AFTER scanCursor.
 * 2. Stop as soon as a row is at-or-before scanCursor (remaining pages are older).
 */
import type { GalleryImage } from '../domain/entities/galleryImage';
import {
  type CompositeCursor,
  isAfterCursor,
  isAtOrBeforeCursor,
} from './compositeCursor';

export interface LightweightAsset {
  readonly assetId: string;
  readonly dateAdded: number;
}

export interface IncrementalPageResult<T> {
  readonly newCandidates: readonly T[];
  readonly reachedCursor: boolean;
  readonly examined: number;
}

/**
 * Filter a newest-first page: keep only items after cursor; stop flag when older region hit.
 */
export function filterNewestFirstPage<T extends LightweightAsset>(
  page: readonly T[],
  scanCursor: CompositeCursor,
): IncrementalPageResult<T> {
  const newCandidates: T[] = [];
  let reachedCursor = false;
  let examined = 0;

  for (const item of page) {
    examined += 1;
    if (isAtOrBeforeCursor(item, scanCursor)) {
      reachedCursor = true;
      break;
    }
    if (isAfterCursor(item, scanCursor)) {
      newCandidates.push(item);
    }
  }

  return { newCandidates, reachedCursor, examined };
}

const EMPTY_INSPECTED: ReadonlySet<string> = new Set<string>();

export interface FloorPageResult<T> {
  readonly newCandidates: readonly T[];
  /** True once a row strictly older (by second) than the floor was seen: stop paging. */
  readonly reachedFloor: boolean;
  readonly examined: number;
}

/**
 * Robust newest-first page walk anchored to a FIXED floor (session start marker).
 *
 * Unlike `filterNewestFirstPage`, it does NOT early-stop at same-second ties against an
 * advancing cursor. It keeps examining rows until a strictly-older `dateAdded` second is
 * reached. This is the key fix for batch downloads (e.g. pulling many drone photos at once):
 * those rows commonly share a DATE_ADDED second, and MediaStore may return the tied rows in
 * an order that does not match our composite (dateAdded, assetId) key. Stopping only on a
 * strictly-older second guarantees every same-second sibling is inspected.
 *
 * `inspectedIds` lets the caller skip rows already processed this session so hydration cost
 * stays bounded even though we re-walk the whole "since session start" window each scan.
 */
export function collectNewSinceFloor<T extends LightweightAsset>(
  page: readonly T[],
  floorCursor: CompositeCursor,
  inspectedIds: ReadonlySet<string> = EMPTY_INSPECTED,
): FloorPageResult<T> {
  const newCandidates: T[] = [];
  let reachedFloor = false;
  let examined = 0;

  for (const item of page) {
    examined += 1;
    // Only a strictly-older second proves the remaining pages are all historical.
    if (item.dateAdded < floorCursor.dateAdded) {
      reachedFloor = true;
      break;
    }
    if (inspectedIds.has(item.assetId)) {
      continue;
    }
    if (isAfterCursor(item, floorCursor)) {
      newCandidates.push(item);
    }
  }

  return { newCandidates, reachedFloor, examined };
}

export interface ScanMetrics {
  readonly assetsRead: number;
  readonly pagesQueried: number;
  readonly assetsHydrated: number;
  readonly newCandidates: number;
  readonly durationMs: number;
}

export function emptyScanMetrics(durationMs = 0): ScanMetrics {
  return {
    assetsRead: 0,
    pagesQueried: 0,
    assetsHydrated: 0,
    newCandidates: 0,
    durationMs,
  };
}

/** Simulate a large gallery scan cost for benchmarks (pure). */
export function simulateIncrementalScanCost(params: {
  readonly pageSize: number;
  readonly scanCursor: CompositeCursor;
  readonly newestFirstIds: readonly LightweightAsset[];
}): { hydrated: number; pages: number; examined: number } {
  const { pageSize, scanCursor, newestFirstIds } = params;
  let hydrated = 0;
  let pages = 0;
  let examined = 0;
  let offset = 0;

  while (offset < newestFirstIds.length) {
    pages += 1;
    const page = newestFirstIds.slice(offset, offset + pageSize);
    offset += page.length;
    const result = filterNewestFirstPage(page, scanCursor);
    examined += result.examined;
    hydrated += result.newCandidates.length;
    if (result.reachedCursor || page.length < pageSize) {
      break;
    }
  }

  return { hydrated, pages, examined };
}

export function asLightweight(image: GalleryImage): LightweightAsset {
  return { assetId: image.assetId, dateAdded: image.dateAdded };
}
