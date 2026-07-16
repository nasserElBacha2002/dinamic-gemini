import { MIGRATIONS } from '../src/database/migrations/migrations';

describe('SQLite migrations', () => {
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
});

