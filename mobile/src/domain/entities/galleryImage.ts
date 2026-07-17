/**
 * Device-independent representation of one MediaStore image row.
 *
 * Only fields sourced from `MediaStore.Images.Media` are modeled. There is intentionally
 * no video/duration field: the mobile flow never reads `MediaStore.Video`.
 */
export interface GalleryImage {
  /**
   * Stable identity from the media library (Expo `Asset.id` / MediaStore row key).
   * Always a non-empty string — never a silent numeric fallback.
   */
  readonly assetId: string;
  /**
   * Numeric MediaStore `_ID` when `assetId` is a validated decimal integer.
   * Absent when the library id is non-numeric; never coerced to `0`.
   */
  readonly mediaStoreNumericId?: number;
  /** content:// or file:// URI to open/read the image. */
  readonly uri: string;
  /** MediaStore `DISPLAY_NAME` (file name). */
  readonly displayName: string;
  /** MediaStore `MIME_TYPE` (e.g. image/jpeg). May be empty on some OEMs. */
  readonly mimeType: string;
  /** Size in bytes (0 when unknown / not yet hydrated). */
  readonly size: number;
  /** Width in pixels (0 when unknown). */
  readonly width: number;
  /** Height in pixels (0 when unknown). */
  readonly height: number;
  /** Creation / DATE_ADDED in epoch seconds. */
  readonly dateAdded: number;
  /** Modification time in epoch seconds. */
  readonly dateModified: number;
  /** Album/folder identifier, when available. */
  readonly bucketId: number | null;
  /** Relative path / album id, when available. */
  readonly relativePath: string | null;
}

/**
 * Parse a library asset id into a numeric MediaStore id when it is a strict decimal integer.
 * Returns undefined for empty/non-numeric values — callers must NOT substitute 0.
 */
export function parseMediaStoreNumericId(assetId: string): number | undefined {
  const raw = assetId.trim();
  if (!/^\d+$/.test(raw)) {
    return undefined;
  }
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n < 0) {
    return undefined;
  }
  return n;
}

/** Require a non-empty asset id; throw on invalid integration data. */
export function requireAssetId(raw: string | null | undefined): string {
  const id = (raw ?? '').trim();
  if (!id) {
    throw new Error('Invalid media asset id: empty');
  }
  return id;
}
