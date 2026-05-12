import { V3_INVENTORIES_BASE, V3_REVIEW_QUEUE_BASE } from '../constants/v3ApiPaths';
import type { PositionDetailResponse, ReviewActionRequest, ReviewQueueListResponse } from './types';
import { buildQueryString } from './queryString';
import { apiRequestJson, apiRequestVoid } from './request';

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

/** Wire review queue list query — omission/lowercase rules stay aligned with `canonicalizeReviewQueueListQuery`. */
export function buildReviewQueueQueryString(q?: ReviewQueueListQuery): string {
  const minConfidenceWire =
    q?.min_confidence != null && !Number.isNaN(q.min_confidence) ? String(q.min_confidence) : undefined;
  const maxConfidenceWire =
    q?.max_confidence != null && !Number.isNaN(q.max_confidence) ? String(q.max_confidence) : undefined;

  return buildQueryString([
    ['inventory_id', q?.inventory_id],
    ['aisle_id', q?.aisle_id],
    ['min_confidence', minConfidenceWire, { trim: false }],
    ['max_confidence', maxConfidenceWire, { trim: false }],
    ['traceability', q?.traceability, { transform: (value) => value.toLowerCase() }],
    ['has_evidence', q?.has_evidence],
    ['qty_zero', q?.qty_zero],
    ['sku_contains', q?.sku_contains],
    ['position_status', q?.position_status, { transform: (value) => value.toLowerCase() }],
    ['sort_by', q?.sort_by],
    ['sort_dir', q?.sort_dir],
    ['page', q?.page, { min: 1 }],
    ['page_size', q?.page_size, { min: 1 }],
  ]);
}

export async function getReviewQueuePositions(
  listQuery?: ReviewQueueListQuery
): Promise<ReviewQueueListResponse> {
  return apiRequestJson<ReviewQueueListResponse>(
    `${API_BASE}${V3_REVIEW_QUEUE_BASE}/positions${buildReviewQueueQueryString(listQuery)}`
  );
}

export async function getPositionDetail(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  options?: { jobId?: string | null; exactPosition?: boolean }
): Promise<PositionDetailResponse> {
  const qs = buildQueryString([
    ['job_id', options?.jobId],
    ['exact_position', options?.exactPosition === true ? true : undefined, { emit: 'true-only' }],
  ]);
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positions/${positionId}${qs}`;
  return apiRequestJson<PositionDetailResponse>(path);
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
