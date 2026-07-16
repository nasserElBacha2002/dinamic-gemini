/**
 * Photos-only admission filter (Fase 0, §14).
 *
 * Decides whether a MediaStore row is admissible into the capture flow. Every rejection
 * carries a machine-readable reason so a new video in the gallery is provably ignored:
 * it produces no queue entry, no upload, and never moves the marker.
 */
import type { GalleryImage } from '../domain/entities/galleryImage';
import {
  extensionOf,
  isAllowedImageExtension,
  isAllowedImageMime,
  isVideoMime,
  normalizeMime,
} from '../shared/constants/imageFormats';

export type ImageRejectionReason =
  | 'video_mime'
  | 'video_extension'
  | 'missing_mime'
  | 'octet_stream'
  | 'disallowed_mime'
  | 'disallowed_extension'
  | 'empty_size'
  | 'unreadable_dimensions';

export type ImageAdmission =
  | { readonly admitted: true }
  | { readonly admitted: false; readonly reason: ImageRejectionReason };

const _VIDEO_EXTENSIONS = new Set([
  '.mp4',
  '.mov',
  '.avi',
  '.mkv',
  '.webm',
  '.m4v',
  '.3gp',
  '.mts',
]);

const ADMITTED: ImageAdmission = { admitted: true };

function reject(reason: ImageRejectionReason): ImageAdmission {
  return { admitted: false, reason };
}

/**
 * Pure admission decision. Note: this does NOT decode the file — decodability is verified
 * separately by the stability step (which needs device I/O). Dimensions are checked only
 * when MediaStore already reported them (0 is treated as "unknown", not a hard reject here,
 * because some OEMs populate width/height lazily; the stability probe finalizes this).
 */
export function admitImage(image: GalleryImage): ImageAdmission {
  const mime = normalizeMime(image.mimeType);
  const ext = extensionOf(image.displayName);

  // Hard video rejections first (belt-and-suspenders even though we query Images only).
  if (isVideoMime(mime)) {
    return reject('video_mime');
  }
  if (_VIDEO_EXTENSIONS.has(ext)) {
    return reject('video_extension');
  }

  if (!mime) {
    return reject('missing_mime');
  }
  if (mime === 'application/octet-stream') {
    return reject('octet_stream');
  }
  if (!isAllowedImageMime(mime)) {
    return reject('disallowed_mime');
  }
  // Extension must be coherent with an allowed image type when present.
  if (ext && !isAllowedImageExtension(image.displayName)) {
    return reject('disallowed_extension');
  }
  if (!(image.size > 0)) {
    return reject('empty_size');
  }
  return ADMITTED;
}

export function isAdmissibleImage(image: GalleryImage): boolean {
  return admitImage(image).admitted;
}
