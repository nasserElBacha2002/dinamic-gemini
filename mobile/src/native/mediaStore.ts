/**
 * MediaStore.Images adapter (Android) built on expo-media-library.
 *
 * PHOTOS-ONLY: every query passes `mediaType: photo`. We never request `video` or `all`.
 *
 * Incremental strategy (newest-first):
 * - Expo `sortBy: [[creationTime, false]]` → descending creationTime (newest first).
 * - Pages are walked until we hit rows at-or-before `scanCursor`.
 * - Full hydration (getAssetInfoAsync + filesystem size) runs ONLY for new candidates.
 */
import * as FileSystem from 'expo-file-system';
import * as MediaLibrary from 'expo-media-library';

import { collectNewSinceFloor, type ScanMetrics } from '../core/incrementalScan';
import type { CompositeCursor } from '../core/compositeCursor';
import type { GalleryImage } from '../domain/entities/galleryImage';
import { parseMediaStoreNumericId, requireAssetId } from '../domain/entities/galleryImage';
import { extensionOf } from '../shared/constants/imageFormats';

export interface PermissionState {
  readonly granted: boolean;
  readonly limited: boolean;
  readonly canAskAgain: boolean;
}

const _EXT_TO_MIME: Record<string, string> = {
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.heic': 'image/heic',
  '.heif': 'image/heif',
};

export async function requestPhotoPermission(): Promise<PermissionState> {
  const res = await MediaLibrary.requestPermissionsAsync(false, ['photo']);
  return {
    granted: res.granted,
    limited: res.accessPrivileges === 'limited',
    canAskAgain: res.canAskAgain,
  };
}

export async function getPhotoPermission(): Promise<PermissionState> {
  const res = await MediaLibrary.getPermissionsAsync(false, ['photo']);
  return {
    granted: res.granted,
    limited: res.accessPrivileges === 'limited',
    canAskAgain: res.canAskAgain,
  };
}

function inferMime(filename: string): string {
  return _EXT_TO_MIME[extensionOf(filename)] ?? '';
}

function toLightweight(asset: MediaLibrary.Asset): { assetId: string; dateAdded: number; raw: MediaLibrary.Asset } {
  const assetId = requireAssetId(asset.id);
  return {
    assetId,
    dateAdded: Math.floor((asset.creationTime ?? 0) / 1000),
    raw: asset,
  };
}

async function resolveLocalUri(asset: MediaLibrary.Asset): Promise<string> {
  try {
    const info = await MediaLibrary.getAssetInfoAsync(asset);
    return info.localUri ?? asset.uri;
  } catch (error) {
    // expo-media-library probes EXIF GPS via MediaStore.setRequireOriginal on API 29+.
    // Without ACCESS_MEDIA_LOCATION that throws — we intentionally omit that permission
    // (photos-only capture; GPS is unused). Fall back to the gallery URI.
    const message = error instanceof Error ? error.message : String(error);
    if (/ACCESS_MEDIA_LOCATION/i.test(message)) {
      return asset.uri;
    }
    throw error;
  }
}

async function hydrateAsset(asset: MediaLibrary.Asset): Promise<GalleryImage> {
  const assetId = requireAssetId(asset.id);
  const numeric = parseMediaStoreNumericId(assetId);
  const localUri = await resolveLocalUri(asset);

  let size = 0;
  try {
    const stat = await FileSystem.getInfoAsync(localUri, { size: true });
    if (stat.exists && typeof stat.size === 'number') {
      size = stat.size;
    }
  } catch {
    size = 0;
  }

  return {
    assetId,
    ...(numeric !== undefined ? { mediaStoreNumericId: numeric } : {}),
    uri: localUri,
    displayName: asset.filename,
    mimeType: inferMime(asset.filename),
    size,
    width: asset.width ?? 0,
    height: asset.height ?? 0,
    dateAdded: Math.floor((asset.creationTime ?? 0) / 1000),
    dateModified: Math.floor((asset.modificationTime ?? 0) / 1000),
    bucketId: null,
    relativePath: asset.albumId ?? null,
  };
}

export interface IncrementalScanOptions {
  readonly scanCursor: CompositeCursor;
  /**
   * Fixed session lower bound (start marker). When provided, paging is anchored here instead
   * of the advancing scan cursor so batch/same-second downloads are never skipped.
   * Falls back to `scanCursor` for backward compatibility.
   */
  readonly floorCursor?: CompositeCursor;
  /** Asset ids already processed this session; skipped to avoid re-hydration. */
  readonly inspectedAssetIds?: ReadonlySet<string>;
  readonly pageSize?: number;
  readonly now?: () => number;
}

export interface IncrementalScanResult {
  readonly images: GalleryImage[];
  readonly metrics: ScanMetrics;
}

/**
 * Fetch photos added since the session floor, hydrating metadata solely for new candidates.
 *
 * Paging is anchored to `floorCursor` (the fixed session-start marker) rather than the
 * advancing scan cursor, and stops only once a strictly-older second is reached. This makes
 * batch downloads robust: when many photos land in the same DATE_ADDED second (all drone
 * photos pulled at once), none are skipped by an early tie-based stop. `inspectedAssetIds`
 * prevents re-hydrating rows already processed this session.
 */
export async function queryNewPhotosSince(
  options: IncrementalScanOptions,
): Promise<IncrementalScanResult> {
  const pageSize = options.pageSize ?? 50;
  const floorCursor = options.floorCursor ?? options.scanCursor;
  const inspected = options.inspectedAssetIds ?? new Set<string>();
  const started = (options.now ?? Date.now)();
  let after: string | undefined;
  let assetsRead = 0;
  let pagesQueried = 0;
  let assetsHydrated = 0;
  const images: GalleryImage[] = [];

  for (;;) {
    const page = await MediaLibrary.getAssetsAsync({
      mediaType: [MediaLibrary.MediaType.photo],
      // false = descending → newest first (Expo MediaLibrary SortBy docs).
      sortBy: [[MediaLibrary.SortBy.creationTime, false]],
      first: pageSize,
      ...(after ? { after } : {}),
    });
    pagesQueried += 1;

    const light = page.assets.map(toLightweight);
    const filtered = collectNewSinceFloor(light, floorCursor, inspected);
    assetsRead += filtered.examined;

    for (const candidate of filtered.newCandidates) {
      const hydrated = await hydrateAsset(candidate.raw);
      assetsHydrated += 1;
      images.push(hydrated);
    }

    if (filtered.reachedFloor || !page.hasNextPage) {
      break;
    }
    after = page.endCursor;
  }

  return {
    images,
    metrics: {
      assetsRead,
      pagesQueried,
      assetsHydrated,
      newCandidates: images.length,
      durationMs: (options.now ?? Date.now)() - started,
    },
  };
}

/** Fetch the single most-recent photo — used to build the session start marker. */
export async function queryMostRecentPhoto(): Promise<GalleryImage | null> {
  const page = await MediaLibrary.getAssetsAsync({
    mediaType: [MediaLibrary.MediaType.photo],
    sortBy: [[MediaLibrary.SortBy.creationTime, false]],
    first: 1,
  });
  const first = page.assets[0];
  if (!first) {
    return null;
  }
  return hydrateAsset(first);
}

export function subscribeToGalleryChanges(onChange: () => void): { remove: () => void } {
  const sub = MediaLibrary.addListener(() => onChange());
  return { remove: () => sub.remove() };
}
