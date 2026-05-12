/**
 * Higher-level JSON and blob-download helpers built on ``protectedFetch`` + ``handleResponse``.
 * Phase F0.1 — keep ``http.ts`` as the low-level module; do not use these for auth or XHR uploads.
 */

import {
  filenameFromContentDisposition,
  handleResponse,
  protectedFetch,
  throwApiErrorIfNotOk,
} from './http';
import type { ApiErrorDetail } from './types';

export interface ApiRequestJsonOptions extends Omit<RequestInit, 'body'> {
  /** Plain JSON-serializable objects/arrays/primitives, ``FormData``, ``Blob``, ``ArrayBuffer``, or raw string body (no default ``Content-Type``). */
  body?: unknown;
}

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== 'undefined' && body instanceof FormData;
}

function isBinaryLikeBody(body: unknown): boolean {
  if (typeof Blob !== 'undefined' && body instanceof Blob) return true;
  if (typeof ArrayBuffer !== 'undefined' && body instanceof ArrayBuffer) return true;
  return typeof ArrayBuffer !== 'undefined' && ArrayBuffer.isView(body as ArrayBufferView);
}

/**
 * Authenticated fetch with JSON-friendly defaults: merges headers, stringifies plain objects,
 * and parses responses via ``handleResponse`` (same ``ApiError`` pipeline as direct callers).
 *
 * - Does **not** set ``Content-Type: application/json`` for ``FormData`` (browser sets multipart boundary).
 * - Does **not** stringify ``FormData`` / ``Blob`` / typed arrays.
 * - **String** ``body`` is sent **as-is** (e.g. pre-serialized JSON). No default ``Content-Type`` is set;
 *   set ``Content-Type`` in ``headers`` when the server requires it.
 * - Object/array/primitive JSON bodies: ``JSON.stringify`` plus ``Content-Type: application/json`` only
 *   when ``Content-Type`` is not already set.
 */
export async function apiRequestJson<T>(url: string, options: ApiRequestJsonOptions = {}): Promise<T> {
  const { body, headers: inputHeaders, ...rest } = options;
  const headers = new Headers(inputHeaders);

  let outgoingBody: BodyInit | undefined;

  if (body === undefined) {
    outgoingBody = undefined;
  } else if (isFormData(body)) {
    outgoingBody = body;
    const ct = headers.get('Content-Type');
    if (ct && ct.includes('application/json')) {
      headers.delete('Content-Type');
    }
  } else if (isBinaryLikeBody(body)) {
    outgoingBody = body as BodyInit;
  } else if (typeof body === 'string') {
    outgoingBody = body;
  } else {
    outgoingBody = JSON.stringify(body);
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
  }

  const response = await protectedFetch(url, {
    ...rest,
    headers,
    body: outgoingBody,
  });
  return handleResponse<T>(response);
}

export interface ApiDownloadBlobOptions extends RequestInit {
  fallbackFilename: string;
}

/**
 * Download a binary response: same error handling as existing CSV/log helpers, then blob + anchor.
 */
export async function apiDownloadBlob(url: string, options: ApiDownloadBlobOptions): Promise<void> {
  const { fallbackFilename, ...fetchInit } = options;
  const response = await protectedFetch(url, fetchInit);
  if (!response.ok) {
    const text = await response.text();
    let data: ApiErrorDetail;
    try {
      data = (text ? JSON.parse(text) : {}) as ApiErrorDetail;
    } catch {
      data = {};
    }
    throwApiErrorIfNotOk(response, text, data);
  }
  const blob = await response.blob();
  const filename = filenameFromContentDisposition(response.headers.get('Content-Disposition'), fallbackFilename);
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
