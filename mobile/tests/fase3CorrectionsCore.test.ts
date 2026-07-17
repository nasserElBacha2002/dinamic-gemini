import { redact, redactString } from '../src/core/logging';
import {
  uniqueJobMonitorWorkName,
  uniqueRemoteDeleteWorkName,
  uniqueUploadSessionWorkName,
  createBackgroundWorkScheduler,
} from '../src/native/backgroundWork';
import { createLogger } from '../src/core/logging';

describe('deep redaction', () => {
  it('redacts secrets inside arrays and nested objects', () => {
    const out = redact({
      items: [{ api_key: 'k', ok: 1 }, { nested: { client_secret: 's' } }],
      headers: { Authorization: 'Bearer abc.def' },
      url: 'https://x.test/file?access_token=tok&other=1',
      my_password: 'p',
    });
    expect((out.items as unknown[])[0]).toEqual({ api_key: '[redacted]', ok: 1 });
    expect(((out.items as unknown[])[1] as { nested: Record<string, unknown> }).nested.client_secret).toBe(
      '[redacted]',
    );
    expect((out.headers as Record<string, unknown>).Authorization).toBe('[redacted]');
    expect(out.url).toBe('https://x.test/file?access_token=[redacted]&other=1');
    expect(out.my_password).toBe('[redacted]');
  });

  it('redacts Bearer tokens in free-form strings', () => {
    expect(redactString('Authorization: Bearer eyJhbGciOi.abc')).toContain('Bearer [redacted]');
  });
});

describe('WorkManager naming / noop scheduler', () => {
  it('uses stable unique work names', () => {
    expect(uniqueUploadSessionWorkName('s1')).toBe('upload-session-s1');
    expect(uniqueJobMonitorWorkName('j1')).toBe('job-monitor-j1');
    expect(uniqueRemoteDeleteWorkName('a1')).toBe('remote-delete-a1');
  });

  it('tracks and cancels scheduled noop work on logout path', async () => {
    const events: string[] = [];
    const logger = createLogger((r) => events.push(r.event));
    const scheduler = createBackgroundWorkScheduler(logger);
    await scheduler.scheduleUploadSession('s1');
    await scheduler.scheduleJobMonitor('j1');
    await scheduler.cancelAllTracked();
    expect(events.filter((e) => e === 'work_scheduled').length).toBeGreaterThanOrEqual(3);
  });
});
