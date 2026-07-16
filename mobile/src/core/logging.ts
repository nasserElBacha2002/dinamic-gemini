/**
 * Structured, redaction-safe local logging (Fase 0, §30).
 *
 * Emits JSON-serializable events. Never logs tokens, passwords, image bytes, or full signed
 * URLs. A small redaction pass strips obviously sensitive keys before emitting.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type LogEvent =
  | 'session_start'
  | 'session_finish'
  | 'marker_initial'
  | 'photo_detected'
  | 'photo_ignored'
  | 'file_unstable'
  | 'auth_login'
  | 'auth_refresh'
  | 'upload_started'
  | 'upload_confirmed'
  | 'upload_retry'
  | 'upload_paused'
  | 'upload_resumed'
  | 'photo_enqueued'
  | 'upload_limits_refreshed'
  | 'upload_limits_fallback'
  | 'upload_enqueue_missing_batch'
  | 'error'
  | 'job_started'
  | 'job_status_changed'
  | 'job_poll_error'
  | 'recovery';

export interface LogRecord {
  readonly ts: string;
  readonly level: LogLevel;
  readonly event: LogEvent;
  readonly fields: Record<string, unknown>;
}

const _REDACT_KEYS = new Set([
  'token',
  'access_token',
  'accesstoken',
  'refresh_token',
  'refreshtoken',
  'authorization',
  'password',
  'pass',
  'apikey',
  'api_key',
  'x-api-key',
  'signed_url',
  'signedurl',
  'bytes',
  'data',
]);

export function redact(fields: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (_REDACT_KEYS.has(key.toLowerCase())) {
      out[key] = '[redacted]';
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = redact(value as Record<string, unknown>);
    } else {
      out[key] = value;
    }
  }
  return out;
}

export type LogSink = (record: LogRecord) => void;

/** Default sink: console. Replace in native layer with SQLite/file sink as needed. */
const consoleSink: LogSink = (record) => {
  // eslint-disable-next-line no-console
  console.log(JSON.stringify(record));
};

export function createLogger(
  sink: LogSink = consoleSink,
  now: () => Date = () => new Date(),
) {
  function emit(level: LogLevel, event: LogEvent, fields: Record<string, unknown> = {}): void {
    sink({ ts: now().toISOString(), level, event, fields: redact(fields) });
  }
  return {
    debug: (event: LogEvent, fields?: Record<string, unknown>) => emit('debug', event, fields),
    info: (event: LogEvent, fields?: Record<string, unknown>) => emit('info', event, fields),
    warn: (event: LogEvent, fields?: Record<string, unknown>) => emit('warn', event, fields),
    error: (event: LogEvent, fields?: Record<string, unknown>) => emit('error', event, fields),
  };
}

export type Logger = ReturnType<typeof createLogger>;
