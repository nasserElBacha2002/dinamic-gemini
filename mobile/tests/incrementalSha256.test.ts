/**
 * IncrementalSha256 must match Node crypto / payloadFingerprint (FIPS 180-4).
 * Regression: missing K[42] caused zip_sha_mismatch vs Android MessageDigest.
 */

import { createHash } from 'node:crypto';

import { IncrementalSha256 } from '../src/features/exportPrep/incrementalSha256';
import { sha256BytesHex } from '../src/core/payloadFingerprint';

function nodeSha(bytes: Uint8Array): string {
  return createHash('sha256').update(Buffer.from(bytes)).digest('hex');
}

function incrementalChunked(bytes: Uint8Array, chunk: number): string {
  const h = new IncrementalSha256();
  for (let i = 0; i < bytes.length; i += chunk) {
    h.update(bytes.subarray(i, Math.min(i + chunk, bytes.length)));
  }
  return h.digestHex();
}

describe('IncrementalSha256', () => {
  it('matches empty / abc NIST vectors via Node crypto', () => {
    expect(incrementalChunked(new Uint8Array(0), 64)).toBe(nodeSha(new Uint8Array(0)));
    expect(incrementalChunked(new TextEncoder().encode('abc'), 1)).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  it('matches sha256BytesHex and crypto across chunk sizes (incl. 256KiB sink chunks)', () => {
    const bytes = new Uint8Array(300_000);
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = (i * 17) & 0xff;
    }
    const expected = nodeSha(bytes);
    expect(sha256BytesHex(bytes)).toBe(expected);
    expect(incrementalChunked(bytes, 256 * 1024)).toBe(expected);
    expect(incrementalChunked(bytes, 63)).toBe(expected);
    expect(incrementalChunked(bytes, 1)).toBe(expected);
  });

  it('matches crypto for ~12MiB multi-chunk (ZIP-sized)', () => {
    const bytes = new Uint8Array(12 * 1024 * 1024);
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = i & 0xff;
    }
    expect(incrementalChunked(bytes, 256 * 1024)).toBe(nodeSha(bytes));
  }, 60_000);
});
