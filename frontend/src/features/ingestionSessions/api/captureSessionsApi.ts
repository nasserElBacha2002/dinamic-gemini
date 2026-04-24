import { V3_INVENTORIES_BASE } from '../../../constants/v3ApiPaths';
import { getStoredToken } from '../../auth/storage';
import { ApiError } from '../../../api/types';
import i18n from '../../../i18n';
import type {
  CaptureSessionDetailResponse,
  CaptureSessionGroupsListResponse,
  CaptureSessionResponse,
  MaterializedCaptureSessionGroupPreviewResponse,
  MaterializeCaptureSessionGroupResponse,
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
  sessionId: string,
  aisleId?: string
): Promise<CaptureSessionDetailResponse> {
  const resolvedAisleId = (aisleId || "").trim();
  const path = resolvedAisleId
    ? `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(resolvedAisleId)}/capture-sessions/${encodeURIComponent(sessionId)}/close`
    : `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/close`;
  const response = await protectedFetch(path, { method: 'POST' });
  return handleResponse<CaptureSessionDetailResponse>(response);
}

export async function cancelCaptureSession(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionDetailResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/cancel`,
    { method: 'POST' }
  );
  return handleResponse<CaptureSessionDetailResponse>(response);
}

export async function getCaptureSessionGroups(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionGroupsListResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups`
  );
  return handleResponse<CaptureSessionGroupsListResponse>(response);
}

export async function computeCaptureSessionGroups(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionGroupsListResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/compute-groups`,
    { method: 'POST' }
  );
  return handleResponse<CaptureSessionGroupsListResponse>(response);
}

export async function assignCaptureSessionGroupToExistingAisle(
  inventoryId: string,
  sessionId: string,
  groupId: string,
  aisleId: string
): Promise<CaptureSessionGroupsListResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/assign-existing`;
  const response = await protectedFetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ aisle_id: aisleId }),
  });
  return handleResponse<CaptureSessionGroupsListResponse>(response);
}

export async function createAisleFromCaptureSessionGroup(
  inventoryId: string,
  sessionId: string,
  groupId: string,
  code: string
): Promise<CaptureSessionGroupsListResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/create-aisle`;
  const response = await protectedFetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  return handleResponse<CaptureSessionGroupsListResponse>(response);
}

export async function materializeCaptureSessionGroup(
  inventoryId: string,
  sessionId: string,
  groupId: string
): Promise<MaterializeCaptureSessionGroupResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/materialize`;
  const response = await protectedFetch(base, { method: 'POST' });
  return handleResponse<MaterializeCaptureSessionGroupResponse>(response);
}

export async function previewMaterializedCaptureSessionGroup(
  inventoryId: string,
  sessionId: string,
  groupId: string
): Promise<MaterializedCaptureSessionGroupPreviewResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/preview`;
  const response = await protectedFetch(base, { method: 'POST' });
  return handleResponse<MaterializedCaptureSessionGroupPreviewResponse>(response);
}

/**
 * Max files per staging POST (matches backend ``v3_capture_max_files_per_upload``, default 50).
 * The ingestion hook sends **multiple sequential** requests of at most this many files
 * when the user selects more than the limit; it does **not** issue parallel POSTs for
 * different chunks (see ``useUploadCaptureItems``).
 */
export const CAPTURE_STAGING_MAX_FILES_PER_REQUEST = 50;

function parseUploadStagingResponse(body: Record<string, unknown>): UploadCaptureSessionItemsResponse {
  const items = Array.isArray(body.items) ? (body.items as UploadCaptureSessionItemsResponse['items']) : [];
  const rawErrors = Array.isArray(body.errors) ? body.errors : [];
  const errors = rawErrors.map((row) => {
    const r = row as Record<string, unknown>;
    return {
      filename: typeof r.filename === 'string' ? r.filename : 'file',
      code: typeof r.code === 'string' ? r.code : 'UNKNOWN',
      detail: typeof r.detail === 'string' ? r.detail : '',
      file_index: typeof r.file_index === 'number' && Number.isFinite(r.file_index) ? r.file_index : 0,
    };
  });
  return { items, errors };
}

export async function uploadCaptureSessionStagingFiles(
  inventoryId: string,
  sessionId: string,
  files: File[],
  aisleId?: string,
  onProgress?: (progressPct: number) => void
): Promise<UploadCaptureSessionItemsResponse> {
  if (!files.length) {
    throw new ApiError(i18n.t('errors.request_failed'));
  }
  const token = getStoredToken();
  const form = new FormData();
  for (const f of files) {
    form.append('files', f, f.name);
  }
  return new Promise<UploadCaptureSessionItemsResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const resolvedAisleId = (aisleId || '').trim();
    const path = resolvedAisleId
      ? `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(resolvedAisleId)}/capture-sessions/${encodeURIComponent(sessionId)}/items`
      : `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/items`;
    xhr.open('POST', path);
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
        resolve(parseUploadStagingResponse(body));
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

/** @deprecated Prefer ``uploadCaptureSessionStagingFiles`` with a one-element array. */
export async function uploadCaptureItem(
  inventoryId: string,
  sessionId: string,
  file: File,
  aisleId?: string,
  onProgress?: (progressPct: number) => void
): Promise<UploadCaptureSessionItemsResponse> {
  return uploadCaptureSessionStagingFiles(inventoryId, sessionId, [file], aisleId, onProgress);
}

