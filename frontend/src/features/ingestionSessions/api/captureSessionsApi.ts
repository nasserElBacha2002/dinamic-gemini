import { V3_INVENTORIES_BASE } from '../../../constants/v3ApiPaths';
import { getStoredToken } from '../../auth/storage';
import { ApiError } from '../../../api/types';
import i18n from '../../../i18n';
import { messageFromErrorDetail } from '../../../api/http';
import { apiRequestJson } from '../../../api/request';
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
  return apiRequestJson<PaginatedCaptureSessionListResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/capture-sessions${buildCaptureSessionsQuery(params)}`
  );
}

export async function createCaptureSession(
  inventoryId: string,
  aisleId?: string
): Promise<CaptureSessionResponse> {
  const resolvedAisleId = (aisleId || "").trim();
  const path = resolvedAisleId
    ? `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(resolvedAisleId)}/capture-sessions`
    : `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions`;
  return apiRequestJson<CaptureSessionResponse>(path, { method: 'POST' });
}

export async function getCaptureSessionDetail(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionDetailResponse> {
  return apiRequestJson<CaptureSessionDetailResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}`
  );
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
  return apiRequestJson<CaptureSessionDetailResponse>(path, { method: 'POST' });
}

export async function cancelCaptureSession(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionDetailResponse> {
  return apiRequestJson<CaptureSessionDetailResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/cancel`,
    { method: 'POST' }
  );
}

export async function getCaptureSessionGroups(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionGroupsListResponse> {
  return apiRequestJson<CaptureSessionGroupsListResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups`
  );
}

export async function computeCaptureSessionGroups(
  inventoryId: string,
  sessionId: string
): Promise<CaptureSessionGroupsListResponse> {
  return apiRequestJson<CaptureSessionGroupsListResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/compute-groups`,
    { method: 'POST' }
  );
}

export async function assignCaptureSessionGroupToExistingAisle(
  inventoryId: string,
  sessionId: string,
  groupId: string,
  aisleId: string
): Promise<CaptureSessionGroupsListResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/assign-existing`;
  return apiRequestJson<CaptureSessionGroupsListResponse>(base, {
    method: 'POST',
    body: { aisle_id: aisleId },
  });
}

export async function createAisleFromCaptureSessionGroup(
  inventoryId: string,
  sessionId: string,
  groupId: string,
  code: string,
  client_supplier_id: string
): Promise<CaptureSessionGroupsListResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/create-aisle`;
  return apiRequestJson<CaptureSessionGroupsListResponse>(base, {
    method: 'POST',
    body: { code, client_supplier_id },
  });
}

export async function materializeCaptureSessionGroup(
  inventoryId: string,
  sessionId: string,
  groupId: string
): Promise<MaterializeCaptureSessionGroupResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/materialize`;
  return apiRequestJson<MaterializeCaptureSessionGroupResponse>(base, { method: 'POST' });
}

export async function previewMaterializedCaptureSessionGroup(
  inventoryId: string,
  sessionId: string,
  groupId: string
): Promise<MaterializedCaptureSessionGroupPreviewResponse> {
  const base = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/capture-sessions/${encodeURIComponent(sessionId)}/groups/${encodeURIComponent(groupId)}/preview`;
  return apiRequestJson<MaterializedCaptureSessionGroupPreviewResponse>(base, { method: 'POST' });
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

/** Uses ``XMLHttpRequest`` (not ``fetch`` / ``apiRequestJson``) so ``xhr.upload`` can report upload progress; keep separate from generic helpers. */
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
      let body: Record<string, unknown>;
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
        new ApiError(messageFromErrorDetail(body.detail, xhr.statusText || i18n.t('errors.request_failed')), xhr.status, {
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

