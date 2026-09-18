/**
 * Phase 2 — direct indexed draft lookup (real SQLite).
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { MIGRATIONS } from '../src/database/migrations/migrations';
import {
  DraftLookupError,
  LocalDetectionDraftRepository,
} from '../src/database/repositories/localDetectionDraftRepository';
import { __resetSqliteWriteGateForTests } from '../src/database/sqliteWriteGate';

type AsyncDb = {
  execAsync: (sql: string) => Promise<void>;
  runAsync: (sql: string, ...params: unknown[]) => Promise<{ changes: number }>;
  getFirstAsync: <T>(sql: string, ...params: unknown[]) => Promise<T | null>;
  getAllAsync: <T>(sql: string, ...params: unknown[]) => Promise<T[]>;
};

function openTempDb(): { sync: DatabaseSync; db: AsyncDb; file: string } {
  const file = path.join(
    os.tmpdir(),
    `phase2-draft-lookup-${Date.now()}-${Math.random().toString(16).slice(2)}.sqlite`,
  );
  const sync = new DatabaseSync(file);
  sync.exec('PRAGMA foreign_keys = ON;');
  const db: AsyncDb = {
    execAsync: async (sql) => {
      sync.exec(sql);
    },
    runAsync: async (sql, ...params) => {
      const result = sync.prepare(sql).run(...(params as never[]));
      return { changes: Number(result.changes ?? 0) };
    },
    getFirstAsync: async <T,>(sql: string, ...params: unknown[]) => {
      const row = sync.prepare(sql).get(...(params as never[]));
      return (row as T) ?? null;
    },
    getAllAsync: async <T,>(sql: string, ...params: unknown[]) => {
      return sync.prepare(sql).all(...(params as never[])) as T[];
    },
  };
  return { sync, db, file };
}

function applyAllMigrations(sync: DatabaseSync): void {
  for (const m of MIGRATIONS) {
    sync.exec(m.sql);
    sync.prepare(
      `INSERT OR REPLACE INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?);`,
    ).run(m.version, m.name, new Date().toISOString());
  }
}

function ensureSchemaMigrationsTable(sync: DatabaseSync): void {
  sync.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY NOT NULL,
      name TEXT NOT NULL,
      applied_at TEXT NOT NULL
    );
  `);
}

describe('phase2 direct indexed draft lookup', () => {
  const files: string[] = [];

  afterEach(() => {
    __resetSqliteWriteGateForTests();
    for (const f of files.splice(0)) {
      try {
        fs.unlinkSync(f);
      } catch {
        /* ignore */
      }
    }
  });

  async function seededRepo(): Promise<{
    repo: LocalDetectionDraftRepository;
    sync: DatabaseSync;
    file: string;
  }> {
    const { sync, db, file } = openTempDb();
    files.push(file);
    ensureSchemaMigrationsTable(sync);
    applyAllMigrations(sync);
    // Minimal parent rows for FK
    const now = new Date().toISOString();
    for (const sessionId of ['sess-a', 'sess-b'] as const) {
      sync.prepare(
        `INSERT INTO capture_sessions (
           id, inventory_id, inventory_name, aisle_id, aisle_name, status,
           started_at, scan_cursor_date_added, scan_cursor_asset_id,
           last_valid_cursor_date_added, last_valid_cursor_asset_id,
           created_at, updated_at
         ) VALUES (?, 'inv', 'Inv', 'aisle', 'A1', 'ACTIVE', ?, 0, '', 0, '', ?, ?);`,
      ).run(sessionId, now, now, now);
    }
    for (const [id, session] of [
      ['photo-1', 'sess-a'],
      ['photo-2', 'sess-a'],
      ['photo-other', 'sess-b'],
    ] as const) {
      sync.prepare(
        `INSERT INTO capture_photos (
           id, capture_session_id, asset_id, uri, display_name, mime_type,
           size, width, height, date_added, date_modified, status,
           created_at, updated_at
         ) VALUES (?, ?, ?, ?, ?, 'image/jpeg', 10, 1, 1, 0, 0, 'CAPTURED', ?, ?);`,
      ).run(id, session, `asset-${id}`, `file:///tmp/${id}.jpg`, `${id}.jpg`, now, now);
    }
    const repo = new LocalDetectionDraftRepository(db as never);
    return { repo, sync, file };
  }

  test('getBySessionAndPhotoId returns the correct draft', async () => {
    const { repo } = await seededRepo();
    await repo.upsertDraft({
      capturePhotoId: 'photo-1',
      captureSessionId: 'sess-a',
      clientFileId: null,
      status: 'RESOLVED',
      parserVersion: 'p1',
      detectorVersion: 'd1',
      preparedAssetFingerprint: 'fp1',
    });
    await repo.upsertDraft({
      capturePhotoId: 'photo-2',
      captureSessionId: 'sess-a',
      clientFileId: null,
      status: 'RESOLVED',
      parserVersion: 'p1',
      detectorVersion: 'd1',
      preparedAssetFingerprint: 'fp2',
    });

    const hit = await repo.getBySessionAndPhotoId('sess-a', 'photo-1');
    expect(hit.draft?.capture_photo_id).toBe('photo-1');
    expect(hit.rowsMatched).toBe(1);
    expect(hit.lookupMode).toBe('direct_indexed_lookup');
    expect(hit.fullSessionRowsLoaded).toBe(0);
    expect(hit.queryCount).toBe(1);
  });

  test('does not return draft from another session', async () => {
    const { repo } = await seededRepo();
    await repo.upsertDraft({
      capturePhotoId: 'photo-other',
      captureSessionId: 'sess-b',
      clientFileId: null,
      status: 'RESOLVED',
      parserVersion: 'p1',
      detectorVersion: 'd1',
      preparedAssetFingerprint: 'fp-x',
    });
    const miss = await repo.getBySessionAndPhotoId('sess-a', 'photo-other');
    expect(miss.draft).toBeNull();
    expect(miss.rowsMatched).toBe(0);
  });

  test('returns null when absent (not an error)', async () => {
    const { repo } = await seededRepo();
    const miss = await repo.getBySessionAndPhotoId('sess-a', 'photo-1');
    expect(miss.draft).toBeNull();
  });

  test('upsert then lookup returns same logical draft', async () => {
    const { repo } = await seededRepo();
    const saved = await repo.upsertDraft({
      capturePhotoId: 'photo-1',
      captureSessionId: 'sess-a',
      clientFileId: 'cf',
      status: 'RESOLVED',
      parserVersion: 'p1',
      detectorVersion: 'd1',
      preparedAssetFingerprint: 'fp1',
      internalCode: 'CODE1',
    });
    const hit = await repo.getBySessionAndPhotoId('sess-a', 'photo-1');
    expect(hit.draft?.id).toBe(saved.id);
    expect(hit.draft?.internal_code).toBe('CODE1');
  });

  test('retry upsert same fingerprint does not create duplicates', async () => {
    const { repo, sync } = await seededRepo();
    await repo.upsertDraft({
      capturePhotoId: 'photo-1',
      captureSessionId: 'sess-a',
      clientFileId: null,
      status: 'PENDING',
      parserVersion: 'p1',
      detectorVersion: 'd1',
      preparedAssetFingerprint: 'fp1',
    });
    await repo.upsertDraft({
      capturePhotoId: 'photo-1',
      captureSessionId: 'sess-a',
      clientFileId: null,
      status: 'RESOLVED',
      parserVersion: 'p1',
      detectorVersion: 'd1',
      preparedAssetFingerprint: 'fp1',
    });
    const count = sync
      .prepare(
        `SELECT COUNT(*) AS c FROM local_detection_drafts
         WHERE capture_session_id = ? AND capture_photo_id = ?;`,
      )
      .get('sess-a', 'photo-1') as { c: number };
    expect(Number(count.c)).toBe(1);
    const hit = await repo.getBySessionAndPhotoId('sess-a', 'photo-1');
    expect(hit.draft?.status).toBe('RESOLVED');
  });

  test('multiple fingerprints select highest scan_generation then updated_at', async () => {
    const { repo, sync } = await seededRepo();
    const t1 = '2026-01-01T00:00:00.000Z';
    const t2 = '2026-01-02T00:00:00.000Z';
    const t3 = '2026-01-03T00:00:00.000Z';
    // Bypass upsert UNIQUE path: insert two distinct fingerprint rows manually.
    sync.prepare(
      `INSERT INTO local_detection_drafts (
         id, capture_photo_id, capture_session_id, status,
         parser_version, detector_version, prepared_asset_fingerprint,
         candidate_count, scan_generation, created_at, updated_at
       ) VALUES (?, 'photo-1', 'sess-a', 'RESOLVED', 'p1', 'd1', ?, 0, ?, ?, ?);`,
    ).run('draft-old', 'fp-a', 1, t1, t1);
    sync.prepare(
      `INSERT INTO local_detection_drafts (
         id, capture_photo_id, capture_session_id, status,
         parser_version, detector_version, prepared_asset_fingerprint,
         candidate_count, scan_generation, created_at, updated_at
       ) VALUES (?, 'photo-1', 'sess-a', 'RESOLVED', 'p1', 'd1', ?, 0, ?, ?, ?);`,
    ).run('draft-new', 'fp-b', 2, t2, t3);

    const hit = await repo.getBySessionAndPhotoId('sess-a', 'photo-1');
    expect(hit.rowsMatched).toBe(2);
    expect(hit.draft?.id).toBe('draft-new');
    expect(hit.draft?.prepared_asset_fingerprint).toBe('fp-b');
    expect(hit.selectionRule).toBe(
      'scan_generation_desc_updated_at_desc_created_at_desc',
    );
    expect(hit.queryCount).toBe(1);
    expect(hit.fullSessionRowsLoaded).toBe(0);
  });

  test('same generation prefers latest updated_at (not earliest created_at)', async () => {
    const { repo, sync } = await seededRepo();
    const earlyCreated = '2026-01-01T00:00:00.000Z';
    const lateCreated = '2026-01-02T00:00:00.000Z';
    const newerUpdate = '2026-01-05T00:00:00.000Z';
    sync.prepare(
      `INSERT INTO local_detection_drafts (
         id, capture_photo_id, capture_session_id, status,
         parser_version, detector_version, prepared_asset_fingerprint,
         candidate_count, scan_generation, created_at, updated_at
       ) VALUES (?, 'photo-1', 'sess-a', 'RESOLVED', 'p1', 'd1', ?, 0, 1, ?, ?);`,
    ).run('draft-early', 'fp-a', earlyCreated, earlyCreated);
    sync.prepare(
      `INSERT INTO local_detection_drafts (
         id, capture_photo_id, capture_session_id, status,
         parser_version, detector_version, prepared_asset_fingerprint,
         candidate_count, scan_generation, created_at, updated_at
       ) VALUES (?, 'photo-1', 'sess-a', 'UNRESOLVED', 'p1', 'd1', ?, 0, 1, ?, ?);`,
    ).run('draft-late-updated', 'fp-b', lateCreated, newerUpdate);

    const hit = await repo.getBySessionAndPhotoId('sess-a', 'photo-1');
    expect(hit.rowsMatched).toBe(2);
    expect(hit.draft?.id).toBe('draft-late-updated');
  });

  test('SQL error becomes DRAFT_LOOKUP_FAILED not null', async () => {
    const { db, file } = openTempDb();
    files.push(file);
    const repo = new LocalDetectionDraftRepository(db as never);
    // Table missing → SQL error
    await expect(repo.getBySessionAndPhotoId('s', 'p')).rejects.toBeInstanceOf(DraftLookupError);
    try {
      await repo.getBySessionAndPhotoId('s', 'p');
    } catch (error) {
      expect(error).toBeInstanceOf(DraftLookupError);
      expect((error as DraftLookupError).code).toBe('DRAFT_LOOKUP_FAILED');
    }
  });

  test('migration v39 creates session_photo index (idempotent)', async () => {
    const { sync, file } = openTempDb();
    files.push(file);
    ensureSchemaMigrationsTable(sync);
    applyAllMigrations(sync);
    const idx = sync
      .prepare(
        `SELECT name, sql FROM sqlite_master
         WHERE type = 'index' AND name = 'idx_local_detection_drafts_session_photo';`,
      )
      .get() as { name: string; sql: string } | undefined;
    expect(idx?.name).toBe('idx_local_detection_drafts_session_photo');
    expect(idx?.sql).toContain('capture_session_id');
    expect(idx?.sql).toContain('capture_photo_id');

    // Re-run migration SQL — IF NOT EXISTS keeps idempotent
    const v39 = MIGRATIONS.find((m) => m.version === 39)!;
    expect(() => sync.exec(v39.sql)).not.toThrow();
  });

  test('EXPLAIN QUERY PLAN uses session_photo index without ORDER BY temp B-tree', async () => {
    const { sync, file } = openTempDb();
    files.push(file);
    ensureSchemaMigrationsTable(sync);
    applyAllMigrations(sync);
    const plan = sync
      .prepare(
        `EXPLAIN QUERY PLAN
         SELECT * FROM local_detection_drafts
         WHERE capture_session_id = ?
           AND capture_photo_id = ?;`,
      )
      .all('sess-a', 'photo-1') as Array<{ detail: string }>;
    const joined = plan.map((p) => p.detail).join('\n');
    fs.writeFileSync(
      path.join(os.tmpdir(), 'phase2-query-plan.txt'),
      joined + '\n',
      'utf8',
    );
    expect(joined.toLowerCase()).toMatch(/session_photo|using index|cover/i);
    expect(joined.toLowerCase()).not.toMatch(/temp b-tree|use temp/);
  });

  test('UNIQUE allows multiple drafts per photo across fingerprints', async () => {
    const { sync, file } = openTempDb();
    files.push(file);
    ensureSchemaMigrationsTable(sync);
    applyAllMigrations(sync);
    const idx = sync
      .prepare(
        `SELECT sql FROM sqlite_master
         WHERE type = 'table' AND name = 'local_detection_drafts';`,
      )
      .get() as { sql: string } | undefined;
    expect(idx?.sql ?? '').toMatch(
      /UNIQUE\s*\(\s*capture_photo_id\s*,\s*detector_version\s*,\s*parser_version\s*,\s*prepared_asset_fingerprint\s*\)/i,
    );
  });
});
