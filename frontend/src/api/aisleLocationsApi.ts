import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  AisleLocation,
  AisleLocationLabel,
  AisleLocationLabelListResponse,
  AisleLocationListResponse,
  CreateAisleLocationRequest,
  InvalidateAisleLocationLabelRequest,
  IssueAisleLocationLabelRequest,
  UpdateAisleLocationRequest,
} from './types';
import { buildQueryString } from './queryString';
import { apiDownloadBlob, apiRequestJson } from './request';
import { protectedFetch, throwApiErrorIfNotOk } from './http';
import type { ApiErrorDetail } from './types';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface AisleLocationsListQuery {
  status?: string | null;
  search?: string | null;
  page?: number;
  page_size?: number;
}

function aisleLocationsBase(inventoryId: string, aisleId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/locations`;
}

function inventoryLocationLabelsBase(inventoryId: string, locationId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/locations/${encodeURIComponent(locationId)}/labels`;
}

export async function listAisleLocations(
  inventoryId: string,
  aisleId: string,
  listQuery?: AisleLocationsListQuery
): Promise<AisleLocationListResponse> {
  const qs = buildQueryString([
    ['status', listQuery?.status],
    ['search', listQuery?.search],
    ['page', listQuery?.page, { min: 1 }],
    ['page_size', listQuery?.page_size, { min: 1 }],
  ]);
  return apiRequestJson<AisleLocationListResponse>(`${aisleLocationsBase(inventoryId, aisleId)}${qs}`);
}

export async function createAisleLocation(
  inventoryId: string,
  aisleId: string,
  body: CreateAisleLocationRequest
): Promise<AisleLocation> {
  return apiRequestJson<AisleLocation>(aisleLocationsBase(inventoryId, aisleId), {
    method: 'POST',
    body,
  });
}

export async function updateAisleLocation(
  inventoryId: string,
  aisleId: string,
  locationId: string,
  body: UpdateAisleLocationRequest
): Promise<AisleLocation> {
  return apiRequestJson<AisleLocation>(
    `${aisleLocationsBase(inventoryId, aisleId)}/${encodeURIComponent(locationId)}`,
    {
      method: 'PATCH',
      body,
    }
  );
}

export async function listAisleLocationLabels(
  inventoryId: string,
  locationId: string,
  options?: { status?: string | null }
): Promise<AisleLocationLabelListResponse> {
  const qs = buildQueryString([['status', options?.status]]);
  return apiRequestJson<AisleLocationLabelListResponse>(
    `${inventoryLocationLabelsBase(inventoryId, locationId)}${qs}`
  );
}

export async function issueAisleLocationLabel(
  inventoryId: string,
  locationId: string,
  body?: IssueAisleLocationLabelRequest
): Promise<AisleLocationLabel> {
  return apiRequestJson<AisleLocationLabel>(inventoryLocationLabelsBase(inventoryId, locationId), {
    method: 'POST',
    body: body ?? {},
  });
}

export async function invalidateAisleLocationLabel(
  inventoryId: string,
  locationId: string,
  labelId: string,
  body?: InvalidateAisleLocationLabelRequest
): Promise<AisleLocationLabel> {
  return apiRequestJson<AisleLocationLabel>(
    `${inventoryLocationLabelsBase(inventoryId, locationId)}/${encodeURIComponent(labelId)}/invalidate`,
    {
      method: 'POST',
      body: body ?? {},
    }
  );
}

export interface RenderAisleLocationLabelRequest {
  format: 'PDF' | 'PNG';
  preset: string;
}

export interface AisleLocationLabelArtifact {
  id: string;
  label_id: string;
  format: string;
  preset: string;
  template_version: number;
  marker_version: number;
  content_type: string;
  file_size_bytes: number;
  artifact_hash: string;
  created_at: string;
}

export async function renderAisleLocationLabel(
  inventoryId: string,
  labelId: string,
  body: RenderAisleLocationLabelRequest
): Promise<AisleLocationLabelArtifact> {
  return apiRequestJson<AisleLocationLabelArtifact>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/labels/${encodeURIComponent(labelId)}/render`,
    { method: 'POST', body }
  );
}

export async function replaceAisleLocationLabel(
  inventoryId: string,
  labelId: string,
  body?: { idempotency_key?: string | null }
): Promise<AisleLocationLabel> {
  return apiRequestJson<AisleLocationLabel>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/labels/${encodeURIComponent(labelId)}/replace`,
    { method: 'POST', body: body ?? {} }
  );
}

/** Absolute URL for backend-rendered preview (prefer authenticated blob helpers below). */
export function aisleLocationLabelPreviewUrl(
  inventoryId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): string {
  const format = opts?.format ?? 'PNG';
  const preset = opts?.preset ?? 'MM_100x100';
  const qs = buildQueryString([
    ['format', format],
    ['preset', preset],
  ]);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/labels/${encodeURIComponent(labelId)}/preview${qs}`;
}

export function aisleLocationLabelDownloadUrl(
  inventoryId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): string {
  const format = opts?.format ?? 'PDF';
  const preset = opts?.preset ?? 'MM_100x100';
  const qs = buildQueryString([
    ['format', format],
    ['preset', preset],
  ]);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/labels/${encodeURIComponent(labelId)}/download${qs}`;
}

/** Authenticated GET → Blob (Bearer via protectedFetch). Caller must revoke object URL. */
export async function fetchAisleLocationLabelPreviewBlob(
  inventoryId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): Promise<Blob> {
  const url = aisleLocationLabelPreviewUrl(inventoryId, labelId, opts);
  const response = await protectedFetch(url);
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
  return response.blob();
}

/** Authenticated download via blob + anchor (Bearer). */
export async function downloadAisleLocationLabelFile(
  inventoryId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): Promise<void> {
  const format = opts?.format ?? 'PDF';
  const preset = opts?.preset ?? 'MM_100x100';
  const url = aisleLocationLabelDownloadUrl(inventoryId, labelId, { format, preset });
  await apiDownloadBlob(url, {
    fallbackFilename: `dinamic_position_${labelId}_${preset}.${format.toLowerCase()}`,
  });
}

export interface BatchRenderAisleLocationLabelsRequest {
  preset?: string;
  format?: 'PDF';
  location_ids?: string[] | null;
  emit_missing?: boolean;
  idempotency_key?: string | null;
}

export function aisleLocationLabelsBatchRenderUrl(inventoryId: string, aisleId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/labels/batch-render`;
}

/** Authenticated POST batch-render → PDF download (Bearer). */
export async function downloadAisleLocationLabelsBatch(
  inventoryId: string,
  aisleId: string,
  body: BatchRenderAisleLocationLabelsRequest
): Promise<void> {
  const url = aisleLocationLabelsBatchRenderUrl(inventoryId, aisleId);
  const preset = body.preset ?? 'MM_100x100';
  await apiDownloadBlob(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      preset,
      format: body.format ?? 'PDF',
      location_ids: body.location_ids ?? null,
      emit_missing: Boolean(body.emit_missing),
      idempotency_key: body.idempotency_key ?? null,
    }),
    fallbackFilename: `dinamic_position_batch_${aisleId}_${preset}.pdf`,
  });
}
