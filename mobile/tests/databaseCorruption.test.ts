import { isSqliteMalformedError } from '../src/database/sqliteErrors';

describe('isSqliteMalformedError', () => {
  it('detects common SQLite corruption messages', () => {
    expect(isSqliteMalformedError(new Error('database disk image is malformed'))).toBe(true);
    expect(isSqliteMalformedError(new Error('SQLITE_CORRUPT: database disk image is malformed'))).toBe(
      true,
    );
    expect(isSqliteMalformedError('file is not a database')).toBe(true);
    expect(isSqliteMalformedError(new Error('UNIQUE constraint failed'))).toBe(false);
  });
});
