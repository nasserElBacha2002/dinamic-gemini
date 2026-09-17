/**
 * UTF-8 helpers must work when TextDecoder/TextEncoder are absent (Hermes).
 */

import { decodeUtf8, encodeUtf8 } from '../src/features/exportPrep/utf8';

describe('exportPrep utf8 (Hermes-safe)', () => {
  const originalDecoder = globalThis.TextDecoder;
  const originalEncoder = globalThis.TextEncoder;

  afterEach(() => {
    Object.defineProperty(globalThis, 'TextDecoder', {
      value: originalDecoder,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, 'TextEncoder', {
      value: originalEncoder,
      configurable: true,
      writable: true,
    });
  });

  it('round-trips ASCII and multibyte without TextDecoder', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis as any).TextDecoder;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis as any).TextEncoder;

    const samples = ['results.csv', 'photos/0001_p.jpg', 'café', '日本語'];
    for (const s of samples) {
      const bytes = encodeUtf8(s);
      expect(decodeUtf8(bytes)).toBe(s);
    }
  });

  it('decodes ZIP path bytes that previously used TextDecoder', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis as any).TextDecoder;
    const bytes = Uint8Array.from([0x6d, 0x61, 0x6e, 0x69, 0x66, 0x65, 0x73, 0x74, 0x2e, 0x6a, 0x73, 0x6f, 0x6e]);
    expect(decodeUtf8(bytes)).toBe('manifest.json');
  });
});
