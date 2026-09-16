/**
 * Phase 5 — bounded-memory STORE ZIP writer.
 * Uses Node fs append sink; independent parser validates structure (not the writer).
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import { crc32Bytes, CRC32_VECTOR_123456789 } from '../src/features/exportPrep/crc32';
import {
  writeBoundedStoreZip,
  ZipWriteError,
  ZIP32_MAX_ENTRIES,
  type ZipWriteProgress,
} from '../src/features/exportPrep/boundedZipWriter';
import {
  parseStoreZipIndependent,
  validateLocalExportZipContract,
} from '../src/features/exportPrep/independentZipValidator';
import { sha256BytesHex } from '../src/core/payloadFingerprint';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  makeDirectoryAsync: jest.fn(async () => undefined),
  writeAsStringAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 1 })),
}));

function tmpZipPath(name: string): string {
  return path.join(os.tmpdir(), `p5-zip-${name}-${Date.now()}-${Math.random().toString(16).slice(2)}.zip`);
}

function enc(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

describe('crc32', () => {
  it('matches known vector CRC32("123456789")', () => {
    expect(crc32Bytes(enc('123456789'))).toBe(CRC32_VECTOR_123456789);
  });
});

describe('writeBoundedStoreZip', () => {
  const live: string[] = [];

  afterEach(() => {
    for (const p of live.splice(0)) {
      try {
        fs.unlinkSync(p);
      } catch {
        /* ignore */
      }
    }
  });

  async function write(
    entries: Parameters<typeof writeBoundedStoreZip>[0]['entries'],
    opts?: {
      signal?: AbortSignal;
      maxTotalBytes?: number;
      onProgress?: (p: ZipWriteProgress) => void;
    },
  ) {
    const target = tmpZipPath('w');
    live.push(target);
    const result = await writeBoundedStoreZip({
      targetUri: target,
      entries,
      ...(opts?.signal ? { signal: opts.signal } : {}),
      ...(opts?.maxTotalBytes != null ? { maxTotalBytes: opts.maxTotalBytes } : {}),
      ...(opts?.onProgress ? { onProgress: opts.onProgress } : {}),
    });
    const bytes = new Uint8Array(fs.readFileSync(target));
    return { result, bytes, target };
  }

  it('processes entries sequentially and never opens two at once', async () => {
    const order: string[] = [];
    let open = 0;
    let peak = 0;
    const { result, bytes } = await write([
      {
        path: 'results.csv',
        sizeBytes: 4,
        getBytes: async () => {
          open += 1;
          peak = Math.max(peak, open);
          order.push('csv');
          const b = enc('a,b\n');
          open -= 1;
          return b;
        },
      },
      {
        path: 'photos/0001_a.jpg',
        sizeBytes: 3,
        getBytes: async () => {
          open += 1;
          peak = Math.max(peak, open);
          order.push('p1');
          await Promise.resolve();
          const b = new Uint8Array([1, 2, 3]);
          open -= 1;
          return b;
        },
      },
      {
        path: 'photos/0002_b.jpg',
        sizeBytes: 2,
        getBytes: async () => {
          open += 1;
          peak = Math.max(peak, open);
          order.push('p2');
          const b = new Uint8Array([4, 5]);
          open -= 1;
          return b;
        },
      },
    ]);
    expect(order).toEqual(['csv', 'p1', 'p2']);
    expect(peak).toBe(1);
    expect(result.peakOpenEntries).toBe(1);
    expect(result.method).toBe('STORE');
    expect(bytes[0]).toBe(0x50);
    expect(bytes[1]).toBe(0x4b);
  });

  it('does not accumulate all photo bytes in the sink (disk size == written)', async () => {
    const photos = Array.from({ length: 10 }, (_, i) => {
      const data = new Uint8Array(1024);
      data.fill(i & 0xff);
      return {
        path: `photos/${String(i + 1).padStart(4, '0')}_p.jpg`,
        sizeBytes: data.byteLength,
        getBytes: () => data,
      };
    });
    const csv = enc('h\n');
    const manifest = enc('{"included_photo_count":10,"package_kind":"local_aisle_export"}\n');
    const { result, bytes } = await write([
      { path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv },
      { path: 'manifest.json', sizeBytes: manifest.byteLength, getBytes: () => manifest },
      ...photos,
    ]);
    expect(result.byteLength).toBe(bytes.byteLength);
    expect(result.peakOpenEntries).toBe(1);
    const parsed = validateLocalExportZipContract(bytes);
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.entryCount).toBe(12);
      for (let i = 0; i < 10; i += 1) {
        const e = parsed.entries.find((x) => x.path === photos[i]!.path);
        expect(e?.data).toEqual(photos[i]!.getBytes());
      }
    }
  });

  it('STORE preserves exact bytes and CRC matches independent parser', async () => {
    const payload = new Uint8Array([0xff, 0xd8, 0xff, 0xd9, 0x01, 0x02]);
    const { bytes } = await write([
      {
        path: 'photos/0001_x.jpg',
        sizeBytes: payload.byteLength,
        getBytes: () => payload,
      },
    ]);
    const parsed = parseStoreZipIndependent(bytes);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.entries[0]!.data).toEqual(payload);
    expect(parsed.entries[0]!.crc32).toBe(crc32Bytes(payload));
    expect(parsed.entries[0]!.method).toBe(0);
  });

  it('rejects empty entry', async () => {
    await expect(
      write([{ path: 'photos/e.jpg', sizeBytes: 0, getBytes: () => new Uint8Array(0) }]),
    ).rejects.toMatchObject({ code: 'ZIP_SOURCE_CHANGED' });
  });

  it('rejects size mismatch', async () => {
    await expect(
      write([{ path: 'photos/e.jpg', sizeBytes: 5, getBytes: () => new Uint8Array([1, 2]) }]),
    ).rejects.toMatchObject({ code: 'ZIP_SOURCE_CHANGED' });
  });

  it('rejects sha mismatch', async () => {
    const data = new Uint8Array([9, 9, 9]);
    await expect(
      write([
        {
          path: 'photos/e.jpg',
          sizeBytes: 3,
          expectedSha256: '00'.repeat(32),
          getBytes: () => data,
        },
      ]),
    ).rejects.toMatchObject({ code: 'ZIP_SOURCE_CHANGED' });
  });

  it('accepts matching sha256', async () => {
    const data = new Uint8Array([9, 9, 9]);
    const sha = sha256BytesHex(data);
    const { result } = await write([
      { path: 'photos/e.jpg', sizeBytes: 3, expectedSha256: sha, getBytes: () => data },
    ]);
    expect(result.entryCount).toBe(1);
  });

  it('rejects unsafe / invalid paths', async () => {
    await expect(
      write([{ path: '../x.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([1]) }]),
    ).rejects.toMatchObject({ code: 'ZIP_VALIDATION_FAILED' });
    await expect(
      write([{ path: '/abs.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([1]) }]),
    ).rejects.toMatchObject({ code: 'ZIP_VALIDATION_FAILED' });
  });

  it('rejects duplicate paths', async () => {
    await expect(
      write([
        { path: 'a.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([1]) },
        { path: 'a.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([2]) },
      ]),
    ).rejects.toMatchObject({ code: 'ZIP_VALIDATION_FAILED' });
  });

  it('cancels before start', async () => {
    const ac = new AbortController();
    ac.abort();
    await expect(
      write([{ path: 'a.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([1]) }], {
        signal: ac.signal,
      }),
    ).rejects.toMatchObject({ code: 'ZIP_CANCELLED' });
  });

  it('cancels between entries and leaves no published success path', async () => {
    const ac = new AbortController();
    let reads = 0;
    await expect(
      write(
        [
          {
            path: 'a.jpg',
            sizeBytes: 1,
            getBytes: () => {
              reads += 1;
              ac.abort();
              return new Uint8Array([1]);
            },
          },
          {
            path: 'b.jpg',
            sizeBytes: 1,
            getBytes: () => {
              reads += 1;
              return new Uint8Array([2]);
            },
          },
        ],
        { signal: ac.signal },
      ),
    ).rejects.toMatchObject({ code: 'ZIP_CANCELLED' });
    expect(reads).toBe(1);
  });

  it('cancels when signal aborts during getBytes (chunk boundary)', async () => {
    const ac = new AbortController();
    await expect(
      write(
        [
          {
            path: 'a.jpg',
            sizeBytes: 2,
            getBytes: async () => {
              ac.abort();
              return new Uint8Array([1, 2]);
            },
          },
          {
            path: 'b.jpg',
            sizeBytes: 1,
            getBytes: () => new Uint8Array([3]),
          },
        ],
        { signal: ac.signal },
      ),
    ).rejects.toMatchObject({ code: 'ZIP_CANCELLED' });
  });

  it('read failure cancels the package', async () => {
    await expect(
      write([
        {
          path: 'a.jpg',
          sizeBytes: 1,
          getBytes: async () => {
            throw new Error('disk gone');
          },
        },
      ]),
    ).rejects.toMatchObject({ code: 'ZIP_SOURCE_READ_FAILED' });
  });

  it('rejects ZIP_TOTAL_TOO_LARGE before writing', async () => {
    await expect(
      write([{ path: 'a.jpg', sizeBytes: 1000, getBytes: () => new Uint8Array(1000) }], {
        maxTotalBytes: 100,
      }),
    ).rejects.toMatchObject({ code: 'ZIP_TOTAL_TOO_LARGE' });
  });

  it('rejects too many entries (ZIP64 unsupported)', async () => {
    const many = Array.from({ length: ZIP32_MAX_ENTRIES + 1 }, (_, i) => ({
      path: `p/${i}.jpg`,
      sizeBytes: 1,
      getBytes: () => new Uint8Array([1]),
    }));
    await expect(write(many)).rejects.toMatchObject({ code: 'ZIP_TOO_MANY_ENTRIES' });
  });

  it('progress is monotonic and not 100% before VALIDATING', async () => {
    const stages: ZipWriteProgress['stage'][] = [];
    const completed: number[] = [];
    let sawValidating = false;
    let completedAtValidating = -1;
    await write(
      [
        { path: 'a.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([1]) },
        { path: 'b.jpg', sizeBytes: 1, getBytes: () => new Uint8Array([2]) },
      ],
      {
        onProgress: (p) => {
          stages.push(p.stage);
          completed.push(p.completedEntries);
          if (p.stage === 'VALIDATING') {
            sawValidating = true;
            completedAtValidating = p.completedEntries;
          }
          // Never claim "done writing" with validating incomplete — UI uses stages.
          if (p.stage === 'WRITING_ENTRIES') {
            expect(p.completedEntries).toBeLessThanOrEqual(p.totalEntries);
          }
        },
      },
    );
    expect(sawValidating).toBe(true);
    expect(completedAtValidating).toBe(2);
    for (let i = 1; i < completed.length; i += 1) {
      expect(completed[i]!).toBeGreaterThanOrEqual(completed[i - 1]!);
    }
    expect(stages).toContain('PREPARING');
    expect(stages).toContain('WRITING_DIRECTORY');
  });

  it('UTF-8 path round-trips', async () => {
    const name = 'photos/0001_café.jpg';
    const data = new Uint8Array([7]);
    const { bytes } = await write([{ path: name, sizeBytes: 1, getBytes: () => data }]);
    const parsed = parseStoreZipIndependent(bytes);
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.entries[0]!.path).toBe(name);
    }
  });

  it('golden: 1 / 10 / 100 synthetic photos validate independently', async () => {
    for (const n of [1, 10, 100] as const) {
      const csv = enc(`n=${n}\n`);
      const manifest = enc(
        JSON.stringify({
          included_photo_count: n,
          package_kind: 'local_aisle_export',
          schema_version: 1,
        }) + '\n',
      );
      const photos = Array.from({ length: n }, (_, i) => {
        const data = new Uint8Array((i % 17) + 1);
        data.fill((i * 3) & 0xff);
        return {
          path: `photos/${String(i + 1).padStart(4, '0')}_p.jpg`,
          sizeBytes: data.byteLength,
          expectedSha256: sha256BytesHex(data),
          getBytes: () => data,
        };
      });
      const started = Date.now();
      const { result, bytes } = await write([
        { path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv },
        { path: 'manifest.json', sizeBytes: manifest.byteLength, getBytes: () => manifest },
        ...photos,
      ]);
      const durationMs = Date.now() - started;
      expect(result.peakOpenEntries).toBe(1);
      expect(result.entryCount).toBe(n + 2);
      const parsed = validateLocalExportZipContract(bytes);
      expect(parsed.ok).toBe(true);
      // Instrumentation (not device RAM): sequential + peakOpen=1; duration recorded for n.
      expect(durationMs).toBeGreaterThanOrEqual(0);
      expect(result.byteLength).toBe(bytes.byteLength);
    }
  });

  it('failed write leaves tmp path for caller cleanup (sink closed)', async () => {
    const target = tmpZipPath('fail');
    live.push(target);
    await expect(
      writeBoundedStoreZip({
        targetUri: target,
        entries: [
          {
            path: 'a.jpg',
            sizeBytes: 1,
            getBytes: async () => {
              throw new Error('boom');
            },
          },
        ],
      }),
    ).rejects.toBeInstanceOf(ZipWriteError);
    // File may exist as partial — must not be treated as valid package.
    if (fs.existsSync(target)) {
      const partial = new Uint8Array(fs.readFileSync(target));
      const parsed = parseStoreZipIndependent(partial);
      expect(parsed.ok).toBe(false);
    }
  });
});
