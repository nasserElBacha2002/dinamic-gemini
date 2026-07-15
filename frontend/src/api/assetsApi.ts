import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { UPLOAD_LIMITS } from '../features/uploads/bulkUpload.config';
import { xhrMultipartUpload } from '../features/uploads/xhrMultipartUpload';
import type { BulkUploadServerBatchResult } from '../features/uploads/bulkUpload.types';
import { fetchReferenceImageDisplay, type FetchReferenceImageDisplayResult } from '../utils/fetchReferenceImageDisplay';
import { ApiError } from './types';
import type { ApiErrorDetail, SourceAssetSummary, UploadAisleAssetsResponse } from './types';
import { protectedFetch, throwApiErrorIfNotOk } from './http';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

/** Upload one aisle-asset multipart batch (≤ max files / max bytes). Prefer bulk uploader. */
export async function uploadAisleAssetsBatch(args: {
  inventoryId: string;
  aisleId: string;
  files: File[];
  clientFileIds: string[];
  uploadBatchId: string;
  signal?: AbortSignal;
  onProgress?: (loaded: number, total: number) => void;
}): Promise<UploadAisleAssetsResponse> {
  if (args.files.length > UPLOAD_LIMITS.maxFilesPerRequest) {
    throw new ApiError(`At most ${UPLOAD_LIMITS.maxFilesPerRequest} files per request`);
  }
  const form = new FormData();
  form.append('upload_batch_id', args.uploadBatchId);
  for (const id of args.clientFileIds) {
    form.append('client_file_ids', id);
  }
  for (const file of args.files) {
    form.append('files', file, file.name);
  }
  return xhrMultipartUpload<UploadAisleAssetsResponse>({
    url: `${API_BASE}${V3_INVENTORIES_BASE}/${args.inventoryId}/aisles/${args.aisleId}/assets`,
    form,
    signal: args.signal,
    onProgress: args.onProgress,
  });
}

/** Map a successful aisle batch response into bulk uploader outcomes. */
export function aisleAssetsResponseToOutcomes(
  body: UploadAisleAssetsResponse
): BulkUploadServerBatchResult {
  const outcomes: BulkUploadServerBatchResult['outcomes'] = [];
  for (const row of body.uploaded ?? []) {
    outcomes.push({
      clientFileId: row.client_file_id || '',
      status: 'completed',
      serverId: row.asset_id,
    });
  }
  for (const err of body.errors ?? []) {
    outcomes.push({
      clientFileId: err.client_file_id || '',
      status: 'failed',
      code: err.code,
      message: err.detail,
    });
  }
  // Backward compatibility: if only assets[] present
  if (!outcomes.length && body.assets?.length) {
    for (const a of body.assets) {
      outcomes.push({
        clientFileId: '',
        status: 'completed',
        serverId: a.id,
      });
    }
  }
  return { outcomes };
}

/** @deprecated Prefer bulk uploader + uploadAisleAssetsBatch. Single-request helper. */
export async function uploadAisleAssets(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<UploadAisleAssetsResponse> {
  const clientFileIds = files.map((_, i) => `legacy-${i}-${Date.now()}`);
  return uploadAisleAssetsBatch({
    inventoryId,
    aisleId,
    files,
    clientFileIds,
    uploadBatchId: `legacy-batch-${Date.now()}`,
  });
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
