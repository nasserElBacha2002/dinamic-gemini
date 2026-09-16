import * as FileSystem from 'expo-file-system';

import { base64ToBytes } from '../../core/base64';
import { sha256BytesHex } from '../../core/payloadFingerprint';
import { isValidStagedSha256 } from '../../database/repositories/exportPrepRepository';

/**
 * SHA-256 of staged file bytes as pure 64-char hex (no `sha256:` prefix).
 * Throws if the file cannot be read or the digest is invalid.
 */
export async function hashStagedFileSha256Hex(uri: string): Promise<string> {
  const b64 = await FileSystem.readAsStringAsync(uri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  const bytes = base64ToBytes(b64);
  if (bytes.byteLength === 0) {
    throw Object.assign(new Error('EXPORT_PREP_HASH_EMPTY'), { code: 'EXPORT_PREP_HASH_EMPTY' });
  }
  const hex = sha256BytesHex(bytes).trim().toLowerCase();
  if (!isValidStagedSha256(hex)) {
    throw Object.assign(new Error('EXPORT_PREP_HASH_INVALID'), { code: 'EXPORT_PREP_HASH_INVALID' });
  }
  return hex;
}
