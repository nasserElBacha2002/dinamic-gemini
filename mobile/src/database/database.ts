import * as SQLite from 'expo-sqlite';

import { MIGRATIONS, validateMigrations } from './migrations/migrations';
import { isSqliteMalformedError } from './sqliteErrors';
import { SQLITE_BUSY_TIMEOUT_MS, __resetSqliteWriteGateForTests } from './sqliteWriteGate';

export type SQLiteDatabase = Awaited<ReturnType<typeof SQLite.openDatabaseAsync>>;
export { isSqliteMalformedError, isSqliteBusyError } from './sqliteErrors';
export {
  runExclusiveDbWrite,
  runExclusiveDbWriteWithBusyRetry,
  withSqliteBusyRetry,
  SQLITE_BUSY_TIMEOUT_MS,
} from './sqliteWriteGate';

export const MOBILE_DB_NAME = 'dinamic_mobile.db';

let dbPromise: Promise<SQLiteDatabase> | null = null;
let recoveredFromCorruption = false;

/** True once after a successful recreate; consume so UI can show a one-shot alert. */
export function consumeDatabaseRecoveryFlag(): boolean {
  const value = recoveredFromCorruption;
  recoveredFromCorruption = false;
  return value;
}

/** @internal test helper */
export function __resetDatabaseSingletonForTests(): void {
  dbPromise = null;
  recoveredFromCorruption = false;
  __resetSqliteWriteGateForTests();
}

async function probeDatabase(db: SQLiteDatabase): Promise<void> {
  const row = await db.getFirstAsync<{ ok: number }>('SELECT 1 AS ok;');
  if (row?.ok !== 1) {
    throw new Error('database disk image is malformed: probe failed');
  }
  const integrity = await db.getFirstAsync<{ integrity_check: string }>('PRAGMA integrity_check;');
  const result = integrity?.integrity_check ?? '';
  if (result !== 'ok') {
    throw new Error(`database disk image is malformed: ${result}`);
  }
}

async function openMigratedDatabase(): Promise<SQLiteDatabase> {
  const db = await SQLite.openDatabaseAsync(MOBILE_DB_NAME);
  // Reduce "database is locked" under concurrent upload/scan writers.
  await db.execAsync('PRAGMA journal_mode = WAL;');
  await db.execAsync(`PRAGMA busy_timeout = ${SQLITE_BUSY_TIMEOUT_MS};`);
  await db.execAsync('PRAGMA synchronous = NORMAL;');
  await probeDatabase(db);
  await migrate(db);
  return db;
}

async function recreateDatabaseAfterCorruption(cause: unknown): Promise<SQLiteDatabase> {
  try {
    await SQLite.deleteDatabaseAsync(MOBILE_DB_NAME);
  } catch {
    // Best-effort delete; open below still attempts a fresh file.
  }
  recoveredFromCorruption = true;
  const db = await SQLite.openDatabaseAsync(MOBILE_DB_NAME);
  await migrate(db);
  void cause;
  return db;
}

export async function getDatabase(): Promise<SQLiteDatabase> {
  if (!dbPromise) {
    dbPromise = (async () => {
      try {
        return await openMigratedDatabase();
      } catch (error) {
        if (!isSqliteMalformedError(error)) {
          throw error;
        }
        return recreateDatabaseAfterCorruption(error);
      }
    })().catch((error) => {
      dbPromise = null;
      throw error;
    });
  }
  return dbPromise;
}

export async function migrate(db: SQLiteDatabase): Promise<void> {
  validateMigrations();
  await db.execAsync('PRAGMA foreign_keys = ON;');
  await db.execAsync('PRAGMA journal_mode = WAL;');
  await db.execAsync(`PRAGMA busy_timeout = ${SQLITE_BUSY_TIMEOUT_MS};`);
  await db.execAsync(
    'CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY NOT NULL, name TEXT NOT NULL, applied_at TEXT NOT NULL);',
  );
  const rows = await db.getAllAsync<{ version: number }>('SELECT version FROM schema_migrations;');
  const applied = new Set(rows.map((r) => r.version));
  for (const migration of MIGRATIONS) {
    if (applied.has(migration.version)) {
      continue;
    }
    await db.execAsync('BEGIN;');
    try {
      await db.execAsync(migration.sql);
      await db.runAsync(
        'INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);',
        migration.version,
        migration.name,
        new Date().toISOString(),
      );
      await db.execAsync('COMMIT;');
    } catch (e) {
      await db.execAsync('ROLLBACK;');
      throw e;
    }
  }
}
