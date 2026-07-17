/**
 * Composite marker captured at the start of a capture session.
 *
 * Per audit: a marker based solely on timestamp OR solely on filename is unreliable.
 * We persist a composite of library asset id + DATE_ADDED plus disambiguating metadata.
 */
export interface CaptureMarker {
  /** Original library asset id of the last existing image (null = empty gallery). */
  readonly assetId: string | null;
  /** MediaStore `_ID` when assetId is numeric (null otherwise / empty gallery). */
  readonly mediaStoreNumericId: number | null;
  /** DATE_ADDED (epoch seconds) of that image (null = empty gallery). */
  readonly dateAdded: number | null;
  /** DATE_MODIFIED (epoch seconds), disambiguation only. */
  readonly dateModified: number | null;
  /** DISPLAY_NAME, disambiguation / audit only. */
  readonly displayName: string | null;
  /** SIZE in bytes, disambiguation / audit only. */
  readonly size: number | null;
  /** BUCKET_ID (drone folder), optional scoping. */
  readonly bucketId: number | null;
  readonly inventoryId: string;
  readonly aisleId: string;
}
