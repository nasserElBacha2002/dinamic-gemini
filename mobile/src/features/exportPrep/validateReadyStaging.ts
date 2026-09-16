import type { ExportPrepJobRow } from './exportPrepTypes';
import { isValidStagedSha256 } from '../../database/repositories/exportPrepRepository';
import { stagingFileExists } from './exportStaging';
import { hashStagedFileSha256Hex } from './stagedSha256';
import * as FileSystem from 'expo-file-system';

export type ReadyValidationMode = 'light' | 'strong';

export type ReadyValidationFailure =
  | 'MISSING_STAGING_URI'
  | 'MISSING_EXPORT_FILE_NAME'
  | 'INVALID_SIZE_BYTES'
  | 'INVALID_SHA256_FORMAT'
  | 'STAGING_FILE_MISSING'
  | 'STAGING_SIZE_MISMATCH'
  | 'STAGING_SHA_MISMATCH';

export interface ReadyValidationResult {
  readonly ok: boolean;
  readonly failure?: ReadyValidationFailure;
  readonly actualSizeBytes?: number;
  readonly actualSha256?: string;
}

/**
 * Central READY integrity check.
 *
 * Both modes require: staging_uri, export_file_name, size_bytes > 0, SHA hex format,
 * staging file exists, and **real file size === size_bytes**.
 *
 * - `light` (REVIEW_OPEN / recovery soft path): stops after size match — no re-hash.
 * - `strong` (EXPORT_PREFLIGHT, reinclude, promote QUEUED→READY): also recomputes
 *   SHA-256 of staged bytes and requires equality with persisted sha256.
 *
 * A well-formed SHA string alone is never treated as integrity proof.
 */
export async function validateReadyStaging(
  job: Pick<
    ExportPrepJobRow,
    'staging_uri' | 'export_file_name' | 'size_bytes' | 'sha256'
  >,
  mode: ReadyValidationMode,
): Promise<ReadyValidationResult> {
  if (!job.staging_uri) {
    return { ok: false, failure: 'MISSING_STAGING_URI' };
  }
  if (!job.export_file_name) {
    return { ok: false, failure: 'MISSING_EXPORT_FILE_NAME' };
  }
  if (!(job.size_bytes != null && job.size_bytes > 0)) {
    return { ok: false, failure: 'INVALID_SIZE_BYTES' };
  }
  if (!isValidStagedSha256(job.sha256)) {
    return { ok: false, failure: 'INVALID_SHA256_FORMAT' };
  }
  if (!(await stagingFileExists(job.staging_uri))) {
    return { ok: false, failure: 'STAGING_FILE_MISSING' };
  }

  const info = await FileSystem.getInfoAsync(job.staging_uri, { size: true });
  const actualSize =
    info.exists && typeof info.size === 'number' ? info.size : 0;
  if (actualSize !== job.size_bytes) {
    return {
      ok: false,
      failure: 'STAGING_SIZE_MISMATCH',
      actualSizeBytes: actualSize,
    };
  }

  if (mode === 'light') {
    return { ok: true, actualSizeBytes: actualSize };
  }

  let actualSha: string;
  try {
    actualSha = await hashStagedFileSha256Hex(job.staging_uri);
  } catch {
    return { ok: false, failure: 'STAGING_SHA_MISMATCH', actualSizeBytes: actualSize };
  }
  if (actualSha !== job.sha256!.trim().toLowerCase()) {
    return {
      ok: false,
      failure: 'STAGING_SHA_MISMATCH',
      actualSizeBytes: actualSize,
      actualSha256: actualSha,
    };
  }
  return { ok: true, actualSizeBytes: actualSize, actualSha256: actualSha };
}

/** Source MediaStore/original URI must exist and be non-empty before enqueue. */
export async function sourceUriIsReadable(uri: string | null | undefined): Promise<boolean> {
  if (!uri) return false;
  try {
    const info = await FileSystem.getInfoAsync(uri, { size: true });
    return Boolean(info.exists && typeof info.size === 'number' && info.size > 0);
  } catch {
    return false;
  }
}
