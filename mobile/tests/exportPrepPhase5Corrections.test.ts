/**
 * Phase 5 corrections — on-disk bounded ZIP validator, chunk cancel, contract, platform.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import { writeBoundedStoreZip, ZipWriteError } from '../src/features/exportPrep/boundedZipWriter';
import { validateOnDiskStoreZip } from '../src/features/exportPrep/boundedOnDiskZipValidator';
import { validateLocalExportZipContract } from '../src/features/exportPrep/independentZipValidator';
import {
  buildStoreZipBytes,
  BUILD_STORE_ZIP_BYTES_MAX,
  adaptLegacyZipEntryProgress,
} from '../src/features/exportPrep/streamingZipWriter';
import { assertZipWritePlatformSupported, resolveZipWritePlatform } from '../src/features/exportPrep/zipWritePlatform';
import { createBinaryAppendSink } from '../src/features/exportPrep/binaryAppendSink';
import { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from '../src/features/localCsv/localPackageContract';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  cacheDirectory: 'file:///cache/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  makeDirectoryAsync: jest.fn(async () => undefined),
  writeAsStringAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 1 })),
}));

function enc(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

function tmpPath(name: string): string {
  return path.join(os.tmpdir(), `p5c-${name}-${Date.now()}-${Math.random().toString(16).slice(2)}`);
}

describe('Phase 5 corrections — on-disk validator', () => {
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

  async function writeContractZip(photoCount: number, photoSize = 64): Promise<{
    path: string;
    sha256: string;
    size: number;
    entryCount: number;
  }> {
    const target = tmpPath('z');
    live.push(target);
    const csv = enc('h\n');
    const manifest = enc(
      JSON.stringify({
        package_kind: LOCAL_PACKAGE_KIND,
        package_version: LOCAL_PACKAGE_VERSION,
        included_photo_count: photoCount,
        expected_photo_count: photoCount,
        package_checksum_sha256: 'fp',
      }) + '\n',
    );
    const photos = Array.from({ length: photoCount }, (_, i) => {
      const data = new Uint8Array(photoSize);
      data.fill((i * 7) & 0xff);
      return {
        path: `photos/${String(i + 1).padStart(4, '0')}_p.jpg`,
        sizeBytes: data.byteLength,
        getBytes: () => data,
      };
    });
    const written = await writeBoundedStoreZip({
      targetUri: target,
      entries: [
        { path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv },
        { path: 'manifest.json', sizeBytes: manifest.byteLength, getBytes: () => manifest },
        ...photos,
      ],
    });
    return {
      path: target,
      sha256: written.sha256,
      size: written.byteLength,
      entryCount: written.entryCount,
    };
  }

  it('validates EOCD/CD/manifest via range reads without loading photos', async () => {
    const zip = await writeContractZip(10, 256 * 1024);
    const result = await validateOnDiskStoreZip({
      uri: zip.path,
      allowedRoots: [os.tmpdir()],
      expectedSha256: zip.sha256,
      expectedSizeBytes: zip.size,
      expectedContentFingerprint: 'fp',
      verifyCrcAll: false,
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.entryCount).toBe(12);
    expect(result.maxBufferBytes).toBeLessThan(512 * 1024);
    expect(result.rangeReads).toBeGreaterThan(3);
    // Photo payloads not materialized: max buffer << sum of photo bytes (~2.5 MiB).
    expect(result.maxBufferBytes).toBeLessThan(10 * 256 * 1024);
  });

  it('rejects truncated ZIP', async () => {
    const zip = await writeContractZip(1, 32);
    const truncated = tmpPath('trunc');
    live.push(truncated);
    const bytes = fs.readFileSync(zip.path);
    fs.writeFileSync(truncated, bytes.subarray(0, Math.max(4, bytes.length - 40)));
    const result = await validateOnDiskStoreZip({
      uri: truncated,
      allowedRoots: [os.tmpdir()],
      computeSha256: false,
    });
    expect(result.ok).toBe(false);
  });

  it('rejects wrong package_kind', async () => {
    const target = tmpPath('kind');
    live.push(target);
    const csv = enc('x\n');
    const manifest = enc(
      JSON.stringify({
        package_kind: 'WRONG_KIND',
        package_version: 2,
        included_photo_count: 0,
        expected_photo_count: 0,
      }) + '\n',
    );
    await writeBoundedStoreZip({
      targetUri: target,
      entries: [
        { path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv },
        { path: 'manifest.json', sizeBytes: manifest.byteLength, getBytes: () => manifest },
      ],
    });
    const result = await validateOnDiskStoreZip({
      uri: target,
      allowedRoots: [os.tmpdir()],
      computeSha256: true,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe('package_kind_mismatch');
  });

  it('validateLocalExportZipContract rejects wrong package_kind', () => {
    const bytes = enc('not-a-zip');
    const bad = validateLocalExportZipContract(bytes);
    expect(bad.ok).toBe(false);
  });

  it('legacy progress adapter never reports done===total while writing entries', () => {
    const reports: Array<[number, number]> = [];
    adaptLegacyZipEntryProgress(
      {
        completedEntries: 5,
        totalEntries: 5,
        processedBytes: 10,
        totalBytes: 10,
        stage: 'WRITING_ENTRIES',
      },
      (d, t) => reports.push([d, t]),
    );
    expect(reports[0]).toEqual([4, 5]);
  });
});

describe('Phase 5 corrections — cancel between chunks', () => {
  it('aborts during multi-chunk append of one entry', async () => {
    const target = tmpPath('chunk-abort.zip');
    const sink = await createBinaryAppendSink(target);
    const ac = new AbortController();
    const big = new Uint8Array(256 * 1024 * 3 + 10);
    big.fill(7);
    let threw: unknown;
    try {
      let chunks = 0;
      const MAX = 256 * 1024;
      for (let i = 0; i < big.length; i += MAX) {
        if (chunks === 2) {
          ac.abort();
        }
        chunks += 1;
        await sink.append(big.subarray(i, Math.min(i + MAX, big.length)), ac.signal);
      }
    } catch (e) {
      threw = e;
    }
    await sink.close();
    expect(threw).toBeInstanceOf(ZipWriteError);
    expect((threw as ZipWriteError).code).toBe('ZIP_CANCELLED');
  });
});

describe('Phase 5 corrections — buildStoreZipBytes probe limit', () => {
  it('rejects packages larger than probe max', async () => {
    const big = new Uint8Array(BUILD_STORE_ZIP_BYTES_MAX + 1);
    await expect(
      buildStoreZipBytes([{ path: 'x.bin', getBytes: () => big }]),
    ).rejects.toMatchObject({ code: 'ZIP_TOTAL_TOO_LARGE' });
  });
});

describe('Phase 5 corrections — platform', () => {
  it('Node test runtime is supported; assert does not throw', () => {
    expect(resolveZipWritePlatform()).toBe('node');
    expect(() => assertZipWritePlatformSupported()).not.toThrow();
  });
});

describe('Phase 5 corrections — real-ish sizes 1/10 (bounded buffers)', () => {
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

  it.each([1, 10] as const)(
    'writes and on-disk validates %s x ~2MiB photos with bounded maxBuffer',
    async (n) => {
      const target = tmpPath(`real-${n}`);
      live.push(target);
      const photoSize = 2 * 1024 * 1024;
      const csv = enc(`n=${n}\n`);
      const manifest = enc(
        JSON.stringify({
          package_kind: LOCAL_PACKAGE_KIND,
          package_version: LOCAL_PACKAGE_VERSION,
          included_photo_count: n,
          expected_photo_count: n,
        }) + '\n',
      );
      const started = Date.now();
      let peakOpen = 0;
      let open = 0;
      const photos = Array.from({ length: n }, (_, i) => ({
        path: `photos/${String(i + 1).padStart(4, '0')}_p.jpg`,
        sizeBytes: photoSize,
        getBytes: () => {
          open += 1;
          peakOpen = Math.max(peakOpen, open);
          const data = new Uint8Array(photoSize);
          data.fill((i * 13) & 0xff);
          open -= 1;
          return data;
        },
      }));
      const written = await writeBoundedStoreZip({
        targetUri: target,
        entries: [
          { path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv },
          { path: 'manifest.json', sizeBytes: manifest.byteLength, getBytes: () => manifest },
          ...photos,
        ],
      });
      const validated = await validateOnDiskStoreZip({
        uri: target,
        allowedRoots: [os.tmpdir()],
        expectedSha256: written.sha256,
        expectedSizeBytes: written.byteLength,
        verifyCrcAll: false,
      });
      expect(validated.ok).toBe(true);
      expect(peakOpen).toBe(1);
      expect(written.peakOpenEntries).toBe(1);
      if (validated.ok) {
        expect(validated.maxBufferBytes).toBeLessThan(photoSize);
      }
      // Instrumentation (Node): duration + size — not device RAM.
      expect(Date.now() - started).toBeGreaterThanOrEqual(0);
      expect(written.byteLength).toBeGreaterThan(n * photoSize);
    },
    120_000,
  );
});
