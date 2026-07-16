import type { GalleryImage } from '../src/domain/entities/galleryImage';

/** Build a GalleryImage with sensible photo defaults; override per test. */
export function makeImage(overrides: Partial<GalleryImage> = {}): GalleryImage {
  return {
    mediaStoreId: 1,
    uri: 'content://media/external/images/media/1',
    displayName: 'DJI_0001.jpg',
    mimeType: 'image/jpeg',
    size: 2_000_000,
    width: 4000,
    height: 3000,
    dateAdded: 1_700_000_000,
    dateModified: 1_700_000_000,
    bucketId: 42,
    relativePath: 'DCIM/Drone/',
    ...overrides,
  };
}

/** Build a video row as it could (wrongly) appear if a video slipped into candidates. */
export function makeVideo(overrides: Partial<GalleryImage> = {}): GalleryImage {
  return makeImage({
    mediaStoreId: 999,
    displayName: 'DJI_0002.mp4',
    mimeType: 'video/mp4',
    ...overrides,
  });
}
