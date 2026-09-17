import { digestAbsoluteFile } from './digestAbsoluteFile';
import { isValidStagedSha256 } from '../../database/repositories/exportPrepRepository';

export type StagedHashMode = 'native_file' | 'js_base64_full_file';

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
  let dig: Awaited<ReturnType<typeof digestAbsoluteFile>>;
  try {
    dig = await digestAbsoluteFile(uri);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'EXPORT_PREP_HASH_FAILED';
    throw Object.assign(new Error(message), {
      code: 'EXPORT_PREP_HASH_FAILED',
      cause: error,
    });
  }
  if (!(dig.size > 0)) {
    throw Object.assign(new Error('EXPORT_PREP_HASH_EMPTY'), { code: 'EXPORT_PREP_HASH_EMPTY' });
  }
  const hex = dig.sha256.trim().toLowerCase();
  if (!isValidStagedSha256(hex)) {
    throw Object.assign(new Error('EXPORT_PREP_HASH_INVALID'), { code: 'EXPORT_PREP_HASH_INVALID' });
  }
  return {
    sha256: hex,
    bytesHashed: dig.size,
    hashMode: 'native_file',
  };
}
