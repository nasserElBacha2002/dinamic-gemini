/**
 * MediaStore.Images adapter (Android) built on expo-media-library.
 *
 * PHOTOS-ONLY: every query passes `mediaType: photo`. We never request `video` or `all`.
 * The generic types here allow the pure-core detection/filter to run against real device rows.
 *
 * NOTE: This file requires the Expo dev toolchain to compile/run; it is intentionally
 * excluded from the Fase 0 pure-core sandbox validation.
 */
import * as FileSystem from 'expo-file-system';
import * as MediaLibrary from 'expo-media-library';

import type { GalleryImage } from '../domain/entities/galleryImage';
import { extensionOf } from '../shared/constants/imageFormats';

export interface PermissionState {
  readonly granted: boolean;
  /** Android 14+: user granted access to a subset of photos only. */
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

/** Request ONLY photo read access. Never requests video permission. */
export async function requestPhotoPermission(): Promise<PermissionState> {
  // `writeOnly: false` => read access. On Android this maps to READ_MEDIA_IMAGES
  // (+ READ_MEDIA_VISUAL_USER_SELECTED on 14+). No video permission is requested.
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

async function toGalleryImage(asset: MediaLibrary.Asset): Promise<GalleryImage> {
  // getAssetInfoAsync resolves a readable localUri and precise metadata on Android.
  const info = await MediaLibrary.getAssetInfoAsync(asset);
  const localUri = info.localUri ?? asset.uri;

  let size = 0;
  try {
    const stat = await FileSystem.getInfoAsync(localUri, { size: true });
    if (stat.exists && typeof stat.size === 'number') {
      size = stat.size;
    }
  } catch {
    size = 0;
  }

  const mediaStoreId = Number.parseInt(asset.id, 10);
  return {
    mediaStoreId: Number.isFinite(mediaStoreId) ? mediaStoreId : 0,
    uri: localUri,
    displayName: asset.filename,
    mimeType: inferMime(asset.filename),
    size,
    width: asset.width ?? 0,
    height: asset.height ?? 0,
    // expo returns creation/modification time in ms; MediaStore semantics are seconds.
    dateAdded: Math.floor((asset.creationTime ?? 0) / 1000),
    dateModified: Math.floor((asset.modificationTime ?? 0) / 1000),
    bucketId: null,
    relativePath: asset.albumId ?? null,
  };
}

export interface QueryPhotosOptions {
  /** Page size; drone bursts can be large, so paginate. */
  readonly pageSize?: number;
  /** Opaque MediaLibrary cursor for pagination. */
  readonly after?: string;
}

export interface QueryPhotosResult {
  readonly images: GalleryImage[];
  readonly endCursor: string | undefined;
  readonly hasNextPage: boolean;
}

/**
 * Query a page of images ordered by creationTime ASC (matches DATE_ADDED ASC in the
 * composite-cursor design). VIDEO IS NEVER REQUESTED.
 */
export async function queryPhotos(options: QueryPhotosOptions = {}): Promise<QueryPhotosResult> {
  const page = await MediaLibrary.getAssetsAsync({
    mediaType: [MediaLibrary.MediaType.photo],
    sortBy: [[MediaLibrary.SortBy.creationTime, false]],
    first: options.pageSize ?? 100,
    ...(options.after ? { after: options.after } : {}),
  });
  const images = await Promise.all(page.assets.map(toGalleryImage));
  return {
    images,
    endCursor: page.endCursor,
    hasNextPage: page.hasNextPage,
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
  return toGalleryImage(first);
}

/**
 * Subscribe to gallery changes. expo-media-library emits a generic change event; the
 * caller re-runs the photos-only query + pure detection. We never inspect video here.
 */
export function subscribeToGalleryChanges(onChange: () => void): { remove: () => void } {
  const sub = MediaLibrary.addListener(() => onChange());
  return { remove: () => sub.remove() };
}
