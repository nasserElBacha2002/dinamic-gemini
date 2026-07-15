import type { UploadErrorCode } from './bulkUpload.types';

const TRANSIENT_HTTP = new Set([408, 429, 500, 502, 503, 504]);

export function isTransientHttpStatus(status: number): boolean {
  return TRANSIENT_HTTP.has(status);
}

export function isRetryableUploadErrorCode(code: UploadErrorCode | undefined): boolean {
  if (!code) return true;
  return code === 'TIMEOUT' || code === 'NETWORK_ERROR' || code === 'STORAGE_ERROR' || code === 'UNKNOWN';
}

export function mapHttpStatusToUploadErrorCode(status: number): UploadErrorCode {
  if (status === 401) return 'UNAUTHORIZED';
  if (status === 403) return 'FORBIDDEN';
  if (status === 408 || status === 504) return 'TIMEOUT';
  if (status === 413) return 'REQUEST_TOO_LARGE';
  if (status === 502 || status === 503) return 'NETWORK_ERROR';
  return 'UNKNOWN';
}

/** Exponential backoff with full jitter. */
export function retryDelayMs(attempt: number, baseDelayMs: number): number {
  const exp = Math.max(0, attempt - 1);
  const ceiling = baseDelayMs * 2 ** exp;
  return Math.floor(Math.random() * (ceiling + 1));
}

export async function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return;
  await new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}
