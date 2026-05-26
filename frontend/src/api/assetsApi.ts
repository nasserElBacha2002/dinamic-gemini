import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { isTooManyFilesForUpload, tooManyFilesMessage } from '../utils/uploadFileLimits';
import { fetchReferenceImageDisplay, type FetchReferenceImageDisplayResult } from '../utils/fetchReferenceImageDisplay';
import { ApiError } from './types';
import type { ApiErrorDetail, SourceAssetSummary, UploadAisleAssetsResponse } from './types';
import { protectedFetch, throwApiErrorIfNotOk } from './http';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export async function uploadAisleAssets(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<UploadAisleAssetsResponse> {
  if (isTooManyFilesForUpload(files.length)) {
    throw new ApiError(tooManyFilesMessage('aisle'));
  }
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  return apiRequestJson<UploadAisleAssetsResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/assets`,
    { method: 'POST', body: form }
  );
}

export async function listAisleAssets(inventoryId: string, aisleId: string): Promise<SourceAssetSummary[]> {
  return apiRequestJson<SourceAssetSummary[]>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets`
  );
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

export type FetchEvidenceImageResult = FetchReferenceImageDisplayResult;

export async function fetchEvidenceImageDisplay(
  spec: EvidenceImageLoadSpec
): Promise<FetchEvidenceImageResult> {
  const displayUrl = getReferenceImageDisplayUrl(
    spec.inventoryId,
    spec.aisleId,
    spec.assetId,
    spec.jobId
  );
  const fileUrl = getReferenceImageFileUrl(
    spec.inventoryId,
    spec.aisleId,
    spec.assetId,
    spec.jobId
  );
  return fetchReferenceImageDisplay(displayUrl, fileUrl);
}
