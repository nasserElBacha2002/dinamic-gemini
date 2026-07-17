export type UploadErrorClass =
  | 'retryable'
  | 'auth'
  | 'forbidden'
  | 'not_found'
  | 'conflict_reconcile'
  | 'conflict_blocked'
  | 'payload_too_large'
  | 'unsupported_media'
  | 'validation'
  | 'permanent'
  | 'unknown';

export function classifyUploadHttpError(status: number | null, code: string | null): UploadErrorClass {
  if (status === null) {
    return 'retryable';
  }
  if (status === 401) {
    return 'auth';
  }
  if (status === 403) {
    return 'forbidden';
  }
  if (status === 404) {
    return 'not_found';
  }
  if (status === 408 || status === 429 || status === 500 || status === 502 || status === 503 || status === 504) {
    return 'retryable';
  }
  if (status === 409) {
    if (code === 'ACTIVE_JOB_EXISTS' || code === 'AISLE_SOURCE_ASSET_MUTATION_BLOCKED') {
      return 'conflict_blocked';
    }
    return 'conflict_reconcile';
  }
  if (status === 413 || code === 'UPLOAD_FILE_TOO_LARGE' || code === 'UPLOAD_REQUEST_TOO_LARGE') {
    return 'payload_too_large';
  }
  if (status === 415 || code === 'UNSUPPORTED_ASSET_TYPE') {
    return 'unsupported_media';
  }
  if (status === 422 || status === 400) {
    return 'validation';
  }
  if (status >= 500) {
    return 'retryable';
  }
  return 'unknown';
}

export function isSoftPerFileRetryable(code: string | null): boolean {
  if (!code) {
    return true;
  }
  if (code === 'UNSUPPORTED_ASSET_TYPE' || code === 'ZERO_BYTE_FILE') {
    return false;
  }
  if (code === 'UPLOAD_FILE_TOO_LARGE') {
    return false;
  }
  return true;
}
