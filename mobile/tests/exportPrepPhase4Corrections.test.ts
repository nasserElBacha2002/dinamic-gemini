/**
 * Phase 4 corrections: safe drain coalescing, fingerprint, package reuse, ZIP names, policy.
 */

import * as FileSystem from 'expo-file-system';

import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import { ExportPrepRepository } from '../src/database/repositories/exportPrepRepository';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';
import { buildPackageContentFingerprint } from '../src/features/exportPrep/packageFingerprint';
import { classifySessionExportPolicy } from '../src/features/exportPrep/sessionExportPolicy';
import { assertSafeExportFileName } from '../src/features/exportPrep/validateExportFileName';
import { validateExistingExportPackage } from '../src/features/exportPrep/existingPackageValidator';
import { exportPhotoFileName } from '../src/features/exportPrep/exportPhotoFileName';
import type { CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { LocalCsvExportRow } from '../src/database/repositories/localCsvExportRepository';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 12 })),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(async () => 'c'.repeat(64)),
}));

const SHA = 'a'.repeat(64);

function session(overrides: Partial<CaptureSessionRow> = {}): CaptureSessionRow {
  const now = '2026-01-01T00:00:00Z';
  return {
    id: 's1',
    inventory_id: 'inv',
    inventory_name: 'Inv',
    aisle_id: 'a1',
    aisle_name: 'A1',
    status: 'review',
    started_at: now,
    finished_at: now,
    initial_asset_id: null,
    initial_date_added: null,
    initial_date_modified: null,
    initial_display_name: null,
    initial_size: null,
    initial_bucket_id: null,
    scan_cursor_date_added: EMPTY_CURSOR.dateAdded,
    scan_cursor_asset_id: EMPTY_CURSOR.assetId,
    last_valid_cursor_date_added: EMPTY_CURSOR.dateAdded,
    last_valid_cursor_asset_id: EMPTY_CURSOR.assetId,
    upload_batch_id: null,
    upload_status: 'idle',
    processing_status: 'idle',
    backend_job_id: null,
    upload_started_at: null,
    upload_completed_at: null,
    processing_started_at: null,
    processing_finished_at: null,
    last_upload_error: null,
    last_processing_error: null,
    preparation_processing_mode: 'CODE_SCAN',
    backend_ordered_capture_session_id: null,
    process_attempt_id: null,
    process_idempotency_key: null,
    process_requested_at: null,
    process_confirmed_at: null,
    last_recovery_check_at: null,
    capture_frozen_at: now,
    capture_frozen_photo_count: 1,
    capture_freeze_generation: 1,
    active_freeze_id: 'f1',
    export_packaging_mode: 'STAGING_REQUIRED',
    upload_policy: null,
    active_position_json: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function baseDescriptor(overrides: Record<string, unknown> = {}) {
  return {
    capturePhotoId: 'p1',
    sequenceNumber: 1,
    fileName: '0001_p1.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 10,
    sha256: SHA,
    assetVariant: 'PREPARED' as const,
    ...overrides,
  };
}

describe('Phase 4 corrections — drain coalescing', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  function memoryDb() {
    const rows = new Map<string, Record<string, unknown>>();
    const db = {
      execAsync: async () => undefined,
      getFirstAsync: async <T,>(sql: string, ...p: unknown[]): Promise<T | null> => {
        if (sql.includes('WHERE capture_photo_id = ?')) {
          return (rows.get(String(p[0])) as T) ?? null;
        }
        return null;
      },
      getAllAsync: async <T,>(sql: string, ...p: unknown[]): Promise<T[]> => {
        if (sql.includes('GROUP BY status')) {
          const sid = String(p[0]);
          const counts = new Map<string, number>();
          for (const r of rows.values()) {
            if (r.capture_session_id !== sid) continue;
            counts.set(String(r.status), (counts.get(String(r.status)) ?? 0) + 1);
          }
          return [...counts.entries()].map(([status, c]) => ({ status, c }) as T);
        }
        if (sql.includes('WHERE capture_session_id = ?')) {
          return [...rows.values()].filter((r) => r.capture_session_id === String(p[0])) as T[];
        }
        return [];
      },
      runAsync: async () => ({ changes: 0, lastInsertRowId: 0 }),
    };
    return { db, rows };
  }

  function makeQueue(captureRepo: {
    getSession: jest.Mock;
    listPhotos: jest.Mock;
    listFreezePhotos?: jest.Mock;
  }) {
    const { db } = memoryDb();
    const queue = new ExportPrepQueue({
      prepRepo: new ExportPrepRepository(db as never),
      captureRepo: {
        ...captureRepo,
        getPhotoById: async () => null,
        listFreezePhotos: captureRepo.listFreezePhotos ?? (async () => []),
      } as never,
      draftRepo: { listForSession: async () => [] } as never,
      localCodeScan: null,
      localCodeScanEnabled: false,
      logger: null,
    });
    return { queue };
  }

  it('1+2. barrier true caller does not grant exportable to barrier false (both orders)', async () => {
    const captureRepo = {
      getSession: jest.fn(async () => session()),
      listPhotos: jest.fn(async () => []),
      listFreezePhotos: jest.fn(async () => []),
    };
    const { queue } = makeQueue(captureRepo);

    const runPair = async (order: 'true-first' | 'false-first') => {
      const optsTrue = {
        reason: 'FINISH' as const,
        producerBarrierCompleted: true,
        expectedFreezeId: 'f1',
        expectedFreezeGeneration: 1,
        allowLegacyWithoutFreeze: false,
        timeoutMs: 200,
        pollMs: 20,
      };
      const optsFalse = {
        ...optsTrue,
        producerBarrierCompleted: false,
      };
      const first =
        order === 'true-first'
          ? queue.waitUntilExportable('s1', optsTrue)
          : queue.waitUntilExportable('s1', optsFalse);
      const second =
        order === 'true-first'
          ? queue.waitUntilExportable('s1', optsFalse)
          : queue.waitUntilExportable('s1', optsTrue);
      return Promise.all([first, second]);
    };

    const [a, b] = await runPair('true-first');
    const trueRes = a.producerBarrierCompleted ? a : b;
    const falseRes = a.producerBarrierCompleted ? b : a;
    expect(falseRes.exportable).toBe(false);
    expect(falseRes.producerBarrierCompleted).toBe(false);
    expect(trueRes.producerBarrierCompleted).toBe(true);

    const [c, d] = await runPair('false-first');
    const trueRes2 = c.producerBarrierCompleted ? c : d;
    const falseRes2 = c.producerBarrierCompleted ? d : c;
    expect(falseRes2.exportable).toBe(false);
    expect(trueRes2.producerBarrierCompleted).toBe(true);
    queue.stop();
  });

  it('3. legacy allowed vs prohibited do not share drain work', async () => {
    const captureRepo = {
      getSession: jest.fn(async () =>
        session({
          active_freeze_id: null,
          capture_freeze_generation: 0,
          capture_frozen_at: null,
          export_packaging_mode: null,
        }),
      ),
      listPhotos: jest.fn(async () => []),
      listFreezePhotos: jest.fn(async () => []),
    };
    const { queue } = makeQueue(captureRepo);
    const [legacy, modern] = await Promise.all([
      queue.waitUntilExportable('s1', {
        producerBarrierCompleted: true,
        allowLegacyWithoutFreeze: true,
        timeoutMs: 200,
        pollMs: 20,
      }),
      queue.waitUntilExportable('s1', {
        producerBarrierCompleted: true,
        allowLegacyWithoutFreeze: false,
        timeoutMs: 200,
        pollMs: 20,
      }),
    ]);
    expect(modern.structuralError).toBe('FREEZE_MISSING');
    expect(modern.exportable).toBe(false);
    expect(legacy.structuralError).toBeNull();
    queue.stop();
  });

  it('6. SQLite/database exception maps to DATABASE_ERROR not SESSION_MISSING', async () => {
    const captureRepo = {
      getSession: jest.fn(async () => {
        throw new Error('SQLITE_ERROR: database is locked');
      }),
      listPhotos: jest.fn(async () => []),
      listFreezePhotos: jest.fn(async () => []),
    };
    const { queue } = makeQueue(captureRepo);
    const result = await queue.waitUntilExportable('s1', {
      producerBarrierCompleted: true,
      expectedFreezeId: 'f1',
      expectedFreezeGeneration: 1,
      timeoutMs: 200,
      pollMs: 20,
    });
    expect(result.structuralError).toBe('DATABASE_ERROR');
    expect(result.structuralError).not.toBe('SESSION_MISSING');
    expect(result.exportable).toBe(false);
    queue.stop();
  });
});

describe('Phase 4 corrections — session policy', () => {
  it('4. modern staging session without freeze → freezeRequired', () => {
    const c = classifySessionExportPolicy(
      session({
        active_freeze_id: null,
        capture_frozen_at: null,
        capture_freeze_generation: 0,
        export_packaging_mode: 'STAGING_REQUIRED',
      }),
      true,
    );
    expect(c.freezeRequired).toBe(true);
    expect(c.allowLegacyWithoutFreeze).toBe(false);
  });

  it('5. historical LEGACY_ORIGINALS → LEGACY_SESSION_WITHOUT_PREP', () => {
    const c = classifySessionExportPolicy(
      session({
        active_freeze_id: null,
        capture_frozen_at: null,
        capture_freeze_generation: 0,
        export_packaging_mode: 'LEGACY_ORIGINALS',
      }),
      true,
    );
    expect(c.allowLegacyWithoutFreeze).toBe(true);
    expect(c.fallbackReason).toBe('LEGACY_SESSION_WITHOUT_PREP');
  });
});

describe('Phase 4 corrections — fingerprint', () => {
  it('7-9. fingerprint changes with fileName, sequence, MIME, hash, set, freeze, generation', async () => {
    const base = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor()],
    });
    const byName = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor({ fileName: '0001_other.jpg' })],
    });
    const bySeq = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor({ sequenceNumber: 2 })],
    });
    const byMime = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor({ mimeType: 'image/png' })],
    });
    const byHash = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor({ sha256: 'b'.repeat(64) })],
    });
    const bySet = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor(), baseDescriptor({ capturePhotoId: 'p2', sequenceNumber: 2 })],
    });
    const byFreeze = await buildPackageContentFingerprint({
      freezeId: 'f2',
      freezeGeneration: 1,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor()],
    });
    const byGen = await buildPackageContentFingerprint({
      freezeId: 'f1',
      freezeGeneration: 2,
      csvChecksumSha256: SHA,
      photos: [baseDescriptor()],
    });
    expect(byName).not.toBe(base);
    expect(bySeq).not.toBe(base);
    expect(byMime).not.toBe(base);
    expect(byHash).not.toBe(base);
    expect(bySet).not.toBe(base);
    expect(byFreeze).not.toBe(base);
    expect(byGen).not.toBe(base);
  });
});

describe('Phase 4 corrections — ZIP names', () => {
  it('13. name with ../ is rejected', () => {
    expect(() => assertSafeExportFileName('../x.jpg', 'p1', 1, 'x.jpg')).toThrow(
      /inseguro|PACKAGE_VALIDATION/,
    );
  });

  it('14. slash/backslash rejected', () => {
    expect(() => assertSafeExportFileName('a/b.jpg', 'p1', 1, 'b.jpg')).toThrow();
    expect(() => assertSafeExportFileName('a\\b.jpg', 'p1', 1, 'b.jpg')).toThrow();
  });

  it('deterministic match required', () => {
    const expected = exportPhotoFileName('p1', 1, 'photo.jpg');
    expect(() => assertSafeExportFileName(expected, 'p1', 1, 'photo.jpg')).not.toThrow();
    expect(() => assertSafeExportFileName('0001_wrong.jpg', 'p1', 1, 'photo.jpg')).toThrow(
      /determinista/,
    );
  });
});

describe('Phase 4 corrections — package reuse validation', () => {
  const fingerprint = 'fp-expected';
  const live: string[] = [];

  afterEach(() => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require('fs') as typeof import('fs');
    for (const p of live.splice(0)) {
      try {
        fs.unlinkSync(p);
      } catch {
        /* ignore */
      }
    }
  });

  function row(overrides: Partial<LocalCsvExportRow> = {}): LocalCsvExportRow {
    return {
      id: 'r1',
      export_id: 'e1',
      schema_version: '1.1',
      scope: 'session',
      capture_session_id: 's1',
      inventory_id: 'inv',
      aisle_id: 'a1',
      row_count: 1,
      checksum_sha256: SHA,
      content_fingerprint: fingerprint,
      file_uri: 'file:///docs/e1.csv',
      freeze_id: 'f1',
      zip_size_bytes: null,
      zip_sha256: null,
      package_checksum_sha256: fingerprint,
      exported_at: '2026-01-01T00:00:00Z',
      shared_at: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      ...overrides,
    };
  }

  it('10. non-empty corrupt ZIP is not reused', async () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require('fs') as typeof import('fs');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const os = require('os') as typeof import('os');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const path = require('path') as typeof import('path');
    const zipPath = path.join(os.tmpdir(), `corrupt-${Date.now()}.zip`);
    live.push(zipPath);
    fs.writeFileSync(zipPath, Buffer.from('PK\x03\x04not-a-real-zip-but-nonempty'));
    (FileSystem.getInfoAsync as jest.Mock).mockImplementation(async (uri: string) => {
      if (String(uri).endsWith('.csv')) return { exists: true, size: 20 };
      if (String(uri) === zipPath || String(uri).endsWith('.zip')) {
        return { exists: true, size: fs.statSync(zipPath).size };
      }
      return { exists: false };
    });
    const result = await validateExistingExportPackage({
      row: row(),
      expectedContentFingerprint: fingerprint,
      zipUri: zipPath,
    });
    expect(result.ok).toBe(false);
  });

  it('11. incorrect zip_sha256 rejects reuse', async () => {
    const { writeBoundedStoreZip } = await import('../src/features/exportPrep/boundedZipWriter');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require('fs') as typeof import('fs');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const os = require('os') as typeof import('os');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const path = require('path') as typeof import('path');
    const zipPath = path.join(os.tmpdir(), `sha-mismatch-${Date.now()}.zip`);
    live.push(zipPath);
    const csv = new TextEncoder().encode('a,b\n');
    const manifest = new TextEncoder().encode(
      JSON.stringify({
        package_kind: 'DINAMIC_LOCAL_AISLE_EXPORT',
        package_version: 2,
        package_checksum_sha256: fingerprint,
        included_photo_count: 0,
        expected_photo_count: 0,
      }) + '\n',
    );
    const written = await writeBoundedStoreZip({
      targetUri: zipPath,
      entries: [
        { path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv },
        { path: 'manifest.json', sizeBytes: manifest.byteLength, getBytes: () => manifest },
      ],
    });
    (FileSystem.getInfoAsync as jest.Mock).mockImplementation(async (uri: string) => {
      if (String(uri).endsWith('.csv')) return { exists: true, size: 10 };
      return { exists: true, size: written.byteLength };
    });
    const result = await validateExistingExportPackage({
      row: row({ zip_sha256: '0'.repeat(64), zip_size_bytes: written.byteLength }),
      expectedContentFingerprint: fingerprint,
      zipUri: zipPath,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe('zip_sha_mismatch');
    expect(fs.existsSync(zipPath)).toBe(true);
  });

  it('12. missing manifest rejects reuse', async () => {
    const { writeBoundedStoreZip } = await import('../src/features/exportPrep/boundedZipWriter');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const os = require('os') as typeof import('os');
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const path = require('path') as typeof import('path');
    const zipPath = path.join(os.tmpdir(), `no-manifest-${Date.now()}.zip`);
    live.push(zipPath);
    const csv = new TextEncoder().encode('a,b\n');
    const written = await writeBoundedStoreZip({
      targetUri: zipPath,
      entries: [{ path: 'results.csv', sizeBytes: csv.byteLength, getBytes: () => csv }],
    });
    (FileSystem.getInfoAsync as jest.Mock).mockImplementation(async (uri: string) => {
      if (String(uri).endsWith('.csv')) return { exists: true, size: 10 };
      return { exists: true, size: written.byteLength };
    });
    const result = await validateExistingExportPackage({
      row: row({ zip_size_bytes: written.byteLength, zip_sha256: written.sha256 }),
      expectedContentFingerprint: fingerprint,
      zipUri: zipPath,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/missing_manifest/);
  });
});
