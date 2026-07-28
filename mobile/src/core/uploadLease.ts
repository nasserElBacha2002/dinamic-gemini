/**
 * Phase 2 — upload lease ownership + shared contracts with Kotlin UploadContracts.
 */

export const UPLOAD_WORKER_OWNER_JS = 'js';
export const UPLOAD_WORKER_OWNER_NATIVE = 'native';

/** Lease TTL before another owner may reclaim (ms). Keep in sync with UploadContracts.LEASE_TTL_MS. */
export const UPLOAD_LEASE_TTL_MS = 180_000;

/** Stable error / state codes shared with native worker. */
export const UPLOAD_CODE_AUTH_REQUIRED = 'AUTH_REQUIRED';
export const UPLOAD_CODE_AUTH_VAULT_UNAVAILABLE = 'AUTH_VAULT_UNAVAILABLE';
export const UPLOAD_CODE_DB_MIGRATION_REQUIRED = 'DB_MIGRATION_REQUIRED';
export const UPLOAD_CODE_UPLOAD_REPREPARE_REQUIRED = 'UPLOAD_REPREPARE_REQUIRED';
export const UPLOAD_CODE_REQUEST_TIMEOUT = 'REQUEST_TIMEOUT';
export const UPLOAD_CODE_REQUEST_CANCELLED = 'REQUEST_CANCELLED';
export const UPLOAD_CODE_NETWORK_ERROR = 'NETWORK_ERROR';
export const UPLOAD_CODE_FILE_MISSING = 'FILE_MISSING';
export const UPLOAD_CODE_TLS_ERROR = 'TLS_ERROR';
export const UPLOAD_CODE_RESPONSE_PARSE_ERROR = 'RESPONSE_PARSE_ERROR';
export const UPLOAD_CODE_PAUSED = 'PAUSED';
export const UPLOAD_CODE_PROCESS_PENDING = 'PROCESS_PENDING';

export const UPLOAD_MULTIPART_FIELD_BATCH = 'upload_batch_id';
export const UPLOAD_MULTIPART_FIELD_CLIENT_IDS = 'client_file_ids';
export const UPLOAD_MULTIPART_FIELD_FILES = 'files';

export function isUploadLeaseActive(
  leaseExpiresAt: string | null | undefined,
  nowMs: number = Date.now(),
): boolean {
  if (!leaseExpiresAt) {
    return false;
  }
  const expires = Date.parse(leaseExpiresAt);
  if (!Number.isFinite(expires)) {
    return false;
  }
  return expires > nowMs;
}

/** True when a foreign owner holds a non-expired lease. */
export function hasForeignUploadLease(input: {
  readonly workerOwner: string | null | undefined;
  readonly leaseExpiresAt: string | null | undefined;
  readonly selfOwner: string;
  readonly nowMs?: number;
}): boolean {
  if (!input.workerOwner || input.workerOwner === input.selfOwner) {
    return false;
  }
  return isUploadLeaseActive(input.leaseExpiresAt, input.nowMs);
}

export function leaseExpiresAtIso(fromMs: number = Date.now(), ttlMs: number = UPLOAD_LEASE_TTL_MS): string {
  return new Date(fromMs + ttlMs).toISOString();
}

export const UNIQUE_UPLOAD_QUEUE_WORK = 'dinamic-upload-queue';

export function uniqueUploadSessionWorkName(sessionId: string): string {
  return `dinamic-upload-session-${sessionId}`;
}
