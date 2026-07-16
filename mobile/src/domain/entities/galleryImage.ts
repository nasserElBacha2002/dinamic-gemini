/**
 * Device-independent representation of one MediaStore image row.
 *
 * Only fields sourced from `MediaStore.Images.Media` are modeled. There is intentionally
 * no video/duration field: the mobile flow never reads `MediaStore.Video`.
 */
export interface GalleryImage {
  /** MediaStore `_ID` — stable within the device MediaStore. */
  readonly mediaStoreId: number;
  /** content:// URI to open/read the image. */
  readonly uri: string;
  /** MediaStore `DISPLAY_NAME` (file name). */
  readonly displayName: string;
  /** MediaStore `MIME_TYPE` (e.g. image/jpeg). May be empty on some OEMs. */
  readonly mimeType: string;
  /** MediaStore `SIZE` in bytes. */
  readonly size: number;
  /** MediaStore `WIDTH` in pixels (0 when unknown). */
  readonly width: number;
  /** MediaStore `HEIGHT` in pixels (0 when unknown). */
  readonly height: number;
  /** MediaStore `DATE_ADDED` in epoch seconds. */
  readonly dateAdded: number;
  /** MediaStore `DATE_MODIFIED` in epoch seconds. */
  readonly dateModified: number;
  /** MediaStore `BUCKET_ID` (album/folder identifier), when available. */
  readonly bucketId: number | null;
  /** MediaStore `RELATIVE_PATH` (scoped storage), when available. */
  readonly relativePath: string | null;
}
