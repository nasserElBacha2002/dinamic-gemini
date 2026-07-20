import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { buildQueryString } from './queryString';
import { apiRequestJson, apiRequestVoid } from './request';
import type {
  AssetProcessingDetail,
  AssetProcessingListResponse,
  InvalidateResultRequest,
  InvalidateResultResponse,
  ProcessingEventsPage,
  ProcessingObservabilityCapabilities,
  ReprocessAssetRequest,
  ReprocessAssetResponse,
} from './types/processing';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

function assetScopedPath(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string,
  suffix: string
): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  const job = encodeURIComponent(jobId);
  const asset = encodeURIComponent(assetId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/jobs/${job}/assets/${asset}${suffix}`;
}

function jobAssetsPath(inventoryId: string, aisleId: string, jobId: string, suffix: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  const job = encodeURIComponent(jobId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/jobs/${job}/assets${suffix}`;
}

export interface ProcessingAssetsQuery {
  status?: string;
  strategy?: string;
  resolved_by?: string;
  search?: string;
  page?: number;
  page_size?: number;
  has_warnings?: boolean;
  has_fallback?: boolean;
}

export async function getProcessingAssets(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  query?: ProcessingAssetsQuery
): Promise<AssetProcessingListResponse> {
  const qs = buildQueryString([
    ['status', query?.status],
    ['strategy', query?.strategy],
    ['resolved_by', query?.resolved_by],
    ['search', query?.search],
    ['page', query?.page, { min: 1 }],
    ['page_size', query?.page_size, { min: 1 }],
    ['has_warnings', query?.has_warnings === true ? 'true' : query?.has_warnings === false ? 'false' : undefined],
    ['has_fallback', query?.has_fallback === true ? 'true' : query?.has_fallback === false ? 'false' : undefined],
  ]);
  return apiRequestJson<AssetProcessingListResponse>(
    `${jobAssetsPath(inventoryId, aisleId, jobId, '/processing')}${qs}`
  );
}

export async function getProcessingAssetDetail(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string
): Promise<AssetProcessingDetail> {
  return apiRequestJson<AssetProcessingDetail>(
    assetScopedPath(inventoryId, aisleId, jobId, assetId, '/processing-detail')
  );
}

export async function getProcessingEvents(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string,
  query?: { page?: number; page_size?: number }
): Promise<ProcessingEventsPage> {
  const qs = buildQueryString([
    ['page', query?.page, { min: 1 }],
    ['page_size', query?.page_size, { min: 1 }],
  ]);
  return apiRequestJson<ProcessingEventsPage>(
    `${assetScopedPath(inventoryId, aisleId, jobId, assetId, '/processing-events')}${qs}`
  );
}

export async function reprocessAsset(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string,
  body: ReprocessAssetRequest,
  options?: { idempotencyKey?: string }
): Promise<ReprocessAssetResponse> {
  const headers: HeadersInit = {};
  if (options?.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey;
  }
  return apiRequestJson<ReprocessAssetResponse>(
    assetScopedPath(inventoryId, aisleId, jobId, assetId, '/reprocess'),
    { method: 'POST', body, headers }
  );
}

export async function invalidateAssetResult(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string,
  body: InvalidateResultRequest,
  options?: { idempotencyKey?: string }
): Promise<InvalidateResultResponse> {
  const headers: HeadersInit = {};
  if (options?.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey;
  }
  return apiRequestJson<InvalidateResultResponse>(
    assetScopedPath(inventoryId, aisleId, jobId, assetId, '/invalidate-result'),
    { method: 'POST', body, headers }
  );
}

export async function getProcessingObservabilityCapabilities(): Promise<ProcessingObservabilityCapabilities> {
  return apiRequestJson<ProcessingObservabilityCapabilities>(
    `${API_BASE}/api/v3/config/processing-observability-capabilities`
  );
}

/** POST retry persistence — void success when backend exposes it. */
export async function retryAssetPersistence(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string,
  body: { reason: string; expected_state_version: number }
): Promise<void> {
  await apiRequestVoid(
    assetScopedPath(inventoryId, aisleId, jobId, assetId, '/retry-persistence'),
    { method: 'POST', body }
  );
}

/** POST send to external — void success when backend exposes it. */
export async function sendAssetToExternal(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  assetId: string,
  body: { reason: string; expected_state_version: number }
): Promise<void> {
  await apiRequestVoid(
    assetScopedPath(inventoryId, aisleId, jobId, assetId, '/send-to-external'),
    { method: 'POST', body }
  );
}
