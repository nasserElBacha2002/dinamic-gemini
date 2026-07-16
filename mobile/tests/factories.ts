import type { GalleryImage } from '../src/domain/entities/galleryImage';
import { parseMediaStoreNumericId } from '../src/domain/entities/galleryImage';

/** Build a GalleryImage with sensible photo defaults; override per test. */
export function makeImage(overrides: Partial<GalleryImage> = {}): GalleryImage {
  const assetId = overrides.assetId ?? '1';
  const numeric = parseMediaStoreNumericId(assetId);
  const base: GalleryImage = {
    assetId,
    uri: `content://media/external/images/media/${assetId}`,
    displayName: 'DJI_0001.jpg',
    mimeType: 'image/jpeg',
    size: 2_000_000,
    width: 4000,
    height: 3000,
    dateAdded: 1_700_000_000,
    dateModified: 1_700_000_000,
    bucketId: 42,
    relativePath: 'DCIM/Drone/',
    ...(numeric !== undefined ? { mediaStoreNumericId: numeric } : {}),
  };
  return { ...base, ...overrides, assetId: overrides.assetId ?? assetId };
}

/** Build a video row as it could (wrongly) appear if injected into core. */
export function makeVideo(overrides: Partial<GalleryImage> = {}): GalleryImage {
  return makeImage({
    assetId: '999',
    displayName: 'DJI_0002.mp4',
    mimeType: 'video/mp4',
    ...overrides,
  });
}
