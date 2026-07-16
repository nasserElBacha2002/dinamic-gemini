import * as SQLite from 'expo-sqlite';

import { MIGRATIONS, validateMigrations } from './migrations/migrations';

export type SQLiteDatabase = Awaited<ReturnType<typeof SQLite.openDatabaseAsync>>;

let dbPromise: Promise<SQLiteDatabase> | null = null;

export async function getDatabase(): Promise<SQLiteDatabase> {
  if (!dbPromise) {
    dbPromise = SQLite.openDatabaseAsync('dinamic_mobile.db').then(async (db) => {
      await migrate(db);
      return db;
    });
  }
  return dbPromise;
}

export async function migrate(db: SQLiteDatabase): Promise<void> {
  validateMigrations();
  await db.execAsync('PRAGMA foreign_keys = ON;');
  await db.execAsync('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY NOT NULL, name TEXT NOT NULL, applied_at TEXT NOT NULL);');
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

