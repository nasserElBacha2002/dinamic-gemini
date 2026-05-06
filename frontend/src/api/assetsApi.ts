import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { getStoredToken } from '../features/auth/storage';
import i18n from '../i18n';
import type { ApiErrorDetail, SourceAssetSummary, UploadAisleAssetsResponse } from './types';
import { handleResponse, protectedFetch, throwApiErrorIfNotOk } from './http';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export async function uploadAisleAssets(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<UploadAisleAssetsResponse> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/assets`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadAisleAssetsResponse>(response);
}

export async function listAisleAssets(inventoryId: string, aisleId: string): Promise<SourceAssetSummary[]> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets`
  );
  return handleResponse<SourceAssetSummary[]>(response);
}

export async function deleteAisleSourceAsset(
  inventoryId: string,
  aisleId: string,
  assetId: string
): Promise<void> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}`,
    { method: 'DELETE' }
  );
  if (response.status === 204) {
    return;
  }
  const text = await response.text();
  let data: ApiErrorDetail;
  try {
    data = (text ? JSON.parse(text) : {}) as ApiErrorDetail;
  } catch {
    data = {};
  }
  throwApiErrorIfNotOk(response, text, data);
}

export function getReferenceImageFileUrl(
  inventoryId: string,
  aisleId: string,
  assetId: string,
  jobId?: string | null
): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  const path = `${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}/file`;
  if (jobId != null && String(jobId).trim() !== '') {
    return `${base}${path}?job_id=${encodeURIComponent(String(jobId).trim())}`;
  }
  return `${base}${path}`;
}

export function getReferenceImageDisplayUrl(
  inventoryId: string,
  aisleId: string,
  assetId: string,
  jobId?: string | null
): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  const path = `${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}/image-display-url`;
  if (jobId != null && String(jobId).trim() !== '') {
    return `${base}${path}?job_id=${encodeURIComponent(String(jobId).trim())}`;
  }
  return `${base}${path}`;
}

export interface EvidenceImageLoadSpec {
  inventoryId: string;
  aisleId: string;
  assetId: string;
  jobId?: string | null;
}

export type FetchEvidenceImageResult =
  | { ok: true; imageSrc: string; revoke?: () => void }
  | { ok: false; status: number; detail?: string };

async function readOptionalDetail(response: Response): Promise<string | undefined> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    return typeof data?.detail === 'string' ? data.detail : undefined;
  } catch {
    return undefined;
  }
}

async function fetchAuthorizedReferenceFileAsBlob(spec: EvidenceImageLoadSpec): Promise<FetchEvidenceImageResult> {
  const fileUrl = getReferenceImageFileUrl(spec.inventoryId, spec.aisleId, spec.assetId, spec.jobId);
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  try {
    const response = await fetch(fileUrl, { credentials: 'omit', headers });
    if (!response.ok) {
      const detail = await readOptionalDetail(response);
      return { ok: false, status: response.status, detail };
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    return {
      ok: true,
      imageSrc: blobUrl,
      revoke: () => URL.revokeObjectURL(blobUrl),
    };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}

export async function fetchEvidenceImageDisplay(spec: EvidenceImageLoadSpec): Promise<FetchEvidenceImageResult> {
  const url = getReferenceImageDisplayUrl(spec.inventoryId, spec.aisleId, spec.assetId, spec.jobId);
  try {
    const response = await protectedFetch(url);
    if (!response.ok) {
      const detail = await readOptionalDetail(response);
      return { ok: false, status: response.status, detail };
    }
    let data: { image_url?: unknown; requires_authenticated_fetch?: unknown };
    try {
      data = (await response.json()) as typeof data;
    } catch {
      return { ok: false, status: 502, detail: i18n.t('errors.invalid_image_display_url') };
    }
    const imageUrl =
      typeof data.image_url === 'string' && data.image_url.trim() !== '' ? data.image_url.trim() : null;
    const needFetch = data.requires_authenticated_fetch === true;
    if (imageUrl) {
      return { ok: true, imageSrc: imageUrl };
    }
    if (needFetch) {
      return fetchAuthorizedReferenceFileAsBlob(spec);
    }
    return { ok: false, status: 502, detail: i18n.t('errors.invalid_image_display_url') };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}
