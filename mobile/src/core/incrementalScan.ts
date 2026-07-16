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
