/**
 * Phase 1 corrections — native staged SHA-256 with strong native rehash (no weak reuse).
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { createHash } from 'node:crypto';

import { DigestCapabilityError, DigestIoError, digestAbsoluteFile } from '../src/features/exportPrep/digestAbsoluteFile';
import {
  classifyStagedDigestError,
  hashStagedFileSha256Detailed,
  hashStagedFileSha256Hex,
} from '../src/features/exportPrep/stagedSha256';
import {
  isConfirmedReadyIntegrityFailure,
  validateReadyStaging,
} from '../src/features/exportPrep/validateReadyStaging';

jest.mock('expo-file-system', () => {
  const actualFs = jest.requireActual('node:fs') as typeof import('node:fs');
  return {
    EncodingType: { UTF8: 'utf8', Base64: 'base64' },
    readAsStringAsync: jest.fn(async () => {
      throw new Error('Base64 full-file read must not be used for staged SHA');
    }),
    getInfoAsync: jest.fn(async (uri: string) => {
      const p = uri.startsWith('file://') ? decodeURIComponent(uri.slice(7)) : uri;
      if (!actualFs.existsSync(p)) return { exists: false };
      const st = actualFs.statSync(p);
      return {
        exists: true,
        size: st.size,
        modificationTime: Math.floor(st.mtimeMs / 1000),
      };
    }),
  };
});

jest.mock('../src/features/exportPrep/exportStaging', () => ({
  stagingFileExists: jest.fn(async (uri: string) => {
    const p = uri.startsWith('file://') ? decodeURIComponent(uri.slice(7)) : uri;
    return fs.existsSync(p);
  }),
}));

function writeFixture(bytes: Buffer, nameHint = 'bin'): { uri: string; abs: string; sha: string } {
  const abs = path.join(
    os.tmpdir(),
    `phase1-hash-${Date.now()}-${Math.random().toString(16).slice(2)}-${nameHint}`,
  );
  fs.writeFileSync(abs, bytes);
  const sha = createHash('sha256').update(bytes).digest('hex');
  return { uri: `file://${abs}`, abs, sha };
}

describe('phase1 native staged hash', () => {
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

  test('native digest matches independent sha256 of fixture', async () => {
    const payload = Buffer.from('phase1-andes-fixture-bytes-001');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const dig = await digestAbsoluteFile(fx.uri);
    expect(dig.sha256).toBe(fx.sha);
    expect(dig.size).toBe(payload.byteLength);
    const viaHelper = await hashStagedFileSha256Hex(fx.uri);
    expect(viaHelper).toBe(fx.sha);
    expect(viaHelper).toHaveLength(64);
    expect(viaHelper).toBe(viaHelper.toLowerCase());
  });

  test('hashStagedFileSha256Detailed reports native_file and bytesHashed', async () => {
    const payload = Buffer.from('phase1-detailed');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const r = await hashStagedFileSha256Detailed(fx.uri);
    expect(r.hashMode).toBe('native_file');
    expect(r.bytesHashed).toBe(payload.byteLength);
    expect(r.sha256).toBe(fx.sha);
  });

  test('does not call FileSystem.readAsStringAsync (no Base64 full file)', async () => {
    const FileSystem = jest.requireMock('expo-file-system') as {
      readAsStringAsync: jest.Mock;
    };
    FileSystem.readAsStringAsync.mockClear();
    const fx = writeFixture(Buffer.from('no-base64'));
    live.push(fx.abs);
    await hashStagedFileSha256Hex(fx.uri);
    expect(FileSystem.readAsStringAsync).not.toHaveBeenCalled();
  });

  test('two different files do not share digests', async () => {
    const a = writeFixture(Buffer.from('content-a'));
    const b = writeFixture(Buffer.from('content-b'));
    live.push(a.abs, b.abs);
    const ha = await hashStagedFileSha256Hex(a.uri);
    const hb = await hashStagedFileSha256Hex(b.uri);
    expect(ha).not.toBe(hb);
  });

  test('missing file fails as digest IO (not mismatch)', async () => {
    await expect(hashStagedFileSha256Hex('file:///tmp/phase1-missing-xyz.bin')).rejects.toBeTruthy();
    try {
      await hashStagedFileSha256Hex('file:///tmp/phase1-missing-xyz.bin');
    } catch (error) {
      const classified = classifyStagedDigestError(error);
      expect(classified.failure).toBe('STAGING_DIGEST_FAILED');
    }
  });

  test('file URI with plus sign preserves path and digests', async () => {
    const payload = Buffer.from('plus-path-bytes');
    const abs = path.join(os.tmpdir(), `item+A-${Date.now()}.bin`);
    fs.writeFileSync(abs, payload);
    live.push(abs);
    const uri = `file://${abs}`;
    expect(uri).toContain('+');
    const sha = await hashStagedFileSha256Hex(uri);
    expect(sha).toBe(createHash('sha256').update(payload).digest('hex'));
  });
});

describe('phase1 strong validation always rehashes', () => {
  const live: string[] = [];

  afterEach(() => {
    for (const p of live.splice(0)) {
      try {
        fs.unlinkSync(p);
      } catch {
        /* ignore */
      }
    }
    jest.restoreAllMocks();
  });

  function jobFor(fx: { uri: string; sha: string; abs: string }, size: number, readyAt: string | null) {
    return {
      staging_uri: fx.uri,
      export_file_name: 'photo_001.jpg',
      size_bytes: size,
      sha256: fx.sha,
      ready_at: readyAt,
    };
  }

  test('strong validation always uses native_file computed digest', async () => {
    const payload = Buffer.from('ready-rehash');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const readyAt = new Date(Date.now() + 5_000).toISOString();
    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength, readyAt),
      'strong',
    );
    expect(result.ok).toBe(true);
    expect(result.digest?.hashMode).toBe('native_file');
    expect(result.digest?.hashSource).toBe('computed');
    expect(result.digest?.bytesHashed).toBe(payload.byteLength);
    expect(result.digest?.reason).toBe('strong_native_rehash');
    expect(result.actualSha256).toBe(fx.sha);
  });

  test('same-size content swap is detected (never reused by size/mtime)', async () => {
    const original = Buffer.from('AAAA-same-size-content-01');
    const tampered = Buffer.from('BBBB-same-size-content-02');
    expect(original.byteLength).toBe(tampered.byteLength);
    const fx = writeFixture(original);
    live.push(fx.abs);
    const readyAt = new Date().toISOString();
    // Preserve mtime window: write tamper then restore mtime to before ready_at.
    const st = fs.statSync(fx.abs);
    fs.writeFileSync(fx.abs, tampered);
    fs.utimesSync(fx.abs, st.atime, st.mtime);

    const result = await validateReadyStaging(
      jobFor(fx, original.byteLength, readyAt),
      'strong',
    );
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_SHA_MISMATCH');
    expect(result.actualSha256).toBe(createHash('sha256').update(tampered).digest('hex'));
    expect(result.digest?.hashMode).toBe('native_file');
  });

  test('same-size swap within two seconds of ready_at still mismatches', async () => {
    const original = Buffer.alloc(32, 0x11);
    const tampered = Buffer.alloc(32, 0x22);
    const fx = writeFixture(original);
    live.push(fx.abs);
    const readyAt = new Date().toISOString();
    fs.writeFileSync(fx.abs, tampered);
    // mtime is now ≈ ready_at (within 2s skew of old heuristic)
    const result = await validateReadyStaging(
      jobFor(fx, original.byteLength, readyAt),
      'strong',
    );
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_SHA_MISMATCH');
  });

  test('legacy missing ready_at still native rehashes', async () => {
    const payload = Buffer.from('legacy-row');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const result = await validateReadyStaging(jobFor(fx, payload.byteLength, null), 'strong');
    expect(result.ok).toBe(true);
    expect(result.digest?.hashMode).toBe('native_file');
    expect(result.digest?.hashSource).toBe('computed');
    expect(result.digest?.bytesHashed).toBe(payload.byteLength);
  });

  test('size mismatch fails without accepting', async () => {
    const payload = Buffer.from('size-mismatch');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength + 10, new Date().toISOString()),
      'strong',
    );
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_SIZE_MISMATCH');
  });

  test('wrong persisted sha detected on rehash', async () => {
    const payload = Buffer.from('wrong-sha');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const result = await validateReadyStaging(
      {
        ...jobFor(fx, payload.byteLength, null),
        sha256: 'a'.repeat(64),
      },
      'strong',
    );
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_SHA_MISMATCH');
    expect(result.actualSha256).toBe(fx.sha);
    expect(isConfirmedReadyIntegrityFailure(result.failure)).toBe(true);
  });

  test('digest capability error does not report SHA mismatch', async () => {
    const payload = Buffer.from('cap-miss');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const digestMod = require('../src/features/exportPrep/digestAbsoluteFile') as typeof import('../src/features/exportPrep/digestAbsoluteFile');
    jest.spyOn(digestMod, 'digestAbsoluteFile').mockRejectedValueOnce(
      new DigestCapabilityError('digestFile unavailable'),
    );

    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength, new Date().toISOString()),
      'strong',
    );
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_DIGEST_UNAVAILABLE');
    expect(isConfirmedReadyIntegrityFailure(result.failure)).toBe(false);
  });

  test('digest IO error does not report SHA mismatch', async () => {
    const payload = Buffer.from('io-fail');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const digestMod = require('../src/features/exportPrep/digestAbsoluteFile') as typeof import('../src/features/exportPrep/digestAbsoluteFile');
    jest.spyOn(digestMod, 'digestAbsoluteFile').mockRejectedValueOnce(new DigestIoError('EIO'));

    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength, new Date().toISOString()),
      'strong',
    );
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_DIGEST_FAILED');
    expect(isConfirmedReadyIntegrityFailure(result.failure)).toBe(false);
  });

  test('light mode never digests', async () => {
    const payload = Buffer.from('light-only');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength, null),
      'light',
    );
    expect(result.ok).toBe(true);
    expect(result.digest).toBeUndefined();
  });

  test('classifyStagedDigestError maps capability vs io', () => {
    expect(classifyStagedDigestError(new DigestCapabilityError('x')).failure).toBe(
      'STAGING_DIGEST_UNAVAILABLE',
    );
    expect(classifyStagedDigestError(new DigestIoError('y')).failure).toBe(
      'STAGING_DIGEST_FAILED',
    );
    expect(
      classifyStagedDigestError(Object.assign(new Error('digestFile unavailable'), {
        code: 'DIGEST_UNAVAILABLE',
      })).failure,
    ).toBe('STAGING_DIGEST_UNAVAILABLE');
  });
});
