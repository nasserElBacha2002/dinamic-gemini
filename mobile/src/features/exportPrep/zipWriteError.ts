/**
 * Typed ZIP write failures — kept separate from boundedZipWriter to avoid
 * require cycles with binaryAppendSink.
 */

export type ZipWriteFailure =
  | 'ZIP_ENTRY_TOO_LARGE'
  | 'ZIP_TOTAL_TOO_LARGE'
  | 'ZIP_TOO_MANY_ENTRIES'
  | 'ZIP_OFFSET_OVERFLOW'
  | 'ZIP_UNSUPPORTED_ZIP64'
  | 'ZIP_SOURCE_CHANGED'
  | 'ZIP_SOURCE_READ_FAILED'
  | 'ZIP_WRITE_FAILED'
  | 'ZIP_CANCELLED'
  | 'ZIP_VALIDATION_FAILED';

export class ZipWriteError extends Error {
  readonly code: ZipWriteFailure;

  constructor(code: ZipWriteFailure, detail: string) {
    super(`${code}: ${detail}`);
    this.name = 'ZipWriteError';
    this.code = code;
  }
}
