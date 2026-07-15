import { V3_INVENTORIES_BASE } from '../../../constants/v3ApiPaths';
import { UPLOAD_LIMITS, CAPTURE_STAGING_MAX_FILES_PER_REQUEST } from '../../uploads/bulkUpload.config';
import type { BulkUploadServerBatchResult } from '../../uploads/bulkUpload.types';
import { xhrMultipartUpload } from '../../uploads/xhrMultipartUpload';
import { ApiError } from '../../../api/types';
import i18n from '../../../i18n';
import { buildQueryString } from '../../../api/queryString';
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

export { CAPTURE_STAGING_MAX_FILES_PER_REQUEST };

export interface CaptureSessionsListQuery {
  inventoryId: string;
  aisleId?: string;
  page?: number;
  pageSize?: number;
  statusCsv?: string;
}

/** Wire capture-session list query — `page` / `pageSize` use `{ min: 1 }` (same as legacy `> 0` for integer pages). */
export function buildCaptureSessionsQuery(params: CaptureSessionsListQuery): string {
  return buildQueryString([
    ['aisle_id', params.aisleId],
    ['status', params.statusCsv],
    ['page', params.page, { min: 1 }],
    ['page_size', params.pageSize, { min: 1 }],
  ]);
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
      client_file_id: typeof r.client_file_id === 'string' ? r.client_file_id : null,
    };
  });
  return { items, errors };
}

export async function uploadCaptureSessionStagingBatch(args: {
  inventoryId: string;
  sessionId: string;
  files: File[];
  clientFileIds: string[];
  uploadBatchId: string;
  aisleId?: string;
  signal?: AbortSignal;
  onProgress?: (loaded: number, total: number) => void;
}): Promise<UploadCaptureSessionItemsResponse> {
  if (!args.files.length) {
    throw new ApiError(i18n.t('errors.request_failed'));
  }
  if (args.files.length > UPLOAD_LIMITS.maxFilesPerRequest) {
    throw new ApiError(`At most ${UPLOAD_LIMITS.maxFilesPerRequest} files per request`);
  }
  const form = new FormData();
  form.append('upload_batch_id', args.uploadBatchId);
  for (const id of args.clientFileIds) {
    form.append('client_file_ids', id);
  }
  for (const f of args.files) {
    form.append('files', f, f.name);
  }
  const resolvedAisleId = (args.aisleId || '').trim();
  const path = resolvedAisleId
    ? `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(args.inventoryId)}/aisles/${encodeURIComponent(resolvedAisleId)}/capture-sessions/${encodeURIComponent(args.sessionId)}/items`
    : `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(args.inventoryId)}/capture-sessions/${encodeURIComponent(args.sessionId)}/items`;
  const raw = await xhrMultipartUpload<Record<string, unknown>>({
    url: path,
    form,
    signal: args.signal,
    onProgress: args.onProgress,
  });
  return parseUploadStagingResponse(raw);
}

export function stagingResponseToOutcomes(
  body: UploadCaptureSessionItemsResponse,
  clientFileIds: string[]
): BulkUploadServerBatchResult {
  const outcomes: BulkUploadServerBatchResult['outcomes'] = [];
  const errByClient = new Map(
    body.errors
      .filter((e) => e.client_file_id)
      .map((e) => [e.client_file_id as string, e])
  );
  const errByIndex = new Map(body.errors.map((e) => [e.file_index, e]));
  let itemCursor = 0;
  for (let i = 0; i < clientFileIds.length; i++) {
    const clientId = clientFileIds[i];
    const err = errByClient.get(clientId) ?? errByIndex.get(i);
    if (err) {
      outcomes.push({
        clientFileId: clientId,
        status: 'failed',
        code: err.code,
        message: err.detail,
      });
      continue;
    }
    const item = body.items[itemCursor++];
    if (!item) {
      outcomes.push({
        clientFileId: clientId,
        status: 'failed',
        code: 'UNKNOWN',
        message: 'Missing server item for this file',
      });
      continue;
    }
    if (item.import_status !== 'imported') {
      outcomes.push({
        clientFileId: clientId,
        status: 'failed',
        serverId: item.id,
        code: item.last_error_code ?? item.import_status,
        message: item.last_error_detail ?? item.import_status,
      });
      continue;
    }
    outcomes.push({
      clientFileId: clientId,
      status: 'completed',
      serverId: item.id,
    });
  }
  return { outcomes };
}

/** Uses shared XHR transport; prefers ``uploadCaptureSessionStagingBatch`` from the bulk uploader. */
export async function uploadCaptureSessionStagingFiles(
  inventoryId: string,
  sessionId: string,
  files: File[],
  aisleId?: string,
  onProgress?: (progressPct: number) => void
): Promise<UploadCaptureSessionItemsResponse> {
  const clientFileIds = files.map((_, i) => `legacy-${i}-${Date.now()}`);
  return uploadCaptureSessionStagingBatch({
    inventoryId,
    sessionId,
    files,
    clientFileIds,
    uploadBatchId: `legacy-batch-${Date.now()}`,
    aisleId,
    onProgress: (loaded, total) => {
      if (!onProgress || total <= 0) return;
      onProgress(Math.min(100, Math.round((loaded / total) * 100)));
    },
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

