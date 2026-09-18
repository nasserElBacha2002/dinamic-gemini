import type { ExportPrepJobRow } from './exportPrepTypes';
import { isValidStagedSha256 } from '../../database/repositories/exportPrepRepository';
import { stagingFileExists } from './exportStaging';
import { hashStagedFileSha256Hex, classifyStagedDigestError } from './stagedSha256';
import * as FileSystem from 'expo-file-system';

export type ReadyValidationMode = 'light' | 'strong';

export type ReadyValidationFailure =
  | 'MISSING_STAGING_URI'
  | 'MISSING_EXPORT_FILE_NAME'
  | 'INVALID_SIZE_BYTES'
  | 'INVALID_SHA256_FORMAT'
  | 'STAGING_FILE_MISSING'
  | 'STAGING_SIZE_MISMATCH'
  | 'STAGING_SHA_MISMATCH'
  /** Native digest module/capability missing — not corruption. */
  | 'STAGING_DIGEST_UNAVAILABLE'
  /** Digest I/O/bridge failure — not a confirmed content mismatch. */
  | 'STAGING_DIGEST_FAILED';

export type ReadyDigestHashMode = 'native_file';
export type ReadyDigestHashSource = 'computed' | 'validation_fallback';

export type ReadyDigestDecision = {
  readonly hashMode: ReadyDigestHashMode;
  readonly hashSource: ReadyDigestHashSource;
  readonly bytesHashed: number;
  readonly durationMs: number;
  readonly reason: string;
};

export interface ReadyValidationResult {
  readonly ok: boolean;
  readonly failure?: ReadyValidationFailure;
  readonly actualSizeBytes?: number;
  readonly actualSha256?: string;
  readonly digest?: ReadyDigestDecision;
  /** Original technical error message when digest failed (no paths). */
  readonly digestErrorCode?: string;
}

export type ValidateReadyStagingOptions = {
  /**
   * @deprecated Strong validation always recomputes a native digest.
   * Kept for call-site compatibility; ignored.
   */
  readonly forceRehash?: boolean;
};

function monoNow(): number {
  const p = (globalThis as { performance?: { now(): number } }).performance;
  return typeof p?.now === 'function' ? p.now() : Date.now();
}

/**
 * Failures that prove READY staging is inconsistent with on-disk state.
 * Technical digest failures are excluded — READY must be preserved for retry.
 */
export function isConfirmedReadyIntegrityFailure(
  failure: ReadyValidationFailure | undefined,
): boolean {
  return (
    failure === 'STAGING_SHA_MISMATCH' ||
    failure === 'STAGING_SIZE_MISMATCH' ||
    failure === 'STAGING_FILE_MISSING' ||
    failure === 'INVALID_SHA256_FORMAT' ||
    failure === 'INVALID_SIZE_BYTES' ||
    failure === 'MISSING_STAGING_URI' ||
    failure === 'MISSING_EXPORT_FILE_NAME'
  );
}

/**
 * Central READY integrity check.
 *
 * Both modes require: staging_uri, export_file_name, size_bytes > 0, SHA hex format,
 * staging file exists, and **real file size === size_bytes**.
 *
 * - `light`: stops after size match — no digest.
 * - `strong`: always recomputes SHA-256 via native/file streaming digest and requires
 *   equality with the persisted sha256. Size match alone is never treated as content identity.
 *
 * Rationale: staged paths are versioned by convention, but the filesystem does not enforce
 * immutability of a READY URI. Reusing a persisted digest from size/mtime/ready_at would
 * accept same-size content swaps. Native digest is cheap enough (~ms) to keep integrity.
 */
export async function validateReadyStaging(
  job: Pick<
    ExportPrepJobRow,
    'staging_uri' | 'export_file_name' | 'size_bytes' | 'sha256' | 'ready_at'
  >,
  mode: ReadyValidationMode,
  _options?: ValidateReadyStagingOptions,
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

  const expectedSha = job.sha256!.trim().toLowerCase();
  const t0 = monoNow();
  let actualSha: string;
  let bytesHashed = actualSize;
  try {
    // Prefer hex helper so unit tests can mock digest without native modules.
    actualSha = await hashStagedFileSha256Hex(job.staging_uri);
    bytesHashed = actualSize;
  } catch (error) {
    const classified = classifyStagedDigestError(error);
    return {
      ok: false,
      failure: classified.failure,
      actualSizeBytes: actualSize,
      digestErrorCode: classified.code,
      digest: {
        hashMode: 'native_file',
        hashSource: 'computed',
        bytesHashed: 0,
        durationMs: monoNow() - t0,
        reason: classified.reason,
      },
    };
  }
  const durationMs = monoNow() - t0;
  if (actualSha !== expectedSha) {
    return {
      ok: false,
      failure: 'STAGING_SHA_MISMATCH',
      actualSizeBytes: actualSize,
      actualSha256: actualSha,
      digest: {
        hashMode: 'native_file',
        hashSource: 'computed',
        bytesHashed,
        durationMs,
        reason: 'sha_mismatch_after_native_digest',
      },
    };
  }
  return {
    ok: true,
    actualSizeBytes: actualSize,
    actualSha256: actualSha,
    digest: {
      hashMode: 'native_file',
      hashSource: 'computed',
      bytesHashed,
      durationMs,
      reason: 'strong_native_rehash',
    },
  };
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
