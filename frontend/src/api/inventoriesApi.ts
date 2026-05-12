import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  CreateInventoryRequest,
  Inventory,
  InventoryMetrics,
  PaginatedInventoryListResponse,
} from './types';
import { apiDownloadBlob, apiRequestJson } from './request';

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
  return apiRequestJson<PaginatedInventoryListResponse>(`${API_BASE}${V3_INVENTORIES_BASE}/${qs}`);
}

export async function getInventory(id: string): Promise<Inventory> {
  return apiRequestJson<Inventory>(`${API_BASE}${V3_INVENTORIES_BASE}/${id}`);
}

export async function getInventoryMetrics(inventoryId: string): Promise<InventoryMetrics> {
  return apiRequestJson<InventoryMetrics>(`${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/metrics`);
}

export async function exportInventoryResultsCsv(inventoryId: string): Promise<void> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/export?format=csv`;
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_results.csv`,
  });
}

export async function createInventory(body: CreateInventoryRequest): Promise<Inventory> {
  return apiRequestJson<Inventory>(`${API_BASE}${V3_INVENTORIES_BASE}/`, {
    method: 'POST',
    body,
  });
}
