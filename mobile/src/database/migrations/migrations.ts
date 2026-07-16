export interface Migration {
  readonly version: number;
  readonly name: string;
  readonly sql: string;
}

export const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    name: 'capture_sessions_and_photos',
    sql: `
CREATE TABLE IF NOT EXISTS capture_sessions (
  id TEXT PRIMARY KEY NOT NULL,
  inventory_id TEXT NOT NULL,
  inventory_name TEXT NOT NULL,
  aisle_id TEXT NOT NULL,
  aisle_name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  initial_asset_id TEXT,
  initial_date_added INTEGER,
  initial_date_modified INTEGER,
  initial_display_name TEXT,
  initial_size INTEGER,
  initial_bucket_id INTEGER,
  scan_cursor_date_added INTEGER NOT NULL,
  scan_cursor_asset_id TEXT NOT NULL,
  last_valid_cursor_date_added INTEGER NOT NULL,
  last_valid_cursor_asset_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capture_photos (
  id TEXT PRIMARY KEY NOT NULL,
  capture_session_id TEXT NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL,
  media_store_numeric_id INTEGER,
  uri TEXT NOT NULL,
  display_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  date_added INTEGER NOT NULL,
  date_modified INTEGER NOT NULL,
  bucket_id INTEGER,
  relative_path TEXT,
  status TEXT NOT NULL,
  rejection_reason TEXT,
  stability_checks INTEGER NOT NULL DEFAULT 0,
  stability_error TEXT,
  detected_at TEXT,
  stable_at TEXT,
  excluded_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(capture_session_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_capture_photos_session ON capture_photos(capture_session_id);
CREATE INDEX IF NOT EXISTS idx_capture_photos_status ON capture_photos(status);
CREATE INDEX IF NOT EXISTS idx_capture_photos_asset_id ON capture_photos(asset_id);
CREATE INDEX IF NOT EXISTS idx_capture_photos_date_added ON capture_photos(date_added);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_status ON capture_sessions(status);
`,
  },
  {
    version: 2,
    name: 'capture_stability_metrics',
    sql: `
ALTER TABLE capture_photos ADD COLUMN stability_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE capture_photos ADD COLUMN last_stability_attempt_at TEXT;
`,
  },
];

export function validateMigrations(migrations: readonly Migration[] = MIGRATIONS): void {
  const seen = new Set<number>();
  let previous = 0;
  for (const migration of migrations) {
    if (seen.has(migration.version)) {
      throw new Error(`Duplicate migration version: ${migration.version}`);
    }
    if (migration.version <= previous) {
      throw new Error(`Migrations must be strictly ordered: ${migration.version} after ${previous}`);
    }
    if (!migration.name.trim()) {
      throw new Error(`Migration ${migration.version} has an empty name`);
    }
    seen.add(migration.version);
    previous = migration.version;
  }
}

