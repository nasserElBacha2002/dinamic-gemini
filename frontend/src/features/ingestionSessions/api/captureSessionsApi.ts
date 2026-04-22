import { V3_INVENTORIES_BASE } from '../../../constants/v3ApiPaths';
import { getStoredToken } from '../../auth/storage';
import { ApiError } from '../../../api/types';
import i18n from '../../../i18n';
import type {
  CaptureSessionDetailResponse,
  CaptureSessionResponse,
  UploadCaptureSessionItemsResponse,
  PaginatedCaptureSessionListResponse,
} from '../../../types/captureSession';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

function protectedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const token = getStoredToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

function getErrorMessage(detail: unknown, statusText: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown } | undefined;
    if (typeof first?.msg === 'string' && first.msg.trim()) return first.msg.trim();
  }
  return statusText || i18n.t('errors.request_failed');
}

async function handleResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  let data: Record<string, unknown> = {};
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    data = {};
  }
  if (!response.ok) {
    throw new ApiError(getErrorMessage(data.detail, response.statusText), response.status, {
      code: typeof data.code === 'string' ? data.code : undefined,
      detail: data.detail,
    });
  }
  return data as T;
}

export interface CaptureSessionsListQuery {
  inventoryId: string;
  aisleId?: string;
  page?: number;
  pageSize?: number;
  statusCsv?: string;
}

function buildCaptureSessionsQuery(params: CaptureSessionsListQuery): string {
  const q = new URLSearchParams();
  if (params.aisleId?.trim()) q.set('aisle_id', params.aisleId.trim());
  if (params.statusCsv?.trim()) q.set('status', params.statusCsv.trim());
  if (params.page != null && params.page > 0) q.set('page', String(params.page));
  if (params.pageSize != null && params.pageSize > 0) q.set('page_size', String(params.pageSize));
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function getCaptureSessions(params: CaptureSessionsListQuery): Promise<PaginatedCaptureSessionListResponse> {
  const inventoryId = encodeURIComponent(params.inventoryId);
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/capture-sessions${buildCaptureSessionsQuery(params)}`
  );
  return handleResponse<PaginatedCaptureSessionListResponse>(response);
}

export async function createCaptureSession(
  inventoryId: string,
  aisleId?: string
): Promise<CaptureSessionResponse> {
  const resolvedAisleId = (aisleId || "").trim();
  const path = resolvedAisleId
    ? `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(resolvedAisleId)}/capture-sessions`
    : `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions`;
  const response = await protectedFetch(path, { method: 'POST' });
  return handleResponse<CaptureSessionResponse>(response);
}

export async function getCaptureSessionDetail(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionDetailResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}`
  );
  return handleResponse<CaptureSessionDetailResponse>(response);
}

export async function closeCaptureSession(
  inventoryId: string,
  aisleId: string,
  sessionId: string
): Promise<CaptureSessionDetailResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/capture-sessions/${encodeURIComponent(sessionId)}/close`,
    { method: 'POST' }
  );
  return handleResponse<CaptureSessionDetailResponse>(response);
}

export async function uploadCaptureItem(
  inventoryId: string,
  aisleId: string,
  sessionId: string,
  file: File,
  onProgress?: (progressPct: number) => void
): Promise<UploadCaptureSessionItemsResponse> {
  const token = getStoredToken();
  const form = new FormData();
  form.append('files', file);
  return new Promise<UploadCaptureSessionItemsResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(
      'POST',
      `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/capture-sessions/${encodeURIComponent(sessionId)}/items`
    );
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    xhr.upload.onprogress = (event: ProgressEvent<EventTarget>) => {
      if (!event.lengthComputable || !onProgress) return;
      onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onerror = () => {
      reject(new ApiError(i18n.t('errors.request_failed')));
    };
    xhr.onload = () => {
      let body: Record<string, unknown> = {};
      try {
        body = xhr.responseText ? (JSON.parse(xhr.responseText) as Record<string, unknown>) : {};
      } catch {
        body = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        const items = Array.isArray(body.items) ? body.items : [];
        resolve({ items } as UploadCaptureSessionItemsResponse);
        return;
      }
      reject(
        new ApiError(getErrorMessage(body.detail, xhr.statusText), xhr.status, {
          code: typeof body.code === 'string' ? body.code : undefined,
          detail: body.detail,
        })
      );
    };
    xhr.send(form);
  });
}

