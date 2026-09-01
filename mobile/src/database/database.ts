import * as SQLite from 'expo-sqlite';

import { MIGRATIONS, validateMigrations } from './migrations/migrations';
import { isSqliteBusyError, isSqliteMalformedError } from './sqliteErrors';
import {
  SQLITE_BUSY_TIMEOUT_MS,
  __resetSqliteWriteGateForTests,
  resetSqliteWriteGate,
} from './sqliteWriteGate';

export type SQLiteDatabase = Awaited<ReturnType<typeof SQLite.openDatabaseAsync>>;
export { isSqliteMalformedError, isSqliteBusyError } from './sqliteErrors';
export {
  runExclusiveDbWrite,
  runExclusiveDbWriteWithBusyRetry,
  runImmediateTransaction,
  withSqliteBusyRetry,
  SQLITE_BUSY_TIMEOUT_MS,
} from './sqliteWriteGate';

export const MOBILE_DB_NAME = 'dinamic_mobile.db';

/** Shorter native busy wait while opening during bootstrap (avoid 15s UI freeze). */
const BOOTSTRAP_BUSY_TIMEOUT_MS = 2_000;
const BOOTSTRAP_OPEN_MAX_ATTEMPTS = 12;

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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function probeDatabase(db: SQLiteDatabase, options?: { fullIntegrity?: boolean }): Promise<void> {
  const row = await db.getFirstAsync<{ ok: number }>('SELECT 1 AS ok;');
  if (row?.ok !== 1) {
    throw new Error('database disk image is malformed: probe failed');
  }
  if (options?.fullIntegrity !== true) {
    return;
  }
  const integrity = await db.getFirstAsync<{ integrity_check: string }>('PRAGMA integrity_check;');
  const result = integrity?.integrity_check ?? '';
  if (result !== 'ok') {
    throw new Error(`database disk image is malformed: ${result}`);
  }
}

async function configureDatabasePragmas(db: SQLiteDatabase, busyTimeoutMs: number): Promise<void> {
  await db.execAsync('PRAGMA journal_mode = WAL;');
  await db.execAsync(`PRAGMA busy_timeout = ${busyTimeoutMs};`);
  await db.execAsync('PRAGMA synchronous = NORMAL;');
}

async function closeDatabaseHandle(db: SQLiteDatabase | null | undefined): Promise<void> {
  if (!db) return;
  try {
    await db.closeAsync();
  } catch {
    // best-effort — release WAL locks when superseding a bootstrap
  }
}

/**
 * Close the process-wide DB handle before a relaunch bootstrap.
 * Helps Expo reload release SQLite locks held by the previous app instance.
 */
export async function closeDatabaseForRelaunch(): Promise<void> {
  if (!dbPromise) {
    resetSqliteWriteGate();
    return;
  }
  const pending = dbPromise;
  dbPromise = null;
  resetSqliteWriteGate();
  try {
    const db = await pending;
    await closeDatabaseHandle(db);
  } catch {
    // open may still be in progress or already failed
  }
}

async function openMigratedDatabase(): Promise<SQLiteDatabase> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= BOOTSTRAP_OPEN_MAX_ATTEMPTS; attempt += 1) {
    let opened: SQLiteDatabase | null = null;
    try {
      resetSqliteWriteGate();
      opened = await SQLite.openDatabaseAsync(MOBILE_DB_NAME);
      await configureDatabasePragmas(opened, BOOTSTRAP_BUSY_TIMEOUT_MS);
      await probeDatabase(opened, { fullIntegrity: attempt === 1 });
      await migrate(opened);
      await opened.execAsync(`PRAGMA busy_timeout = ${SQLITE_BUSY_TIMEOUT_MS};`);
      return opened;
    } catch (error) {
      lastError = error;
      await closeDatabaseHandle(opened);
      if (isSqliteMalformedError(error)) {
        throw error;
      }
      if (!isSqliteBusyError(error) && attempt >= BOOTSTRAP_OPEN_MAX_ATTEMPTS) {
        throw error;
      }
      if (!isSqliteBusyError(error)) {
        throw error;
      }
      await sleep(Math.min(30 * attempt, 250));
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
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
