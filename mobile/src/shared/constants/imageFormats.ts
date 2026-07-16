/**
 * Photos-only allowlist for the mobile capture client (Fase 0).
 *
 * Aligned with the audited backend behavior:
 *  - Aisle asset upload accepts any `image/*` MIME (materializer `_detect_asset_type`), but
 *    the mobile client deliberately restricts itself to a stricter, explicit allowlist.
 *  - The LLM provider contract supports jpeg/png/webp/gif; HEIC is normalized to JPEG in the
 *    worker via pillow-heif. We allow HEIC/HEIF on-device and let the worker normalize.
 *
 * GIF/BMP/TIFF/SVG and every `video/*` type are intentionally excluded from the mobile flow.
 */

/** MIME types the mobile client is allowed to detect, queue and upload. */
export const ALLOWED_IMAGE_MIME_TYPES: readonly string[] = [
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
  'image/heic',
  'image/heif',
] as const;

/** File extensions coherent with the allowed MIME types (lower-case, dot-prefixed). */
export const ALLOWED_IMAGE_EXTENSIONS: readonly string[] = [
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.heic',
  '.heif',
] as const;

/**
 * Image formats explicitly excluded from the mobile flow even though the backend may
 * technically accept some of them via a generic `image/*` check.
 */
export const EXCLUDED_IMAGE_MIME_TYPES: readonly string[] = [
  'image/gif',
  'image/bmp',
  'image/tiff',
  'image/svg+xml',
] as const;

const _ALLOWED_MIME_SET = new Set(ALLOWED_IMAGE_MIME_TYPES);
const _ALLOWED_EXT_SET = new Set(ALLOWED_IMAGE_EXTENSIONS);

/** Normalize a raw Content-Type / MIME string: lower-case, strip parameters and whitespace. */
export function normalizeMime(raw: string | null | undefined): string {
  if (!raw) {
    return '';
  }
  return raw.trim().toLowerCase().split(';', 1)[0]!.trim();
}

/** Extract a lower-case, dot-prefixed extension from a filename (or '' when absent). */
export function extensionOf(filename: string | null | undefined): string {
  if (!filename) {
    return '';
  }
  const name = filename.trim().toLowerCase();
  const dot = name.lastIndexOf('.');
  if (dot < 0 || dot === name.length - 1) {
    return '';
  }
  return name.slice(dot);
}

export function isAllowedImageMime(raw: string | null | undefined): boolean {
  return _ALLOWED_MIME_SET.has(normalizeMime(raw));
}

export function isAllowedImageExtension(filename: string | null | undefined): boolean {
  return _ALLOWED_EXT_SET.has(extensionOf(filename));
}

export function isVideoMime(raw: string | null | undefined): boolean {
  return normalizeMime(raw).startsWith('video/');
}
