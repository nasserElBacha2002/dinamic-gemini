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
  | 'health_check'
  | 'aisle_blocked';

export interface LogRecord {
  readonly ts: string;
  readonly level: LogLevel;
  readonly event: LogEvent;
  readonly fields: Record<string, unknown>;
}

const EXACT_SENSITIVE_KEYS = new Set([
  'token',
  'access_token',
  'accesstoken',
  'refresh_token',
  'refreshtoken',
  'authorization',
  'password',
  'pass',
  'secret',
  'apikey',
  'api_key',
  'x-api-key',
  'x_api_key',
  'signed_url',
  'signedurl',
  'bytes',
  'data',
  'multipart',
  'payload',
]);

function isSensitiveKey(key: string): boolean {
  const k = key.toLowerCase().replace(/-/g, '_');
  if (EXACT_SENSITIVE_KEYS.has(k)) {
    return true;
  }
  return (
    k.endsWith('_token') ||
    k.endsWith('_secret') ||
    k.endsWith('_password') ||
    k.endsWith('_key') ||
    k.includes('authorization')
  );
}

const BEARER_RE = /\bBearer\s+[A-Za-z0-9\-._~+/]+=*/gi;
const QUERY_SECRET_RE = /([?&](?:access_token|refresh_token|token|api_key|apikey|signature|sig|X-Amz-Signature)=)([^&#]*)/gi;

export function redactString(value: string): string {
  let out = value.replace(BEARER_RE, 'Bearer [redacted]');
  out = out.replace(QUERY_SECRET_RE, '$1[redacted]');
  return out;
}

export function redactValue(value: unknown): unknown {
  if (value == null) {
    return value;
  }
  if (typeof value === 'string') {
    return redactString(value);
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item));
  }
  if (typeof value === 'object') {
    return redact(value as Record<string, unknown>);
  }
  return String(value);
}

export function redact(fields: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (isSensitiveKey(key)) {
      out[key] = '[redacted]';
    } else {
      out[key] = redactValue(value);
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
