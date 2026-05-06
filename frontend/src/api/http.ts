import { getStoredToken } from '../features/auth/storage';
import i18n from '../i18n';
import type { ApiErrorDetail } from './types';
import { ApiError } from './types';

/** Fetch for protected endpoints. Adds Authorization header when token exists. */
export function protectedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const token = getStoredToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

interface ValidationDetailItem {
  msg?: string;
  loc?: unknown;
  type?: string;
}

export function parseResponseJson<T>(text: string): T {
  try {
    return (text ? JSON.parse(text) : {}) as T;
  } catch {
    return {} as T;
  }
}

export function messageFromErrorDetail(
  detail: unknown,
  fallback: string
): string {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === 'object' && typeof (first as ValidationDetailItem).msg === 'string') {
      const msg = (first as ValidationDetailItem).msg!.trim();
      if (msg) return msg;
    }
    return i18n.t('errors.validation_generic');
  }
  return fallback;
}

/** Throws ApiError for non-OK responses. */
export function throwApiErrorIfNotOk(response: Response, text: string, data: ApiErrorDetail): never {
  const message = messageFromErrorDetail(
    data.detail,
    text && text.length < 200 ? text : response.statusText || i18n.t('errors.request_failed')
  );
  throw new ApiError(message, response.status, data);
}

export async function handleResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = parseResponseJson<ApiErrorDetail & T>(text);
  if (!response.ok) {
    throwApiErrorIfNotOk(response, text, data);
  }
  return data as T;
}

export function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* ignore */
    }
  }
  const quoted = /filename\s*=\s*"([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1].trim();
  return fallback;
}
