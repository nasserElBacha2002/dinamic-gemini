/** Stable server error codes for preliminary sync classification. */
export const PRELIMINARY_INGEST_DISABLED = 'PRELIMINARY_INGEST_DISABLED';
export const PRELIMINARY_ASSET_PENDING = 'PRELIMINARY_ASSET_PENDING';
export const PRELIMINARY_VALIDATION_FAILED = 'PRELIMINARY_VALIDATION_FAILED';
export const PRELIMINARY_IDEMPOTENCY_CONFLICT = 'PRELIMINARY_IDEMPOTENCY_CONFLICT';
export const PRELIMINARY_FORBIDDEN = 'PRELIMINARY_FORBIDDEN';

export type PreliminarySyncOutcome =
  | 'synced'
  | 'retry'
  | 'rejected'
  | 'conflict'
  | 'failed_terminal'
  | 'not_ready'
  | 'skipped_lease';

export type PreliminarySyncHttpClass =
  | { readonly kind: 'retry'; readonly errorCode: string; readonly delayMs: number }
  | { readonly kind: 'rejected'; readonly errorCode: string }
  | { readonly kind: 'conflict'; readonly errorCode: string }
  | { readonly kind: 'failed_terminal'; readonly errorCode: string }
  | { readonly kind: 'feature_unavailable'; readonly errorCode: string; readonly delayMs: number }
  | { readonly kind: 'pending_asset'; readonly errorCode: string; readonly delayMs: number };

export function classifyPreliminarySyncError(input: {
  readonly status: number | null;
  readonly code: string | null;
  readonly attempt: number;
  readonly computeDelayMs: (attempt: number) => number;
}): PreliminarySyncHttpClass {
  const { status, code, attempt, computeDelayMs } = input;
  if (code === PRELIMINARY_VALIDATION_FAILED || status === 422) {
    return { kind: 'rejected', errorCode: code ?? 'PRELIMINARY_VALIDATION_FAILED' };
  }
  if (code === PRELIMINARY_IDEMPOTENCY_CONFLICT || status === 409) {
    return { kind: 'conflict', errorCode: code ?? 'PRELIMINARY_IDEMPOTENCY_CONFLICT' };
  }
  if (code === PRELIMINARY_FORBIDDEN || status === 403) {
    return { kind: 'failed_terminal', errorCode: code ?? 'PRELIMINARY_FORBIDDEN' };
  }
  if (code === PRELIMINARY_INGEST_DISABLED) {
    return {
      kind: 'feature_unavailable',
      errorCode: PRELIMINARY_INGEST_DISABLED,
      delayMs: 15 * 60_000,
    };
  }
  if (code === PRELIMINARY_ASSET_PENDING || status === 404) {
    if (code === PRELIMINARY_ASSET_PENDING) {
      return { kind: 'pending_asset', errorCode: PRELIMINARY_ASSET_PENDING, delayMs: 30_000 };
    }
    // Untyped 404/405 from old backends → treat as feature unavailable
    if (status === 404 || status === 405) {
      return {
        kind: 'feature_unavailable',
        errorCode: 'FEATURE_UNAVAILABLE',
        delayMs: 15 * 60_000,
      };
    }
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
