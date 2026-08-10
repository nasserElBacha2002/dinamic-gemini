/**
 * Client-scoped positioning labels API (no inventory/aisle).
 */

import { V3_CLIENTS_BASE } from '../constants/v3ApiPaths';
import { buildQueryString } from './queryString';
import { apiDownloadBlob, apiRequestJson } from './request';
import { protectedFetch, throwApiErrorIfNotOk } from './http';
import type { ApiErrorDetail } from './types';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ClientPositionLabel {
  id: string;
  public_identifier: string;
  client_id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  available_formats: string[];
  signature_status?: string | null;
  invalidated_at?: string | null;
  invalidation_reason?: string | null;
  pallet?: string | null;
  side?: 'LEFT' | 'RIGHT' | string | null;
  level?: number | null;
  marker_index?: number | null;
  marker_total?: number | null;
  marker?: string | null;
}

export interface ClientPositionLabelListResponse {
  items: ClientPositionLabel[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CreateClientPositionLabelRequest {
  name?: string | null;
  description?: string | null;
  pallet?: string | null;
  side?: 'LEFT' | 'RIGHT' | string | null;
  level?: number | null;
  marker_index?: number | null;
  marker_total?: number | null;
}

export interface CreateClientPositionMarkerSetRequest {
  pallet: string;
  side: 'LEFT' | 'RIGHT' | string;
  level: number;
  marker_total: number;
  description?: string | null;
}

export interface ClientPositionLabelMarkerSetResponse {
  items: ClientPositionLabel[];
}

export interface UpdateClientPositionLabelRequest {
  name?: string | null;
  description?: string | null;
}

export interface ClientPositionLabelsListQuery {
  status?: string | null;
  search?: string | null;
  page?: number;
  page_size?: number;
}

function positionLabelsBase(clientId: string): string {
  return `${API_BASE}${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}/position-labels`;
}

export async function listClientPositionLabels(
  clientId: string,
  query?: ClientPositionLabelsListQuery
): Promise<ClientPositionLabelListResponse> {
  const qs = buildQueryString([
    ['status', query?.status],
    ['search', query?.search],
    ['page', query?.page, { min: 1 }],
    ['page_size', query?.page_size, { min: 1 }],
  ]);
  return apiRequestJson<ClientPositionLabelListResponse>(
    `${positionLabelsBase(clientId)}${qs}`
  );
}

export async function createClientPositionLabel(
  clientId: string,
  body: CreateClientPositionLabelRequest,
  opts?: { idempotencyKey?: string }
): Promise<ClientPositionLabel> {
  const headers: Record<string, string> = {};
  if (opts?.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey;
  return apiRequestJson<ClientPositionLabel>(positionLabelsBase(clientId), {
    method: 'POST',
    headers,
    body,
  });
}

/** Create a full marker set (01/N … N/N) with shared pallet/side/level. */
export async function createClientPositionMarkerSet(
  clientId: string,
  body: CreateClientPositionMarkerSetRequest
): Promise<ClientPositionLabelMarkerSetResponse> {
  return apiRequestJson<ClientPositionLabelMarkerSetResponse>(
    `${positionLabelsBase(clientId)}/marker-set`,
    {
      method: 'POST',
      body,
    }
  );
}

export async function getClientPositionLabel(
  clientId: string,
  labelId: string
): Promise<ClientPositionLabel> {
  return apiRequestJson<ClientPositionLabel>(
    `${positionLabelsBase(clientId)}/${encodeURIComponent(labelId)}`
  );
}

export async function updateClientPositionLabel(
  clientId: string,
  labelId: string,
  body: UpdateClientPositionLabelRequest
): Promise<ClientPositionLabel> {
  return apiRequestJson<ClientPositionLabel>(
    `${positionLabelsBase(clientId)}/${encodeURIComponent(labelId)}`,
    {
      method: 'PATCH',
      body,
    }
  );
}

export async function invalidateClientPositionLabel(
  clientId: string,
  labelId: string,
  reason?: string | null
): Promise<ClientPositionLabel> {
  return apiRequestJson<ClientPositionLabel>(
    `${positionLabelsBase(clientId)}/${encodeURIComponent(labelId)}/invalidate`,
    {
      method: 'POST',
      body: { reason: reason ?? null },
    }
  );
}

export function clientPositionLabelPreviewUrl(
  clientId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): string {
  const format = opts?.format ?? 'PNG';
  const preset = opts?.preset ?? 'MM_100x100';
  const qs = buildQueryString([
    ['format', format],
    ['preset', preset],
  ]);
  return `${positionLabelsBase(clientId)}/${encodeURIComponent(labelId)}/preview${qs}`;
}

export function clientPositionLabelDownloadUrl(
  clientId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): string {
  const format = opts?.format ?? 'PDF';
  const preset = opts?.preset ?? 'MM_100x100';
  const qs = buildQueryString([
    ['format', format],
    ['preset', preset],
  ]);
  return `${positionLabelsBase(clientId)}/${encodeURIComponent(labelId)}/download${qs}`;
}

export async function fetchClientPositionLabelPreviewBlob(
  clientId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): Promise<Blob> {
  const url = clientPositionLabelPreviewUrl(clientId, labelId, opts);
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

export async function downloadClientPositionLabelFile(
  clientId: string,
  labelId: string,
  opts?: { format?: 'PDF' | 'PNG'; preset?: string }
): Promise<void> {
  const format = opts?.format ?? 'PDF';
  const preset = opts?.preset ?? 'MM_100x100';
  const url = clientPositionLabelDownloadUrl(clientId, labelId, { format, preset });
  await apiDownloadBlob(url, {
    fallbackFilename: `dinamic_position_${labelId}_${preset}.${format.toLowerCase()}`,
  });
}
