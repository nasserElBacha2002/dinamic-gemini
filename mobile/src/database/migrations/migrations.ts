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
  {
    version: 6,
    name: 'session_preparation_processing_mode',
    sql: `
ALTER TABLE capture_sessions ADD COLUMN preparation_processing_mode TEXT NOT NULL DEFAULT 'UNKNOWN';
`,
  },
  {
    version: 7,
    name: 'upload_worker_leases',
    sql: `
ALTER TABLE capture_photos ADD COLUMN upload_worker_owner TEXT;
ALTER TABLE capture_photos ADD COLUMN upload_lease_token TEXT;
ALTER TABLE capture_photos ADD COLUMN upload_lease_expires_at TEXT;
ALTER TABLE capture_photos ADD COLUMN upload_heartbeat_at TEXT;
ALTER TABLE capture_photos ADD COLUMN upload_cancel_requested INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_capture_photos_upload_lease
  ON capture_photos(upload_lease_expires_at);
`,
  },
  {
    version: 8,
    name: 'local_detection_drafts',
    sql: `
CREATE TABLE IF NOT EXISTS local_detection_drafts (
  id TEXT PRIMARY KEY NOT NULL,
  capture_photo_id TEXT NOT NULL,
  capture_session_id TEXT NOT NULL,
  client_file_id TEXT,
  status TEXT NOT NULL,
  raw_value_hash TEXT,
  raw_value_preview TEXT,
  internal_code TEXT,
  quantity INTEGER,
  quantity_status TEXT,
  detected_format TEXT,
  detected_symbology TEXT,
  parser_version TEXT NOT NULL,
  detector_version TEXT NOT NULL,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  processing_ms INTEGER,
  compare_result TEXT,
  compared_at TEXT,
  prepared_asset_fingerprint TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(capture_photo_id, detector_version, parser_version, prepared_asset_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_local_detection_drafts_photo
  ON local_detection_drafts(capture_photo_id);
CREATE INDEX IF NOT EXISTS idx_local_detection_drafts_session
  ON local_detection_drafts(capture_session_id);
`,
  },
  {
    version: 9,
    name: 'local_detection_drafts_harden',
    sql: `
CREATE TABLE IF NOT EXISTS local_detection_drafts_v9 (
  id TEXT PRIMARY KEY NOT NULL,
  capture_photo_id TEXT NOT NULL,
  capture_session_id TEXT NOT NULL,
  client_file_id TEXT,
  status TEXT NOT NULL,
  raw_value_hash TEXT,
  internal_code TEXT,
  quantity INTEGER,
  quantity_status TEXT,
  detected_format TEXT,
  detected_symbology TEXT,
  parser_version TEXT NOT NULL,
  detector_version TEXT NOT NULL,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  processing_ms INTEGER,
  comparison_status TEXT,
  compare_result TEXT,
  compared_at TEXT,
  prepared_asset_fingerprint TEXT,
  scan_owner TEXT,
  scan_generation INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(capture_photo_id, detector_version, parser_version, prepared_asset_fingerprint),
  FOREIGN KEY (capture_photo_id) REFERENCES capture_photos(id) ON DELETE CASCADE
);

DELETE FROM local_detection_drafts
 WHERE capture_photo_id NOT IN (SELECT id FROM capture_photos);

INSERT OR IGNORE INTO local_detection_drafts_v9 (
  id, capture_photo_id, capture_session_id, client_file_id, status,
  raw_value_hash, internal_code, quantity, quantity_status,
  detected_format, detected_symbology, parser_version, detector_version,
  candidate_count, error_code, processing_ms, comparison_status, compare_result, compared_at,
  prepared_asset_fingerprint, scan_owner, scan_generation, created_at, updated_at
)
SELECT
  id, capture_photo_id, capture_session_id, client_file_id, status,
  raw_value_hash, internal_code, quantity, quantity_status,
  detected_format, detected_symbology, parser_version, detector_version,
  candidate_count, error_code, processing_ms, NULL, compare_result, compared_at,
  prepared_asset_fingerprint, NULL, 0, created_at, updated_at
FROM local_detection_drafts;

DROP TABLE IF EXISTS local_detection_drafts;
ALTER TABLE local_detection_drafts_v9 RENAME TO local_detection_drafts;

CREATE INDEX IF NOT EXISTS idx_local_detection_drafts_photo
  ON local_detection_drafts(capture_photo_id);
CREATE INDEX IF NOT EXISTS idx_local_detection_drafts_session
  ON local_detection_drafts(capture_session_id);
CREATE INDEX IF NOT EXISTS idx_local_detection_drafts_status
  ON local_detection_drafts(status);
`,
  },
  {
    version: 10,
    name: 'local_detection_drafts_sync',
    sql: `
ALTER TABLE local_detection_drafts ADD COLUMN sync_status TEXT NOT NULL DEFAULT 'NOT_READY';
ALTER TABLE local_detection_drafts ADD COLUMN sync_attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE local_detection_drafts ADD COLUMN sync_next_retry_at TEXT;
ALTER TABLE local_detection_drafts ADD COLUMN sync_last_error_code TEXT;
ALTER TABLE local_detection_drafts ADD COLUMN server_preliminary_id TEXT;
ALTER TABLE local_detection_drafts ADD COLUMN synced_at TEXT;
ALTER TABLE local_detection_drafts ADD COLUMN sync_lease_token TEXT;
ALTER TABLE local_detection_drafts ADD COLUMN sync_lease_expires_at TEXT;

CREATE INDEX IF NOT EXISTS idx_local_detection_drafts_sync
  ON local_detection_drafts(sync_status, sync_next_retry_at);
`,
  },
  {
    version: 11,
    name: 'local_detection_drafts_detected_at',
    sql: `
ALTER TABLE local_detection_drafts ADD COLUMN detected_at TEXT;
UPDATE local_detection_drafts
   SET detected_at = updated_at
 WHERE detected_at IS NULL
   AND status NOT IN ('PENDING', 'SCANNING', 'NOT_APPLICABLE');
`,
  },
  {
    version: 12,
    name: 'confirmed_local_results',
    sql: `
CREATE TABLE IF NOT EXISTS confirmed_local_results (
  id TEXT PRIMARY KEY NOT NULL,
  capture_photo_id TEXT NOT NULL UNIQUE,
  capture_session_id TEXT NOT NULL,
  client_file_id TEXT,
  asset_id TEXT,
  detected_internal_code TEXT,
  detected_quantity INTEGER,
  confirmed_internal_code TEXT NOT NULL,
  confirmed_quantity INTEGER,
  quantity_status TEXT NOT NULL,
  source TEXT NOT NULL,
  detected_symbology TEXT,
  parser_version TEXT NOT NULL,
  detector_version TEXT NOT NULL,
  prepared_asset_sha256 TEXT NOT NULL,
  confirmed_by_user_id TEXT,
  confirmed_at TEXT NOT NULL,
  sync_status TEXT NOT NULL DEFAULT 'PENDING',
  sync_attempt_count INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT,
  sync_last_error_code TEXT,
  row_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (capture_photo_id) REFERENCES capture_photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_confirmed_local_results_session
  ON confirmed_local_results(capture_session_id);
CREATE INDEX IF NOT EXISTS idx_confirmed_local_results_sync
  ON confirmed_local_results(sync_status, next_retry_at);
`,
  },
  {
    version: 13,
    name: 'confirmed_local_results_applied_at',
    sql: `
ALTER TABLE confirmed_local_results ADD COLUMN applied_at TEXT;
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

