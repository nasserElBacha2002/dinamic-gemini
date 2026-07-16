/**
 * Composite marker captured at the start of a capture session.
 *
 * Per audit: a marker based solely on timestamp OR solely on filename is unreliable.
 * We persist a composite of MediaStore `_ID` + `DATE_ADDED` (the ordering cursor) plus
 * disambiguating metadata, scoped to a single inventory + aisle.
 */
export interface CaptureMarker {
  /** MediaStore `_ID` of the last existing image at session start (null = empty gallery). */
  readonly mediaStoreId: number | null;
  /** MediaStore `DATE_ADDED` (epoch seconds) of that image (null = empty gallery). */
  readonly dateAdded: number | null;
  /** MediaStore `DATE_MODIFIED` (epoch seconds), disambiguation only. */
  readonly dateModified: number | null;
  /** `DISPLAY_NAME`, disambiguation / audit only. */
  readonly displayName: string | null;
  /** `SIZE` in bytes, disambiguation / audit only. */
  readonly size: number | null;
  /** `BUCKET_ID` (drone folder), optional scoping. */
  readonly bucketId: number | null;
  /** Context this marker belongs to (prevents cross-aisle mixing). */
  readonly inventoryId: string;
  readonly aisleId: string;
}
