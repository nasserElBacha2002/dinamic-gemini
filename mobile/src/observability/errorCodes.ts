import type { ObservabilityErrorCode } from './types';

/**
 * Map operational / HTTP errors to the Phase 0 normalized catalog.
 * Never embeds tokens or payloads.
 */
export function normalizeObservabilityError(input: {
  readonly code?: string | null | undefined;
  readonly httpStatus?: number | null | undefined;
  readonly message?: string | null | undefined;
  readonly stage?: 'prepare' | 'upload' | 'process' | 'job' | 'queue' | 'unknown' | undefined;
}): ObservabilityErrorCode {
  const code = (input.code || '').toUpperCase();
  const msg = (input.message || '').toLowerCase();
  const stage = input.stage ?? 'unknown';
  const status = input.httpStatus;

  if (stage === 'prepare' || code.includes('PREPARE')) {
    if (msg.includes('heic') || msg.includes('convert')) {
      return 'PREPARE_CONVERSION_FAILED';
    }
    if (msg.includes('resize')) {
      return 'PREPARE_RESIZE_FAILED';
    }
    if (msg.includes('vacío') || msg.includes('empty') || msg.includes('read')) {
      return 'PREPARE_READ_FAILED';
    }
    return 'PREPARE_FAILED';
  }

  if (code === 'UPLOAD_LIMIT_EXCEEDED' || code.includes('413') || status === 413) {
    return 'UPLOAD_LIMIT_EXCEEDED';
  }
  if (code.includes('TIMEOUT') || msg.includes('timeout') || status === 408) {
    return 'UPLOAD_TIMEOUT';
  }
  if (code.includes('ABORT') || msg.includes('abort')) {
    return 'UPLOAD_ABORTED';
  }
  if (
    code === 'NETWORK_ERROR' ||
    msg.includes('network') ||
    status === null ||
    status === 0
  ) {
    if (stage === 'process') {
      return 'PROCESS_REQUEST_FAILED';
    }
    if (stage === 'job') {
      return 'JOB_POLL_FAILED';
    }
    return 'UPLOAD_NETWORK_ERROR';
  }
  if (typeof status === 'number' && status >= 500) {
    return 'UPLOAD_HTTP_5XX';
  }
  if (typeof status === 'number' && status >= 400) {
    return 'UPLOAD_HTTP_4XX';
  }
  if (stage === 'process') {
    return 'PROCESS_REQUEST_FAILED';
  }
  if (stage === 'job') {
    if (code.includes('FAIL') || msg.includes('fail')) {
      return 'JOB_TERMINAL_FAILED';
    }
    return 'JOB_POLL_FAILED';
  }
  if (stage === 'queue' || code.includes('RESTORE')) {
    return 'QUEUE_RESTORE_FAILED';
  }
  if (code.includes('RETRY')) {
    return 'UPLOAD_RETRYABLE';
  }
  return 'UNKNOWN_ERROR';
}
