/** Stable server error codes for authoritative local sync classification. */
export const AUTH_INGEST_DISABLED = 'AUTHORITATIVE_INGEST_DISABLED';
export const AUTH_VALIDATION_FAILED = 'AUTHORITATIVE_VALIDATION_FAILED';
export const AUTH_IDEMPOTENCY_CONFLICT = 'AUTHORITATIVE_IDEMPOTENCY_CONFLICT';
export const AUTH_ASSET_MISMATCH = 'AUTHORITATIVE_ASSET_MISMATCH';
export const AUTH_FORBIDDEN = 'AUTHORITATIVE_FORBIDDEN';

export type AuthoritativeSyncOutcome =
  | 'synced'
  | 'retry'
  | 'rejected'
  | 'conflict'
  | 'failed_terminal'
  | 'not_ready'
  | 'endpoint_missing'
  | 'skipped_lease';

export type AuthoritativeSyncHttpClass =
  | { readonly kind: 'retry'; readonly errorCode: string; readonly delayMs: number }
  | { readonly kind: 'rejected'; readonly errorCode: string }
  | { readonly kind: 'conflict'; readonly errorCode: string }
  | { readonly kind: 'failed_terminal'; readonly errorCode: string }
  | { readonly kind: 'endpoint_missing'; readonly errorCode: string; readonly delayMs: number }
  | { readonly kind: 'pending_asset'; readonly errorCode: string; readonly delayMs: number };

export function classifyAuthoritativeSyncError(input: {
  readonly status: number | null;
  readonly code: string | null;
  readonly attempt: number;
  readonly computeDelayMs: (attempt: number) => number;
}): AuthoritativeSyncHttpClass {
  const { status, code, attempt, computeDelayMs } = input;
  if (code === AUTH_VALIDATION_FAILED || status === 422) {
    return { kind: 'rejected', errorCode: code ?? AUTH_VALIDATION_FAILED };
  }
  if (code === AUTH_IDEMPOTENCY_CONFLICT || status === 409) {
    return { kind: 'conflict', errorCode: code ?? AUTH_IDEMPOTENCY_CONFLICT };
  }
  if (code === AUTH_FORBIDDEN || status === 403) {
    return { kind: 'failed_terminal', errorCode: code ?? AUTH_FORBIDDEN };
  }
  if (code === AUTH_INGEST_DISABLED) {
    return {
      kind: 'endpoint_missing',
      errorCode: AUTH_INGEST_DISABLED,
      delayMs: 15 * 60_000,
    };
  }
  if (code === AUTH_ASSET_MISMATCH) {
    return { kind: 'pending_asset', errorCode: AUTH_ASSET_MISMATCH, delayMs: 30_000 };
  }
  if (status === 404 || status === 405) {
    return {
      kind: 'endpoint_missing',
      errorCode: code ?? 'FEATURE_UNAVAILABLE',
      delayMs: 15 * 60_000,
    };
  }
  if (status === 401 || status === 429 || (status != null && status >= 500) || status === null) {
    return {
      kind: 'retry',
      errorCode: status != null ? `HTTP_${status}` : code ?? 'NETWORK_ERROR',
      delayMs: computeDelayMs(attempt),
    };
  }
  return {
    kind: 'failed_terminal',
    errorCode: status != null ? `HTTP_${status}` : code ?? 'SYNC_ERROR',
  };
}
