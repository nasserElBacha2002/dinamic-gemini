/**
 * Phase 9 — durable offline operation contracts (pure types / status machine).
 */

export const OFFLINE_OPERATION_TYPES = [
  'UPLOAD_ASSET',
  'SYNC_AUTHORITATIVE_RESULT',
  'START_SERVER_PROCESSING',
  'APPLY_LOCAL_RESULTS',
  'FINALIZE_AISLE',
  'CREATE_SERVER_REPROCESS',
  'ADOPT_SERVER_PROPOSALS',
  'SYNC_AISLE_REVISION',
  'APPLY_AISLE_REVISION',
] as const;

export type OfflineOperationType = (typeof OFFLINE_OPERATION_TYPES)[number];

export const OFFLINE_OPERATION_STATUSES = [
  'PENDING',
  'READY',
  'RUNNING',
  'RETRY_WAIT',
  'BLOCKED_AUTH',
  'BLOCKED_DEPENDENCY',
  'BLOCKED_CONFLICT',
  'COMPLETED',
  'FAILED_TERMINAL',
  'CANCELED',
] as const;

export type OfflineOperationStatus = (typeof OFFLINE_OPERATION_STATUSES)[number];

export type OfflineErrorClass = 'retryable' | 'terminal' | 'conflict' | 'auth' | 'dependency';

/** Default priority (lower runs first). */
export const OFFLINE_PRIORITY = {
  CAPTURE_PERSIST: 10,
  LOCAL_PROCESSING: 20,
  UPLOAD: 40,
  SYNC: 50,
  APPLY: 60,
  SERVER_PROCESS: 70,
  FINALIZE: 80,
  REVISION: 90,
  DEFAULT: 100,
} as const;

export interface OfflineOperationRow {
  readonly operation_id: string;
  readonly operation_type: OfflineOperationType;
  readonly entity_type: string;
  readonly entity_id: string;
  readonly inventory_id: string | null;
  readonly aisle_id: string | null;
  readonly asset_id: string | null;
  readonly session_id: string | null;
  readonly payload_json: string;
  readonly payload_version: number;
  readonly payload_hash: string | null;
  readonly idempotency_key: string;
  readonly status: OfflineOperationStatus;
  readonly priority: number;
  readonly attempt_count: number;
  readonly max_attempts: number;
  readonly next_retry_at: string | null;
  readonly last_attempt_at: string | null;
  readonly last_error_code: string | null;
  readonly last_error_message: string | null;
  readonly requires_network: number;
  readonly requires_auth: number;
  readonly owner_token: string | null;
  readonly lease_expires_at: string | null;
  readonly heartbeat_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly completed_at: string | null;
}

export function isTerminalStatus(status: OfflineOperationStatus): boolean {
  return status === 'COMPLETED' || status === 'FAILED_TERMINAL' || status === 'CANCELED';
}

export function isRunnableStatus(status: OfflineOperationStatus): boolean {
  return status === 'PENDING' || status === 'READY' || status === 'RETRY_WAIT';
}

export function classifyHttpOrNetworkError(input: {
  readonly code?: string | null;
  readonly httpStatus?: number | null;
  readonly message?: string | null;
}): OfflineErrorClass {
  const code = (input.code ?? '').toUpperCase();
  const msg = (input.message ?? '').toLowerCase();
  const status = input.httpStatus ?? null;

  if (
    code.includes('AUTH') ||
    code === 'UNAUTHORIZED' ||
    status === 401 ||
    msg.includes('authentication') ||
    msg.includes('unauthorized')
  ) {
    return 'auth';
  }

  if (
    code.includes('STALE') ||
    code.includes('CONFLICT') ||
    code.includes('IDEMPOTENCY') ||
    status === 409 ||
    status === 412
  ) {
    return 'conflict';
  }

  if (
    code.includes('MISSING') ||
    code.includes('HASH_MISMATCH') ||
    code.includes('INVALID') ||
    code.includes('FORBIDDEN') ||
    code.includes('SCOPE') ||
    code.includes('UNSUPPORTED') ||
    code.includes('CORRUPT') ||
    status === 400 ||
    status === 403 ||
    status === 404 ||
    status === 422
  ) {
    return 'terminal';
  }

  if (
    status === 429 ||
    status === 502 ||
    status === 503 ||
    status === 504 ||
    code.includes('TIMEOUT') ||
    code.includes('NETWORK') ||
    code.includes('UNAVAILABLE') ||
    msg.includes('network') ||
    msg.includes('timeout') ||
    msg.includes('econnreset')
  ) {
    return 'retryable';
  }

  return 'retryable';
}

export function buildIdempotencyKey(
  type: OfflineOperationType,
  parts: readonly string[],
): string {
  const prefix: Record<OfflineOperationType, string> = {
    UPLOAD_ASSET: 'upload',
    SYNC_AUTHORITATIVE_RESULT: 'auth-sync',
    START_SERVER_PROCESSING: 'process',
    APPLY_LOCAL_RESULTS: 'apply',
    FINALIZE_AISLE: 'finalize',
    CREATE_SERVER_REPROCESS: 'reprocess',
    ADOPT_SERVER_PROPOSALS: 'adoption',
    SYNC_AISLE_REVISION: 'revision-sync',
    APPLY_AISLE_REVISION: 'revision-apply',
  };
  return `${prefix[type]}:${parts.filter(Boolean).join(':')}`;
}
