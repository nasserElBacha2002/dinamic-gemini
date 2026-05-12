/**
 * Higher-level JSON, void, and blob-download helpers built on ``protectedFetch`` + ``handleResponse``.
 *
 * **F0 conventions (Dinamic v3 frontend API layer)**
 *
 * - **JSON** (GET/POST/PUT/PATCH with JSON bodies or JSON responses): prefer {@link apiRequestJson}.
 * - **Browser file download** (CSV, TXT, anchor + object URL): prefer {@link apiDownloadBlob}.
 * - **Success with no meaningful body** (void actions, typical ``response.ok``): prefer {@link apiRequestVoid}.
 * - **Simple multipart uploads** (no progress): use {@link apiRequestJson} with ``body: FormData`` (never set ``Content-Type`` for FormData).
 * - **Upload progress**: keep ``XMLHttpRequest`` (or other explicit paths) outside this module; ``fetch`` has no standard upload progress.
 * - **Auth**, **evidence/blob preview**, **DELETE with non-standard success** (e.g. 204-only): may keep direct ``protectedFetch`` / ``fetch`` in their modules; see ``http.ts`` for primitives.
 *
 * Do not remove or bypass ``protectedFetch`` / ``handleResponse`` here; helpers delegate to them for one ``ApiError`` pipeline.
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

/** Same body/header rules as {@link apiRequestJson}; successful responses ignore the parsed body. */
export type ApiRequestVoidOptions = ApiRequestJsonOptions;

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== 'undefined' && body instanceof FormData;
}

function isBinaryLikeBody(body: unknown): boolean {
  if (typeof Blob !== 'undefined' && body instanceof Blob) return true;
  if (typeof ArrayBuffer !== 'undefined' && body instanceof ArrayBuffer) return true;
  return typeof ArrayBuffer !== 'undefined' && ArrayBuffer.isView(body as ArrayBufferView);
}

/** Shared ``RequestInit`` for ``apiRequestJson`` / ``apiRequestVoid`` (body normalization only). */
function buildProtectedFetchInitFromApiRequestOptions(options: ApiRequestJsonOptions): RequestInit {
  const { body, headers: inputHeaders, ...rest } = options;
  const headers = new Headers(inputHeaders);

  let outgoingBody: BodyInit | undefined;

  if (body === undefined) {
    outgoingBody = undefined;
  } else if (isFormData(body)) {
    outgoingBody = body;
    // Let the browser set multipart boundary; never forward a caller Content-Type.
    headers.delete('Content-Type');
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

  return {
    ...rest,
    headers,
    body: outgoingBody,
  };
}

/**
 * Authenticated fetch with JSON-friendly defaults: merges headers, stringifies plain objects,
 * and parses responses via ``handleResponse`` (same ``ApiError`` pipeline as direct callers).
 *
 * - For ``FormData``: does **not** set ``Content-Type`` and **removes** any caller ``Content-Type`` so the boundary is browser-managed.
 * - Does **not** stringify ``FormData`` / ``Blob`` / typed arrays.
 * - **String** ``body`` is sent **as-is** (e.g. pre-serialized JSON). No default ``Content-Type`` is set;
 *   set ``Content-Type`` in ``headers`` when the server requires it.
 * - Object/array/primitive JSON bodies: ``JSON.stringify`` plus ``Content-Type: application/json`` only
 *   when ``Content-Type`` is not already set.
 */
export async function apiRequestJson<T>(url: string, options: ApiRequestJsonOptions = {}): Promise<T> {
  const response = await protectedFetch(url, buildProtectedFetchInitFromApiRequestOptions(options));
  return handleResponse<T>(response);
}

/**
 * Like {@link apiRequestJson} for request preparation, but discards the response body on success.
 * Uses ``handleResponse`` so errors match the same ``ApiError`` path; ``204`` / empty / ``202`` / ``200`` OK bodies are ignored.
 */
export async function apiRequestVoid(url: string, options: ApiRequestVoidOptions = {}): Promise<void> {
  const response = await protectedFetch(url, buildProtectedFetchInitFromApiRequestOptions(options));
  await handleResponse<unknown>(response);
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
