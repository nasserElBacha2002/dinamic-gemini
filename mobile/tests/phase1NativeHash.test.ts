/**
 * Phase 1 — native staged SHA-256 + strong-validation reuse.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { createHash } from 'node:crypto';

import { digestAbsoluteFile } from '../src/features/exportPrep/digestAbsoluteFile';
import {
  hashStagedFileSha256Detailed,
  hashStagedFileSha256Hex,
} from '../src/features/exportPrep/stagedSha256';
import { validateReadyStaging } from '../src/features/exportPrep/validateReadyStaging';

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

function writeFixture(bytes: Buffer): { uri: string; abs: string; sha: string } {
  const abs = path.join(
    os.tmpdir(),
    `phase1-hash-${Date.now()}-${Math.random().toString(16).slice(2)}.bin`,
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

  test('missing file fails', async () => {
    await expect(hashStagedFileSha256Hex('file:///tmp/phase1-missing-xyz.bin')).rejects.toBeTruthy();
  });
});

describe('phase1 strong validation reuse', () => {
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

  function jobFor(fx: { uri: string; sha: string; abs: string }, size: number, readyAt: string | null) {
    return {
      staging_uri: fx.uri,
      export_file_name: 'photo_001.jpg',
      size_bytes: size,
      sha256: fx.sha,
      ready_at: readyAt,
    };
  }

  test('reuses persisted sha when ready identity matches', async () => {
    const payload = Buffer.from('ready-reuse');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const readyAt = new Date(Date.now() + 5_000).toISOString(); // after mtime
    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength, readyAt),
      'strong',
    );
    expect(result.ok).toBe(true);
    expect(result.digest?.hashMode).toBe('reused_persisted');
    expect(result.digest?.hashSource).toBe('staging_ready');
    expect(result.digest?.bytesHashed).toBe(0);
    expect(result.actualSha256).toBe(fx.sha);
  });

  test('legacy missing ready_at forces native fallback', async () => {
    const payload = Buffer.from('legacy-row');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const result = await validateReadyStaging(jobFor(fx, payload.byteLength, null), 'strong');
    expect(result.ok).toBe(true);
    expect(result.digest?.hashMode).toBe('native_file');
    expect(result.digest?.hashSource).toBe('validation_fallback');
    expect(result.digest?.bytesHashed).toBe(payload.byteLength);
    expect(result.digest?.reason).toBe('legacy_missing_ready_at');
  });

  test('forceRehash computes native digest', async () => {
    const payload = Buffer.from('force-rehash');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const readyAt = new Date(Date.now() + 5_000).toISOString();
    const result = await validateReadyStaging(
      jobFor(fx, payload.byteLength, readyAt),
      'strong',
      { forceRehash: true },
    );
    expect(result.ok).toBe(true);
    expect(result.digest?.hashMode).toBe('native_file');
    expect(result.digest?.reason).toBe('force_rehash');
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

  test('wrong persisted sha detected on forced rehash', async () => {
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
  });

  test('mtime newer than ready_at forces rehash', async () => {
    const payload = Buffer.from('mtime-newer');
    const fx = writeFixture(payload);
    live.push(fx.abs);
    const readyAt = new Date(Date.now() - 60_000).toISOString(); // ready in the past
    // Touch file so mtime is now
    const now = new Date();
    fs.utimesSync(fx.abs, now, now);
    const result = await validateReadyStaging(jobFor(fx, payload.byteLength, readyAt), 'strong');
    expect(result.ok).toBe(true);
    expect(result.digest?.hashMode).toBe('native_file');
    expect(result.digest?.reason).toBe('staging_mtime_newer_than_ready_at');
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
});
