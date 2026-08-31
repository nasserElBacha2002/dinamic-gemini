import { MIGRATIONS, validateMigrations } from '../src/database/migrations/migrations';

describe('SQLite migrations', () => {
  it('keeps migration versions unique and strictly ordered', () => {
    expect(() => validateMigrations()).not.toThrow();
    expect(() =>
      validateMigrations([
        { version: 1, name: 'a', sql: 'SELECT 1;' },
        { version: 1, name: 'b', sql: 'SELECT 2;' },
      ]),
    ).toThrow('Duplicate migration version');
    expect(() =>
      validateMigrations([
        { version: 2, name: 'b', sql: 'SELECT 2;' },
        { version: 1, name: 'a', sql: 'SELECT 1;' },
      ]),
    ).toThrow('Migrations must be strictly ordered');
  });

  it('creates capture_sessions and capture_photos with required constraints and indexes', () => {
    const sql = MIGRATIONS.map((m) => m.sql).join('\n');
    expect(sql).toContain('CREATE TABLE IF NOT EXISTS capture_sessions');
    expect(sql).toContain('CREATE TABLE IF NOT EXISTS capture_photos');
    expect(sql).toContain('UNIQUE(capture_session_id, asset_id)');
    expect(sql).toContain('idx_capture_photos_session');
    expect(sql).toContain('idx_capture_photos_status');
    expect(sql).toContain('idx_capture_photos_asset_id');
    expect(sql).toContain('idx_capture_photos_date_added');
    expect(sql).toContain('scan_cursor_date_added');
    expect(sql).toContain('last_valid_cursor_date_added');
  });

  it('adds v2 stability metrics without editing migration 1 destructively', () => {
    expect(MIGRATIONS.map((m) => m.version)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
    ]);
    const v2 = MIGRATIONS.find((m) => m.version === 2);
    expect(v2?.sql).toContain('stability_attempts');
    expect(v2?.sql).toContain('last_stability_attempt_at');
  });

  it('adds v3/v4 upload and processing fields without rewriting v1', () => {
    const v3 = MIGRATIONS.find((m) => m.version === 3);
    const v4 = MIGRATIONS.find((m) => m.version === 4);
    expect(v3?.sql).toContain('ALTER TABLE capture_sessions ADD COLUMN upload_batch_id');
    expect(v4?.sql).toContain('ALTER TABLE capture_photos ADD COLUMN client_file_id');
    expect(v4?.sql).toContain('CREATE TABLE IF NOT EXISTS processing_jobs');
  });

  it('adds v5 observability_events table with indexes', () => {
    const v5 = MIGRATIONS.find((m) => m.version === 5);
    expect(v5?.name).toBe('observability_events');
    expect(v5?.sql).toContain('CREATE TABLE IF NOT EXISTS observability_events');
    expect(v5?.sql).toContain('idx_observability_events_session');
    expect(v5?.sql).toContain('idx_observability_events_created_at');
  });

  it('adds v6 preparation_processing_mode with UNKNOWN default', () => {
    const v6 = MIGRATIONS.find((m) => m.version === 6);
    expect(v6?.name).toBe('session_preparation_processing_mode');
    expect(v6?.sql).toContain('ALTER TABLE capture_sessions ADD COLUMN preparation_processing_mode');
    expect(v6?.sql).toContain("DEFAULT 'UNKNOWN'");
  });

  it('adds v7 upload worker lease columns', () => {
    const v7 = MIGRATIONS.find((m) => m.version === 7);
    expect(v7?.name).toBe('upload_worker_leases');
    expect(v7?.sql).toContain('upload_lease_token');
    expect(v7?.sql).toContain('upload_worker_owner');
    expect(v7?.sql).toContain('upload_cancel_requested');
  });

  it('adds v8 local_detection_drafts with idempotency unique key', () => {
    const v8 = MIGRATIONS.find((m) => m.version === 8);
    expect(v8?.name).toBe('local_detection_drafts');
    expect(v8?.sql).toContain('CREATE TABLE IF NOT EXISTS local_detection_drafts');
    expect(v8?.sql).toContain(
      'UNIQUE(capture_photo_id, detector_version, parser_version, prepared_asset_fingerprint)',
    );
    expect(v8?.sql).toContain('idx_local_detection_drafts_photo');
  });

  it('adds v9 draft harden without raw_value_preview and with FK cascade', () => {
    const v9 = MIGRATIONS.find((m) => m.version === 9);
    expect(v9?.name).toBe('local_detection_drafts_harden');
    expect(v9?.sql).toContain('ON DELETE CASCADE');
    expect(v9?.sql).toContain('scan_generation');
    expect(v9?.sql).toContain('comparison_status');
    expect(v9?.sql).not.toContain('raw_value_preview');
  });

  it('adds v17/v18 offline_operations ledger and claim lease columns', () => {
    const v17 = MIGRATIONS.find((m) => m.version === 17);
    const v18 = MIGRATIONS.find((m) => m.version === 18);
    expect(v17?.name).toBe('offline_operations');
    expect(v17?.sql).toContain('CREATE TABLE IF NOT EXISTS offline_operations');
    expect(v18?.name).toBe('offline_operations_claim_and_payload_hash');
    expect(v18?.sql).toContain('payload_hash');
    expect(v18?.sql).toContain('lease_expires_at');
  });

  it('adds v19 ordered capture sequence_number and backend session id', () => {
    const v19 = MIGRATIONS.find((m) => m.version === 19);
    expect(v19?.name).toBe('ordered_capture_sequence');
    expect(v19?.sql).toContain('ALTER TABLE capture_photos ADD COLUMN sequence_number');
    expect(v19?.sql).toContain('backend_ordered_capture_session_id');
    expect(v19?.sql).toContain('idx_capture_photos_session_sequence');
  });

  it('adds v20 process attempt identity columns on capture_sessions', () => {
    const v20 = MIGRATIONS.find((m) => m.version === 20);
    expect(v20?.name).toBe('capture_session_process_attempt_identity');
    expect(v20?.sql).toContain('process_attempt_id');
    expect(v20?.sql).toContain('process_idempotency_key');
    expect(v20?.sql).toContain('process_confirmed_at');
    expect(v20?.sql).toContain('last_recovery_check_at');
  });

  it('adds v21 capture freeze watermark columns', () => {
    const v21 = MIGRATIONS.find((m) => m.version === 21);
    expect(v21?.name).toBe('capture_session_freeze_watermark');
    expect(v21?.sql).toContain('capture_frozen_at');
    expect(v21?.sql).toContain('capture_frozen_photo_count');
    expect(v21?.sql).toContain('capture_freeze_generation');
    const v23 = MIGRATIONS.find((m) => m.version === 23);
    expect(v23?.name).toBe('capture_session_freeze_snapshot');
    expect(v23?.sql).toContain('capture_session_freezes');
    expect(v23?.sql).toContain('capture_session_freeze_photos');
  });

  it('adds v22 local_csv_exports table', () => {
    const v22 = MIGRATIONS.find((m) => m.version === 22);
    expect(v22?.name).toBe('local_csv_exports');
    expect(v22?.sql).toContain('CREATE TABLE IF NOT EXISTS local_csv_exports');
    expect(v22?.sql).toContain('content_fingerprint');
  });

  it('adds v24 session active_position_json and draft position_snapshot_json', () => {
    const v24 = MIGRATIONS.find((m) => m.version === 24);
    expect(v24?.name).toBe('session_active_position_and_draft_snapshot');
    expect(v24?.sql).toContain('ALTER TABLE capture_sessions ADD COLUMN active_position_json');
    expect(v24?.sql).toContain('ALTER TABLE local_detection_drafts ADD COLUMN position_snapshot_json');
  });

  it('adds v25 draft multi-product columns', () => {
    const v25 = MIGRATIONS.find((m) => m.version === 25);
    expect(v25?.name).toBe('draft_multi_product_results');
    expect(v25?.sql).toContain('product_results_json');
    expect(v25?.sql).toContain('label_id');
    expect(v25?.sql).toContain('position_detected');
  });

    it('adds v26 draft rejections_json', () => {
    const v26 = MIGRATIONS.find((m) => m.version === 26);
    expect(v26?.name).toBe('draft_product_rejections_json');
    expect(v26?.sql).toContain('rejections_json');
  });

  it('adds v27 confirmed_local_results label_id', () => {
    const v27 = MIGRATIONS.find((m) => m.version === 27);
    expect(v27?.name).toBe('confirmed_local_results_label_id');
    expect(v27?.sql).toContain('ALTER TABLE confirmed_local_results ADD COLUMN label_id');
  });

  it('adds v28 offline recognition profile tables', () => {
    const v28 = MIGRATIONS.find((m) => m.version === 28);
    expect(v28?.name).toBe('offline_recognition_profiles');
    expect(v28?.sql).toContain('CREATE TABLE IF NOT EXISTS offline_recognition_profiles');
    expect(v28?.sql).toContain('CREATE TABLE IF NOT EXISTS offline_aisle_recognition_config');
    expect(v28?.sql).toContain('CREATE TABLE IF NOT EXISTS offline_recognition_sync_meta');
    expect(v28?.sql).toContain('PRIMARY KEY (inventory_id, client_supplier_id, label_kind)');
    expect(v28?.sql).toContain('recognition_profile_snapshot_json');
  });
});

