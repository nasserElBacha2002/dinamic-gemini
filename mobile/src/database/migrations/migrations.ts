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
  {
    version: 3,
    name: 'session_upload_processing_fields',
    sql: `
ALTER TABLE capture_sessions ADD COLUMN upload_batch_id TEXT;
ALTER TABLE capture_sessions ADD COLUMN upload_status TEXT NOT NULL DEFAULT 'idle';
ALTER TABLE capture_sessions ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'idle';
ALTER TABLE capture_sessions ADD COLUMN backend_job_id TEXT;
ALTER TABLE capture_sessions ADD COLUMN upload_started_at TEXT;
ALTER TABLE capture_sessions ADD COLUMN upload_completed_at TEXT;
ALTER TABLE capture_sessions ADD COLUMN processing_started_at TEXT;
ALTER TABLE capture_sessions ADD COLUMN processing_finished_at TEXT;
ALTER TABLE capture_sessions ADD COLUMN last_upload_error TEXT;
ALTER TABLE capture_sessions ADD COLUMN last_processing_error TEXT;

CREATE INDEX IF NOT EXISTS idx_capture_sessions_upload_batch_id ON capture_sessions(upload_batch_id);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_backend_job_id ON capture_sessions(backend_job_id);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_processing_status ON capture_sessions(processing_status);
`,
  },
  {
    version: 4,
    name: 'photo_upload_fields_and_queue_tables',
    sql: `
ALTER TABLE capture_photos ADD COLUMN client_file_id TEXT;
ALTER TABLE capture_photos ADD COLUMN backend_asset_id TEXT;
ALTER TABLE capture_photos ADD COLUMN upload_status TEXT NOT NULL DEFAULT 'not_queued';
ALTER TABLE capture_photos ADD COLUMN upload_progress REAL NOT NULL DEFAULT 0;
ALTER TABLE capture_photos ADD COLUMN upload_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE capture_photos ADD COLUMN upload_batch_id TEXT;
ALTER TABLE capture_photos ADD COLUMN last_upload_error_code TEXT;
ALTER TABLE capture_photos ADD COLUMN last_upload_error_message TEXT;
ALTER TABLE capture_photos ADD COLUMN last_upload_attempt_at TEXT;
ALTER TABLE capture_photos ADD COLUMN next_retry_at TEXT;
ALTER TABLE capture_photos ADD COLUMN uploaded_at TEXT;
ALTER TABLE capture_photos ADD COLUMN remote_deleted_at TEXT;
ALTER TABLE capture_photos ADD COLUMN local_transform_uri TEXT;
ALTER TABLE capture_photos ADD COLUMN original_size INTEGER;
ALTER TABLE capture_photos ADD COLUMN upload_size INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS idx_capture_photos_session_client_file
  ON capture_photos(capture_session_id, client_file_id)
  WHERE client_file_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_capture_photos_upload_status ON capture_photos(upload_status);
CREATE INDEX IF NOT EXISTS idx_capture_photos_next_retry_at ON capture_photos(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_capture_photos_client_file_id ON capture_photos(client_file_id);
CREATE INDEX IF NOT EXISTS idx_capture_photos_backend_asset_id ON capture_photos(backend_asset_id);

CREATE TABLE IF NOT EXISTS upload_batches (
  id TEXT PRIMARY KEY NOT NULL,
  capture_session_id TEXT NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
  inventory_id TEXT NOT NULL,
  aisle_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_upload_batches_session ON upload_batches(capture_session_id);
CREATE INDEX IF NOT EXISTS idx_upload_batches_status ON upload_batches(status);

CREATE TABLE IF NOT EXISTS processing_jobs (
  id TEXT PRIMARY KEY NOT NULL,
  capture_session_id TEXT NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
  inventory_id TEXT NOT NULL,
  aisle_id TEXT NOT NULL,
  backend_job_id TEXT NOT NULL,
  status TEXT NOT NULL,
  remote_status TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  last_polled_at TEXT,
  next_poll_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_session ON processing_jobs(capture_session_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_backend_job_id ON processing_jobs(backend_job_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_next_poll_at ON processing_jobs(next_poll_at);
`,
  },
  {
    version: 5,
    name: 'observability_events',
    sql: `
CREATE TABLE IF NOT EXISTS observability_events (
  id TEXT PRIMARY KEY NOT NULL,
  name TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  session_id TEXT,
  server_job_id TEXT,
  client_file_id TEXT,
  batch_id TEXT,
  attempt_id TEXT,
  duration_ms INTEGER,
  attributes_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observability_events_created_at
  ON observability_events(created_at);
CREATE INDEX IF NOT EXISTS idx_observability_events_session
  ON observability_events(session_id);
CREATE INDEX IF NOT EXISTS idx_observability_events_name
  ON observability_events(name);
CREATE INDEX IF NOT EXISTS idx_observability_events_client_file
  ON observability_events(client_file_id);
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

