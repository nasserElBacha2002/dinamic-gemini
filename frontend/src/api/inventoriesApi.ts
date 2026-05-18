import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  CreateInventoryRequest,
  Inventory,
  InventoryMetrics,
  PaginatedInventoryListResponse,
} from './types';
import { buildQueryString } from './queryString';
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

/** Wire list query — must match ``canonicalizeInventoriesListQuery`` omission rules. */
function buildInventoriesListQueryString(q?: InventoriesListQuery): string {
  return buildQueryString([
    ['search', q?.search],
    ['status', q?.status],
    ['sort_by', q?.sort_by],
    ['sort_dir', q?.sort_dir],
    ['page', q?.page, { min: 1 }],
    ['page_size', q?.page_size, { min: 1 }],
  ]);
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

/** Legacy flat CSV (all aisles, English snake_case columns). */
export async function exportInventoryResultsCsv(inventoryId: string): Promise<void> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/export?format=csv`;
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_results.csv`,
  });
}

export async function exportInventorySummaryCsv(inventoryId: string): Promise<void> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/export/summary?level=inventory`;
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_summary.csv`,
  });
}

export async function exportInventoryPackageZip(inventoryId: string): Promise<void> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/export/package`;
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_export.zip`,
  });
}

export async function createInventory(body: CreateInventoryRequest): Promise<Inventory> {
  return apiRequestJson<Inventory>(`${API_BASE}${V3_INVENTORIES_BASE}/`, {
    method: 'POST',
    body,
  });
}
