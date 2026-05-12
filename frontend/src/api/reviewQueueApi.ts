import { V3_INVENTORIES_BASE, V3_REVIEW_QUEUE_BASE } from '../constants/v3ApiPaths';
import type { PositionDetailResponse, ReviewActionRequest, ReviewQueueListResponse } from './types';
import { handleResponse, protectedFetch } from './http';
import { apiRequestVoid } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ReviewQueueListQuery {
  inventory_id?: string | null;
  aisle_id?: string | null;
  min_confidence?: number | null;
  max_confidence?: number | null;
  traceability?: string | null;
  has_evidence?: boolean | null;
  qty_zero?: boolean | null;
  sku_contains?: string | null;
  position_status?: string | null;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
}

export function buildReviewQueueQueryString(q: ReviewQueueListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.inventory_id != null && String(q.inventory_id).trim() !== '') {
    params.set('inventory_id', String(q.inventory_id).trim());
  }
  if (q.aisle_id != null && String(q.aisle_id).trim() !== '') {
    params.set('aisle_id', String(q.aisle_id).trim());
  }
  if (q.min_confidence != null && !Number.isNaN(q.min_confidence)) {
    params.set('min_confidence', String(q.min_confidence));
  }
  if (q.max_confidence != null && !Number.isNaN(q.max_confidence)) {
    params.set('max_confidence', String(q.max_confidence));
  }
  if (q.traceability != null && String(q.traceability).trim() !== '') {
    params.set('traceability', String(q.traceability).trim().toLowerCase());
  }
  if (q.has_evidence === true) params.set('has_evidence', 'true');
  if (q.has_evidence === false) params.set('has_evidence', 'false');
  if (q.qty_zero === true) params.set('qty_zero', 'true');
  if (q.qty_zero === false) params.set('qty_zero', 'false');
  if (q.sku_contains != null && String(q.sku_contains).trim() !== '') {
    params.set('sku_contains', String(q.sku_contains).trim());
  }
  if (q.position_status != null && String(q.position_status).trim() !== '') {
    params.set('position_status', String(q.position_status).trim().toLowerCase());
  }
  if (q.sort_by != null && String(q.sort_by).trim() !== '') params.set('sort_by', String(q.sort_by).trim());
  if (q.sort_dir != null && String(q.sort_dir).trim() !== '') params.set('sort_dir', String(q.sort_dir).trim());
  if (q.page != null && q.page >= 1) params.set('page', String(q.page));
  if (q.page_size != null && q.page_size >= 1) params.set('page_size', String(q.page_size));
  const s = params.toString();
  return s ? `?${s}` : '';
}

export async function getReviewQueuePositions(
  listQuery?: ReviewQueueListQuery
): Promise<ReviewQueueListResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_REVIEW_QUEUE_BASE}/positions${buildReviewQueueQueryString(listQuery)}`
  );
  return handleResponse<ReviewQueueListResponse>(response);
}

export async function getPositionDetail(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  options?: { jobId?: string | null; exactPosition?: boolean }
): Promise<PositionDetailResponse> {
  const params = new URLSearchParams();
  if (options?.jobId != null && String(options.jobId).trim() !== '') {
    params.set('job_id', String(options.jobId).trim());
  }
  if (options?.exactPosition) {
    params.set('exact_position', 'true');
  }
  const qs = params.toString();
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positions/${positionId}${qs ? `?${qs}` : ''}`;
  const response = await protectedFetch(path);
  return handleResponse<PositionDetailResponse>(response);
}

export async function submitReviewAction(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): Promise<void> {
  return apiRequestVoid(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positions/${positionId}/reviews`,
    {
      method: 'POST',
      body,
    }
  );
}
