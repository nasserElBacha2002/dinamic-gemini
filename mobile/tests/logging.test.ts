import { createLogger, redact, type LogRecord } from '../src/core/logging';

describe('redaction-safe logging', () => {
  it('redacts sensitive keys, including nested ones', () => {
    const out = redact({
      access_token: 'abc',
      nested: { refresh_token: 'xyz', mediaStoreId: 5 },
      mediaStoreId: 7,
    });
    expect(out.access_token).toBe('[redacted]');
    expect((out.nested as Record<string, unknown>).refresh_token).toBe('[redacted]');
    expect((out.nested as Record<string, unknown>).mediaStoreId).toBe(5);
    expect(out.mediaStoreId).toBe(7);
  });

  it('emits structured records without leaking tokens', () => {
    const records: LogRecord[] = [];
    const log = createLogger((r) => records.push(r), () => new Date('2026-01-01T00:00:00Z'));
    log.info('auth_login', { token: 'secret', username: 'op1' });
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      level: 'info',
      event: 'auth_login',
      fields: { token: '[redacted]', username: 'op1' },
      ts: '2026-01-01T00:00:00.000Z',
    });
  });
});
