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

export type ReadyDigestHashMode = 'reused_persisted' | 'native_file';
export type ReadyDigestHashSource =
  | 'staging_ready'
  | 'validation_fallback'
  | 'computed';

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
}

export type ValidateReadyStagingOptions = {
  /** Force native re-hash even when identity would allow reuse. */
  readonly forceRehash?: boolean;
};

function monoNow(): number {
  const p = (globalThis as { performance?: { now(): number } }).performance;
  return typeof p?.now === 'function' ? p.now() : Date.now();
}

/**
 * Staging write-once invariant (export prep):
 * After markReady, the staged file is not rewritten in place. invalidateReady clears
 * staging_uri/sha256 before any new copy. Therefore a READY job with matching on-disk
 * size and a valid persisted sha256 may reuse that digest during strong validation.
 *
 * Fallback to native re-hash when:
 * - ready_at missing (legacy / incomplete rows)
 * - modificationTime is clearly newer than ready_at (possible overwrite)
 * - forceRehash is set
 * - any identity check fails before size mismatch
 */
function shouldReusePersistedSha(input: {
  readonly readyAt: string | null | undefined;
  readonly modificationTimeSec: number | null;
  readonly forceRehash: boolean;
}): { reuse: boolean; reason: string } {
  if (input.forceRehash) {
    return { reuse: false, reason: 'force_rehash' };
  }
  if (!input.readyAt) {
    return { reuse: false, reason: 'legacy_missing_ready_at' };
  }
  const readyMs = Date.parse(input.readyAt);
  if (!Number.isFinite(readyMs)) {
    return { reuse: false, reason: 'ready_at_unparseable' };
  }
  if (input.modificationTimeSec != null && Number.isFinite(input.modificationTimeSec)) {
    const mtimeMs = input.modificationTimeSec * 1000;
    // 2s skew: ready_at is written after digest; mtime is file close time.
    if (mtimeMs > readyMs + 2000) {
      return { reuse: false, reason: 'staging_mtime_newer_than_ready_at' };
    }
  }
  return {
    reuse: true,
    reason: 'ready_immutable_staging_size_match',
  };
}

/**
 * Central READY integrity check.
 *
 * Both modes require: staging_uri, export_file_name, size_bytes > 0, SHA hex format,
 * staging file exists, and **real file size === size_bytes**.
 *
 * - `light`: stops after size match — no digest.
 * - `strong`: reuses persisted sha256 when the write-once identity holds; otherwise
 *   recomputes via native file digest and requires equality with persisted sha256.
 */
export async function validateReadyStaging(
  job: Pick<
    ExportPrepJobRow,
    'staging_uri' | 'export_file_name' | 'size_bytes' | 'sha256' | 'ready_at'
  >,
  mode: ReadyValidationMode,
  options?: ValidateReadyStagingOptions,
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
  const modificationTimeSec =
    info.exists && typeof (info as { modificationTime?: unknown }).modificationTime === 'number'
      ? ((info as { modificationTime: number }).modificationTime)
      : null;

  const decision = shouldReusePersistedSha({
    readyAt: job.ready_at,
    modificationTimeSec,
    forceRehash: options?.forceRehash === true,
  });

  if (decision.reuse) {
    return {
      ok: true,
      actualSizeBytes: actualSize,
      actualSha256: expectedSha,
      digest: {
        hashMode: 'reused_persisted',
        hashSource: 'staging_ready',
        bytesHashed: 0,
        durationMs: 0,
        reason: decision.reason,
      },
    };
  }

  const t0 = monoNow();
  let actualSha: string;
  let bytesHashed = actualSize;
  try {
    // Prefer hex helper so unit tests can mock digest without native modules.
    actualSha = await hashStagedFileSha256Hex(job.staging_uri);
    bytesHashed = actualSize;
  } catch {
    return {
      ok: false,
      failure: 'STAGING_SHA_MISMATCH',
      actualSizeBytes: actualSize,
      digest: {
        hashMode: 'native_file',
        hashSource: 'validation_fallback',
        bytesHashed: 0,
        durationMs: monoNow() - t0,
        reason: decision.reason,
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
        hashSource: 'validation_fallback',
        bytesHashed,
        durationMs,
        reason: `${decision.reason}|sha_mismatch`,
      },
    };
  }
  return {
    ok: true,
    actualSizeBytes: actualSize,
    actualSha256: actualSha,
    digest: {
      hashMode: 'native_file',
      hashSource: decision.reason === 'force_rehash' ? 'validation_fallback' : 'validation_fallback',
      bytesHashed,
      durationMs,
      reason: decision.reason,
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
