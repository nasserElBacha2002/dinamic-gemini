/**
 * Structured, redaction-safe local logging.
 * Emits JSON-serializable events. Never logs tokens, passwords, image bytes, or full signed URLs.
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
  | 'recovery'
  | 'diagnostic_exported'
  | 'storage_cleanup'
  | 'work_scheduled'
  | 'health_check';

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

const consoleSink: LogSink = (record) => {
  // eslint-disable-next-line no-console
  console.log(JSON.stringify(record));
};

/** In-memory ring buffer for diagnostic export (max records). */
export class RingLogBuffer {
  private readonly records: LogRecord[] = [];

  constructor(private readonly maxRecords = 500) {}

  push(record: LogRecord): void {
    this.records.push(record);
    while (this.records.length > this.maxRecords) {
      this.records.shift();
    }
  }

  snapshot(): readonly LogRecord[] {
    return [...this.records];
  }

  clear(): void {
    this.records.length = 0;
  }
}

export const sharedLogBuffer = new RingLogBuffer(500);

export function createLogger(
  sink: LogSink = consoleSink,
  now: () => Date = () => new Date(),
  buffer: RingLogBuffer = sharedLogBuffer,
) {
  function emit(level: LogLevel, event: LogEvent, fields: Record<string, unknown> = {}): void {
    const record: LogRecord = { ts: now().toISOString(), level, event, fields: redact(fields) };
    buffer.push(record);
    sink(record);
  }
  return {
    debug: (event: LogEvent, fields?: Record<string, unknown>) => emit('debug', event, fields),
    info: (event: LogEvent, fields?: Record<string, unknown>) => emit('info', event, fields),
    warn: (event: LogEvent, fields?: Record<string, unknown>) => emit('warn', event, fields),
    error: (event: LogEvent, fields?: Record<string, unknown>) => emit('error', event, fields),
  };
}

export type Logger = ReturnType<typeof createLogger>;
