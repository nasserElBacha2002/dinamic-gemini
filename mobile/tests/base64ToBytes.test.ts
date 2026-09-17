/**
 * Regression: padded base64 must decode on the RN/Hermes path (no Buffer).
 * Bug: `((len * 3) / 4) | 0 - padding` → outLen -1 → "A negative value cannot be an index".
 */

import { base64ToBytes } from '../src/core/base64';
import { sha256BytesHex } from '../src/core/payloadFingerprint';

function withHermesBase64Path<T>(fn: () => T): T {
  const g = globalThis as { Buffer?: unknown };
  const saved = g.Buffer;
  // Force the lookup decoder used on device (Hermes has no Buffer).
  // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
  delete g.Buffer;
  try {
    return fn();
  } finally {
    if (saved !== undefined) {
      g.Buffer = saved;
    }
  }
}

describe('base64ToBytes', () => {
  it('decodes unpadded length (multiple of 3 bytes)', () => {
    withHermesBase64Path(() => {
      const bytes = base64ToBytes('TWFu');
      expect(Array.from(bytes)).toEqual([77, 97, 110]);
    });
  });

  it('decodes single-pad base64 without negative outLen', () => {
    withHermesBase64Path(() => {
      const bytes = base64ToBytes('TWE=');
      expect(Array.from(bytes)).toEqual([77, 97]);
    });
  });

  it('decodes double-pad base64 without negative outLen', () => {
    withHermesBase64Path(() => {
      const bytes = base64ToBytes('TQ==');
      expect(Array.from(bytes)).toEqual([77]);
    });
  });

  it('hashes padded JPEG-like base64 (export prep hash path)', () => {
    const jpegHead = Buffer.from([0xff, 0xd8, 0xff, 0xe0]).toString('base64'); // ends with =
    expect(jpegHead.endsWith('=')).toBe(true);
    withHermesBase64Path(() => {
      const bytes = base64ToBytes(jpegHead);
      expect(bytes.byteLength).toBe(4);
      expect(sha256BytesHex(bytes)).toMatch(/^[0-9a-f]{64}$/);
    });
  });
});
