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
    expect(MIGRATIONS.map((m) => m.version)).toEqual([1, 2, 3, 4, 5]);
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
});

