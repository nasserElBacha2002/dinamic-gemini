/**
 * v3 API client — inventories and aisles.
 * Base URL is relative so Vite proxy forwards /api to the backend.
 * Protected requests include Authorization: Bearer <token> from auth storage.
 */

import { getStoredToken } from '../features/auth/storage';
import type {
  Inventory,
  InventoryListItem,
  Aisle,
  AisleStatusResponse,
  CreateInventoryRequest,
  CreateAisleRequest,
  ApiErrorDetail,
  ProcessAisleResponse,
  SourceAssetSummary,
  UploadAisleAssetsResponse,
  UploadInventoryVisualReferencesResponse,
  InventoryVisualReferenceListResponse,
  PositionListResponse,
  PositionDetailResponse,
  RunMergeResponse,
  MergeResultsResponse,
  ReviewActionRequest,
  InventoryMetrics,
  ExecutionLogResponse,
} from './types';
import { ApiError } from './types';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

/**
 * Fetch for protected v3 endpoints. Adds Authorization: Bearer <token> when a token exists.
 * Use for all /api/v3/* calls. Does not add a header when no token (avoids malformed header).
 * 401 handling (clear auth, redirect to login) can be wired here later if needed.
 */
function protectedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const token = getStoredToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

/** FastAPI validation error item shape. */
interface ValidationDetailItem {
  msg?: string;
  loc?: unknown;
  type?: string;
}

function messageFromErrorDetail(
  detail: unknown,
  fallback: string
): string {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === 'object' && typeof (first as ValidationDetailItem).msg === 'string') {
      const msg = (first as ValidationDetailItem).msg!.trim();
      if (msg) return msg;
    }
    return 'Validation error';
  }
  return fallback;
}

/** Throws ApiError for non-OK responses; shared by handleResponse and submitReviewAction. */
function throwApiErrorIfNotOk(response: Response, text: string, data: ApiErrorDetail): never {
  const message = messageFromErrorDetail(
    data.detail,
    text && text.length < 200 ? text : response.statusText || 'Request failed'
  );
  throw new ApiError(message, response.status, data);
}

async function handleResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let data: ApiErrorDetail & T;
  try {
    data = (text ? JSON.parse(text) : {}) as ApiErrorDetail & T;
  } catch {
    data = {} as ApiErrorDetail & T;
  }
  if (!response.ok) {
    throwApiErrorIfNotOk(response, text, data);
  }
  return data as T;
}

export async function getInventories(): Promise<InventoryListItem[]> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories`);
  const data = await handleResponse<InventoryListItem[]>(response);
  return Array.isArray(data) ? data : [];
}

export async function getInventory(id: string): Promise<Inventory> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/${id}`);
  return handleResponse<Inventory>(response);
}

/** Get inventory metrics — Épica 9 (§9.6). Returns 404 if inventory not found. */
export async function getInventoryMetrics(inventoryId: string): Promise<InventoryMetrics> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/${inventoryId}/metrics`);
  return handleResponse<InventoryMetrics>(response);
}

export async function createInventory(body: CreateInventoryRequest): Promise<Inventory> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<Inventory>(response);
}

export async function uploadInventoryVisualReferences(
  inventoryId: string,
  files: File[]
): Promise<UploadInventoryVisualReferencesResponse> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/visual-references`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadInventoryVisualReferencesResponse>(response);
}

export async function getInventoryVisualReferences(
  inventoryId: string
): Promise<InventoryVisualReferenceListResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/visual-references`
  );
  return handleResponse<InventoryVisualReferenceListResponse>(response);
}

export async function getAisles(inventoryId: string): Promise<Aisle[]> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/${inventoryId}/aisles`);
  const data = await handleResponse<Aisle[]>(response);
  return Array.isArray(data) ? data : [];
}

export async function createAisle(
  inventoryId: string,
  body: CreateAisleRequest
): Promise<Aisle> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/${inventoryId}/aisles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<Aisle>(response);
}

export async function startAisleProcessing(
  inventoryId: string,
  aisleId: string
): Promise<ProcessAisleResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/process`,
    { method: 'POST' }
  );
  return handleResponse<ProcessAisleResponse>(response);
}

/** Get aisle processing status (aisle + latest job). Use for polling or single-aisle status. */
export async function getAisleStatus(
  inventoryId: string,
  aisleId: string
): Promise<AisleStatusResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/status`
  );
  return handleResponse<AisleStatusResponse>(response);
}

/** Run merge/consolidation post-process for an aisle (non-authoritative quantity artifact). */
export async function runAisleMerge(
  inventoryId: string,
  aisleId: string
): Promise<RunMergeResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/merge`,
    { method: 'POST' }
  );
  return handleResponse<RunMergeResponse>(response);
}

/** Read merge/consolidation artifacts for an aisle. */
export async function getAisleMergeResults(
  inventoryId: string,
  aisleId: string
): Promise<MergeResultsResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/merge-results`
  );
  return handleResponse<MergeResultsResponse>(response);
}

/** Get execution log for a job (v3.1.1). Job must belong to the given aisle. */
export async function getExecutionLog(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<ExecutionLogResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/execution-log`
  );
  return handleResponse<ExecutionLogResponse>(response);
}

export async function uploadAisleAssets(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<UploadAisleAssetsResponse> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/assets`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadAisleAssetsResponse>(response);
}

export async function getAisleAssets(
  inventoryId: string,
  aisleId: string
): Promise<SourceAssetSummary[]> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/assets`
  );
  const data = await handleResponse<SourceAssetSummary[]>(response);
  return Array.isArray(data) ? data : [];
}

/**
 * URL for the reference image file of an aisle asset (position.source_image_id).
 * Use for <img src> or open in new tab. Backend returns 404 if asset/file missing.
 * When jobId is provided, backend uses that job to resolve HEIC normalized preview (avoids multi-job regression).
 */
export function getReferenceImageFileUrl(
  inventoryId: string,
  aisleId: string,
  assetId: string,
  jobId?: string | null
): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  const path = `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}/file`;
  if (jobId != null && String(jobId).trim() !== '') {
    return `${base}${path}?job_id=${encodeURIComponent(String(jobId).trim())}`;
  }
  return `${base}${path}`;
}

/** Result of preflight fetch for evidence image. Used to distinguish 404/403/network and show the right message. */
export type FetchEvidenceImageResult =
  | { ok: true; blobUrl: string }
  | { ok: false; status: number; detail?: string };

/**
 * Fetch evidence/reference image with auth (same as protectedFetch). Returns blob URL on success
 * or status + detail on failure so the UI can show a differentiated error (not_found, forbidden, network).
 * Caller must revoke the returned blobUrl when no longer needed (e.g. URL.revokeObjectURL(blobUrl)).
 */
export async function fetchEvidenceImage(url: string): Promise<FetchEvidenceImageResult> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  try {
    const response = await fetch(url, { credentials: 'include', headers });
    if (!response.ok) {
      let detail: string | undefined;
      try {
        const data = (await response.json()) as { detail?: unknown };
        detail = typeof data?.detail === 'string' ? data.detail : undefined;
      } catch {
        detail = undefined;
      }
      return { ok: false, status: response.status, detail };
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    return { ok: true, blobUrl };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}

/** List positions (results) for an aisle — Épica 6. */
export async function getAislePositions(
  inventoryId: string,
  aisleId: string
): Promise<PositionListResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/positions`
  );
  return handleResponse<PositionListResponse>(response);
}

/** Get position detail with products and evidences — Épica 6. */
export async function getPositionDetail(
  inventoryId: string,
  aisleId: string,
  positionId: string
): Promise<PositionDetailResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/positions/${positionId}`
  );
  return handleResponse<PositionDetailResponse>(response);
}

/** Submit a manual review action — Épica 8. */
export async function submitReviewAction(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): Promise<void> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/positions/${positionId}/reviews`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  );
  const text = await response.text();
  let data: ApiErrorDetail;
  try {
    data = (text ? JSON.parse(text) : {}) as ApiErrorDetail;
  } catch {
    data = {};
  }
  if (!response.ok) {
    throwApiErrorIfNotOk(response, text, data);
  }
}
