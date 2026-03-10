/**
 * v3 API client — inventories and aisles.
 * Base URL is relative so Vite proxy forwards /api to the backend.
 */

import type {
  Inventory,
  Aisle,
  CreateInventoryRequest,
  CreateAisleRequest,
  ApiErrorDetail,
  ProcessAisleResponse,
  SourceAssetSummary,
  UploadAisleAssetsResponse,
  PositionListResponse,
  PositionDetailResponse,
  ReviewActionRequest,
} from './types';
import { ApiError } from './types';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

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

export async function getInventories(): Promise<Inventory[]> {
  const response = await fetch(`${API_BASE}/api/v3/inventories`);
  const data = await handleResponse<Inventory[]>(response);
  return Array.isArray(data) ? data : [];
}

export async function getInventory(id: string): Promise<Inventory> {
  const response = await fetch(`${API_BASE}/api/v3/inventories/${id}`);
  return handleResponse<Inventory>(response);
}

export async function createInventory(body: CreateInventoryRequest): Promise<Inventory> {
  const response = await fetch(`${API_BASE}/api/v3/inventories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<Inventory>(response);
}

export async function getAisles(inventoryId: string): Promise<Aisle[]> {
  const response = await fetch(`${API_BASE}/api/v3/inventories/${inventoryId}/aisles`);
  const data = await handleResponse<Aisle[]>(response);
  return Array.isArray(data) ? data : [];
}

export async function createAisle(
  inventoryId: string,
  body: CreateAisleRequest
): Promise<Aisle> {
  const response = await fetch(`${API_BASE}/api/v3/inventories/${inventoryId}/aisles`, {
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
  const response = await fetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/process`,
    { method: 'POST' }
  );
  return handleResponse<ProcessAisleResponse>(response);
}

export async function uploadAisleAssets(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<UploadAisleAssetsResponse> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  const response = await fetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/assets`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadAisleAssetsResponse>(response);
}

export async function getAisleAssets(
  inventoryId: string,
  aisleId: string
): Promise<SourceAssetSummary[]> {
  const response = await fetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/assets`
  );
  const data = await handleResponse<SourceAssetSummary[]>(response);
  return Array.isArray(data) ? data : [];
}

/** List positions (results) for an aisle — Épica 6. */
export async function getAislePositions(
  inventoryId: string,
  aisleId: string
): Promise<PositionListResponse> {
  const response = await fetch(
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
  const response = await fetch(
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
  const response = await fetch(
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
