import { buildStoreZipBytes } from '../src/features/exportPrep/streamingZipWriter';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  makeDirectoryAsync: jest.fn(async () => undefined),
  writeAsStringAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
}));

describe('buildStoreZipBytes', () => {
  it('reads one entry at a time and produces a non-empty archive', async () => {
    const order: string[] = [];
    const bytes = await buildStoreZipBytes([
      {
        path: 'results.csv',
        getBytes: () => {
          order.push('csv');
          return new TextEncoder().encode('a,b\n');
        },
      },
      {
        path: 'photos/0001_x.jpg',
        getBytes: async () => {
          order.push('photo');
          return new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
        },
      },
    ]);
    expect(order).toEqual(['csv', 'photo']);
    expect(bytes.byteLength).toBeGreaterThan(0);
    expect(bytes[0]).toBe(0x50);
    expect(bytes[1]).toBe(0x4b);
  });

  it('synthetic: 100 tiny entries exercise sequential read (not a memory soak)', async () => {
    // Synthetic unit check only — does not prove device peak memory.
    const entries = Array.from({ length: 100 }, (_, i) => ({
      path: `photos/${String(i + 1).padStart(4, '0')}_p.jpg`,
      getBytes: () => new Uint8Array([i & 0xff]),
    }));
    const zip = await buildStoreZipBytes(entries);
    expect(zip.byteLength).toBeGreaterThan(100);
  });
});
