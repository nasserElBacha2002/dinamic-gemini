import * as digestModule from './digestAbsoluteFile';
import { DigestCapabilityError, DigestIoError } from './digestAbsoluteFile';
import { isValidStagedSha256 } from '../../database/repositories/exportPrepRepository';

/** Current staging hash implementation — streaming native/file digest only. */
export type StagedHashMode = 'native_file';

export type StagedHashResult = {
  readonly sha256: string;
  readonly bytesHashed: number;
  readonly hashMode: StagedHashMode;
};

/**
 * SHA-256 of staged file bytes as pure 64-char lowercase hex (no `sha256:` prefix).
 * Uses native/file streaming digest — does **not** load the JPEG as Base64 into JS.
 */
export async function hashStagedFileSha256Hex(uri: string): Promise<string> {
  const result = await hashStagedFileSha256Detailed(uri);
  return result.sha256;
}

export async function hashStagedFileSha256Detailed(uri: string): Promise<StagedHashResult> {
  let dig: Awaited<ReturnType<typeof digestModule.digestAbsoluteFile>>;
  try {
    dig = await digestModule.digestAbsoluteFile(uri);
  } catch (error) {
    if (error instanceof DigestCapabilityError || error instanceof DigestIoError) {
      throw error;
    }
    const message = error instanceof Error ? error.message : 'EXPORT_PREP_HASH_FAILED';
    throw Object.assign(new DigestIoError(message, error), {
      code: 'EXPORT_PREP_HASH_FAILED',
    });
  }
  if (!(dig.size > 0)) {
    throw Object.assign(new DigestIoError('EXPORT_PREP_HASH_EMPTY'), {
      code: 'EXPORT_PREP_HASH_EMPTY',
    });
  }
  const hex = dig.sha256.trim().toLowerCase();
  if (!isValidStagedSha256(hex)) {
    throw Object.assign(new DigestIoError('EXPORT_PREP_HASH_INVALID'), {
      code: 'EXPORT_PREP_HASH_INVALID',
    });
  }
  return {
    sha256: hex,
    bytesHashed: dig.size,
    hashMode: 'native_file',
  };
}

export type ClassifiedStagedDigestError = {
  readonly failure: 'STAGING_DIGEST_UNAVAILABLE' | 'STAGING_DIGEST_FAILED';
  readonly code: string;
  readonly reason: string;
};

/** Map digest exceptions to READY validation failures (never SHA_MISMATCH). */
export function classifyStagedDigestError(error: unknown): ClassifiedStagedDigestError {
  if (error instanceof DigestCapabilityError) {
    return {
      failure: 'STAGING_DIGEST_UNAVAILABLE',
      code: error.code,
      reason: 'digest_capability_unavailable',
    };
  }
  if (error instanceof DigestIoError) {
    return {
      failure: 'STAGING_DIGEST_FAILED',
      code: error.code,
      reason: 'digest_io_failed',
    };
  }
  const code =
    error && typeof error === 'object' && 'code' in error
      ? String((error as { code: unknown }).code)
      : '';
  if (
    code === 'DIGEST_UNAVAILABLE' ||
    code === 'EXPORT_PREP_DIGEST_UNAVAILABLE' ||
    (error instanceof Error && /digestFile unavailable/i.test(error.message))
  ) {
    return {
      failure: 'STAGING_DIGEST_UNAVAILABLE',
      code: code || 'DIGEST_UNAVAILABLE',
      reason: 'digest_capability_unavailable',
    };
  }
  return {
    failure: 'STAGING_DIGEST_FAILED',
    code: code || 'EXPORT_PREP_HASH_FAILED',
    reason: 'digest_io_failed',
  };
}
