import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  ApiErrorDetail,
  CreateInventoryRequest,
  Inventory,
  InventoryMetrics,
  InventoryVisualReference,
  InventoryVisualReferenceListResponse,
  PaginatedInventoryListResponse,
  UploadInventoryVisualReferencesResponse,
} from './types';
import { filenameFromContentDisposition, handleResponse, protectedFetch, throwApiErrorIfNotOk } from './http';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface InventoriesListQuery {
  search?: string | null;
  status?: string | null;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
}

function buildInventoriesListQueryString(q: InventoriesListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.search != null && String(q.search).trim() !== '') params.set('search', String(q.search).trim());
  if (q.status != null && String(q.status).trim() !== '') params.set('status', String(q.status).trim());
  if (q.sort_by != null && String(q.sort_by).trim() !== '') params.set('sort_by', String(q.sort_by).trim());
  if (q.sort_dir != null && String(q.sort_dir).trim() !== '') params.set('sort_dir', String(q.sort_dir).trim());
  if (q.page != null && q.page >= 1) params.set('page', String(q.page));
  if (q.page_size != null && q.page_size >= 1) params.set('page_size', String(q.page_size));
  const s = params.toString();
  return s ? `?${s}` : '';
}

export async function getInventories(
  listQuery?: InventoriesListQuery
): Promise<PaginatedInventoryListResponse> {
  const qs = buildInventoriesListQueryString(listQuery);
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/${qs}`);
  return handleResponse<PaginatedInventoryListResponse>(response);
}

export async function getInventory(id: string): Promise<Inventory> {
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/${id}`);
  return handleResponse<Inventory>(response);
}

export async function getInventoryMetrics(inventoryId: string): Promise<InventoryMetrics> {
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/metrics`);
  return handleResponse<InventoryMetrics>(response);
}

export async function exportInventoryResultsCsv(inventoryId: string): Promise<void> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/export?format=csv`;
  const response = await protectedFetch(path);
  const fallbackName = `inventory_${inventoryId}_results.csv`;
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
  const blob = await response.blob();
  const filename = filenameFromContentDisposition(response.headers.get('Content-Disposition'), fallbackName);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function createInventory(body: CreateInventoryRequest): Promise<Inventory> {
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/`, {
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
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/visual-references`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadInventoryVisualReferencesResponse>(response);
}

export async function getInventoryVisualReferences(
  inventoryId: string
): Promise<InventoryVisualReferenceListResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/visual-references`
  );
  return handleResponse<InventoryVisualReferenceListResponse>(response);
}

export async function deleteInventoryVisualReference(
  inventoryId: string,
  referenceId: string
): Promise<void> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/visual-references/${encodeURIComponent(referenceId)}`,
    { method: 'DELETE' }
  );
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
}

export async function replaceInventoryVisualReference(
  inventoryId: string,
  referenceId: string,
  file: File
): Promise<InventoryVisualReference> {
  const form = new FormData();
  form.append('file', file);
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/visual-references/${encodeURIComponent(referenceId)}`,
    { method: 'PUT', body: form }
  );
  return handleResponse<InventoryVisualReference>(response);
}

export async function fetchInventoryVisualReferenceFile(
  inventoryId: string,
  referenceId: string
): Promise<{ imageSrc: string; revoke: () => void }> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/visual-references/${encodeURIComponent(referenceId)}/file`
  );
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
  const blob = await response.blob();
  const imageSrc = URL.createObjectURL(blob);
  return {
    imageSrc,
    revoke: () => URL.revokeObjectURL(imageSrc),
  };
}
