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

  it('rejects packages larger than BUILD_STORE_ZIP_BYTES_MAX', async () => {
    const { BUILD_STORE_ZIP_BYTES_MAX } = await import(
      '../src/features/exportPrep/streamingZipWriter'
    );
    const big = new Uint8Array(BUILD_STORE_ZIP_BYTES_MAX + 8);
    await expect(
      buildStoreZipBytes([{ path: 'huge.bin', getBytes: () => big }]),
    ).rejects.toMatchObject({ code: 'ZIP_TOTAL_TOO_LARGE' });
  });
});
