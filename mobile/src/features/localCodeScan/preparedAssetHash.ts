import * as FileSystem from 'expo-file-system';

import { base64ToBytes } from '../../core/base64';
import { hashPayloadFingerprint, sha256BytesHex } from '../../core/payloadFingerprint';

/**
 * SHA-256 of prepared file bytes. Prefer hashing once after prepare and reuse.
 */
export async function hashPreparedFileSha256(uri: string): Promise<string> {
  const b64 = await FileSystem.readAsStringAsync(uri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  const bytes = base64ToBytes(b64);
  return `sha256:${sha256BytesHex(bytes)}`;
}

/** Fallback fingerprint when file read fails — still SHA-256, not FNV. */
export function hashPreparedMetaSha256(input: {
  readonly uri: string;
  readonly bytes: number;
  readonly width: number;
  readonly height: number;
}): string {
  return hashPayloadFingerprint(
    `${input.uri}|${input.bytes}|${input.width}x${input.height}`,
  );
}
