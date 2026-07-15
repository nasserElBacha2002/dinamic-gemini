import { getStoredToken } from '../auth/storage';
import { messageFromErrorDetail, parseResponseJson } from '../../api/http';
import { ApiError } from '../../api/types';
import i18n from '../../i18n';
import { UPLOAD_LIMITS } from './bulkUpload.config';
import { mapHttpStatusToUploadErrorCode } from './uploadRetryPolicy';

export interface MultipartUploadRequestOptions {
  url: string;
  form: FormData;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
  onProgress?: (loaded: number, total: number) => void;
}

/**
 * Shared XHR multipart transport with upload progress, auth, abort, and timeout.
 * Used by aisle and capture-session bulk uploads.
 */
export function xhrMultipartUpload<T>(options: MultipartUploadRequestOptions): Promise<T> {
  const { url, form, signal, onProgress, headers: extraHeaders } = options;
  const timeoutMs = options.timeoutMs ?? UPLOAD_LIMITS.requestTimeoutMs;

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    const token = getStoredToken();
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    if (extraHeaders) {
      for (const [k, v] of Object.entries(extraHeaders)) {
        xhr.setRequestHeader(k, v);
      }
    }

    if (timeoutMs > 0) {
      xhr.timeout = timeoutMs;
    }

    const onAbort = () => {
      xhr.abort();
    };
    signal?.addEventListener('abort', onAbort);

    xhr.upload.onprogress = (event: ProgressEvent<EventTarget>) => {
      if (!event.lengthComputable || !onProgress) return;
      onProgress(event.loaded, event.total);
    };

    xhr.ontimeout = () => {
      signal?.removeEventListener('abort', onAbort);
      reject(new ApiError(i18n.t('errors.request_failed'), 408, { code: 'TIMEOUT' }));
    };

    xhr.onerror = () => {
      signal?.removeEventListener('abort', onAbort);
      reject(new ApiError(i18n.t('errors.request_failed'), 0, { code: 'NETWORK_ERROR' }));
    };

    xhr.onabort = () => {
      signal?.removeEventListener('abort', onAbort);
      reject(new DOMException('Aborted', 'AbortError'));
    };

    xhr.onload = () => {
      signal?.removeEventListener('abort', onAbort);
      const body = parseResponseJson<Record<string, unknown>>(xhr.responseText || '');
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T);
        return;
      }
      const code = mapHttpStatusToUploadErrorCode(xhr.status);
      const message = messageFromErrorDetail(
        body.detail,
        xhr.statusText || i18n.t('errors.request_failed')
      );
      reject(
        new ApiError(message, xhr.status, {
          code: typeof body.code === 'string' ? body.code : code,
          detail: body.detail,
        })
      );
    };

    xhr.send(form);
  });
}
