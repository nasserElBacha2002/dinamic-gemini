/**
 * v3 API client — inventories and aisles.
 * Base URL is relative so Vite proxy forwards /api to the backend.
 * Protected requests include Authorization: Bearer <token> from auth storage.
 *
 * User-visible fallback copy should use i18n.t keys (see translation.json), not raw English.
 */

import { V3_ADMIN_BASE, V3_ANALYTICS_BASE, V3_INVENTORIES_BASE, V3_REVIEW_QUEUE_BASE } from '../constants/v3ApiPaths';
import type {
  ApiErrorDetail,
  PositionDetailResponse,
  ReviewActionRequest,
  ProcessingProviderOptionsResponse,
  ReviewQueueListResponse,
  AnalyticsSummaryResponse,
  AnalyticsTrendsResponse,
  InventoryPerformanceListResponse,
  AisleIssueListResponse,
  QualityPatternListResponse,
  ManualInterventionBreakdownResponse,
  AisleBenchmarkCompareResponse,
  AisleBenchmarkCompareManyRequest,
  AisleBenchmarkCompareManyResponse,
  AdminAiComposedPromptResponse,
  AdminAiConfigResponse,
} from './types';
import { filenameFromContentDisposition, handleResponse, protectedFetch, throwApiErrorIfNotOk } from './http';

export type { InventoriesListQuery } from './inventoriesApi';
export {
  createInventory,
  deleteInventoryVisualReference,
  exportInventoryResultsCsv,
  fetchInventoryVisualReferenceFile,
  getInventories,
  getInventory,
  getInventoryMetrics,
  getInventoryVisualReferences,
  replaceInventoryVisualReference,
  uploadInventoryVisualReferences,
} from './inventoriesApi';
export type { AislesListQuery } from './aislesApi';
export {
  createAisle,
  exportAisleResultsCsv,
  getAisles,
  getAisleMergeResults,
  getAisleStatus,
  runAisleMerge,
  startAisleProcessing,
} from './aislesApi';
export type { AislePositionsListQuery } from './jobsApi';
export {
  cancelAisleJob,
  downloadAisleExecutionLogTxt,
  downloadExecutionLogTxt,
  getAisleExecutionLog,
  getAisleExecutionLogTxtUrl,
  getAisleJobDetail,
  getAislePositions,
  getExecutionLog,
  getExecutionLogTxtUrl,
  listAisleJobs,
  promoteAisleOperationalJob,
  retryAisleJob,
} from './jobsApi';
export type { EvidenceImageLoadSpec, FetchEvidenceImageResult } from './assetsApi';
export {
  deleteAisleSourceAsset,
  fetchEvidenceImageDisplay,
  getReferenceImageDisplayUrl,
  getReferenceImageFileUrl,
  listAisleAssets,
  uploadAisleAssets,
} from './assetsApi';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export async function getProcessingProviderOptions(): Promise<ProcessingProviderOptionsResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/processing-provider-options`);
  return handleResponse<ProcessingProviderOptionsResponse>(response);
}

/** GET /api/v3/admin/ai-config — restricted to session user `username === 'admin'`. */
export async function getAdminAiConfig(): Promise<AdminAiConfigResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ADMIN_BASE}/ai-config`);
  return handleResponse<AdminAiConfigResponse>(response);
}

/** GET composed hybrid base text for one variant (same auth gate as ai-config). */
export async function getAdminAiComposedPrompt(params: {
  pipeline_provider_key: string;
  prompt_key: string;
  prompt_parity_mode: boolean;
}): Promise<AdminAiComposedPromptResponse> {
  const q = new URLSearchParams({
    prompt_key: params.prompt_key,
    pipeline_provider_key: params.pipeline_provider_key,
    prompt_parity_mode: String(params.prompt_parity_mode),
  });
  const response = await protectedFetch(
    `${API_BASE}${V3_ADMIN_BASE}/ai-config/composed-prompt?${q.toString()}`
  );
  return handleResponse<AdminAiComposedPromptResponse>(response);
}

/** Phase 6 — explicit two-run compare for an aisle (benchmark / inspection; read-only). */
export async function getAisleBenchmarkCompare(
  inventoryId: string,
  aisleId: string,
  jobAId: string,
  jobBId: string
): Promise<AisleBenchmarkCompareResponse> {
  const params = new URLSearchParams({
    job_a_id: jobAId.trim(),
    job_b_id: jobBId.trim(),
  });
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/benchmark/compare?${params}`;
  const response = await protectedFetch(path);
  return handleResponse<AisleBenchmarkCompareResponse>(response);
}

/** Phase compare-many — explicit baseline + 2..3 selected runs. */
export async function getAisleBenchmarkCompareMany(
  inventoryId: string,
  aisleId: string,
  body: AisleBenchmarkCompareManyRequest
): Promise<AisleBenchmarkCompareManyResponse> {
  const payload: AisleBenchmarkCompareManyRequest = {
    job_ids: body.job_ids.map((jobId) => jobId.trim()),
    baseline_job_id: body.baseline_job_id.trim(),
    include_diff_rows: Boolean(body.include_diff_rows),
  };
  if (body.max_diff_rows != null) {
    payload.max_diff_rows = body.max_diff_rows;
  }
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/benchmark/compare-many`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
  return handleResponse<AisleBenchmarkCompareManyResponse>(response);
}

/**
 * Download Phase 6 benchmark CSV — either one explicit run (append metadata columns) or compare rows.
 * Provide exactly one of (runJobId) or (jobAId + jobBId).
 */
export async function downloadAisleBenchmarkExportCsv(
  inventoryId: string,
  aisleId: string,
  options: { runJobId: string } | { jobAId: string; jobBId: string }
): Promise<void> {
  const params = new URLSearchParams({ format: 'csv' });
  if ('runJobId' in options) {
    params.set('run_job_id', options.runJobId.trim());
  } else {
    params.set('job_a_id', options.jobAId.trim());
    params.set('job_b_id', options.jobBId.trim());
  }
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/benchmark/export?${params}`;
  const response = await protectedFetch(path);
  const fallbackName =
    'runJobId' in options
      ? `benchmark_run_${inventoryId}_${aisleId}_${options.runJobId}.csv`
      : `benchmark_compare_${inventoryId}_${aisleId}_${options.jobAId}_${options.jobBId}.csv`;
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

function buildReviewQueueQueryString(q: ReviewQueueListQuery | undefined): string {
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

/**
 * GET /api/v3/review-queue/positions — cross-inventory queue with filters, KPI summary, sort, pagination.
 */
export async function getReviewQueuePositions(
  listQuery?: ReviewQueueListQuery
): Promise<ReviewQueueListResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_REVIEW_QUEUE_BASE}/positions${buildReviewQueueQueryString(listQuery)}`
  );
  return handleResponse<ReviewQueueListResponse>(response);
}

/** Get position detail with products and evidences — Épica 6. */
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

/** Submit a manual review action — Épica 8. */
export async function submitReviewAction(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): Promise<void> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positions/${positionId}/reviews`,
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

/** Phase 5.1 analytics filters (ISO date strings YYYY-MM-DD). */
export interface AnalyticsQueryParams {
  date_from?: string | null;
  date_to?: string | null;
  inventory_id?: string | null;
  aisle_id?: string | null;
}

function buildAnalyticsQueryString(q: AnalyticsQueryParams | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.date_from != null && String(q.date_from).trim() !== '') {
    params.set('date_from', String(q.date_from).trim());
  }
  if (q.date_to != null && String(q.date_to).trim() !== '') {
    params.set('date_to', String(q.date_to).trim());
  }
  if (q.inventory_id != null && String(q.inventory_id).trim() !== '') {
    params.set('inventory_id', String(q.inventory_id).trim());
  }
  if (q.aisle_id != null && String(q.aisle_id).trim() !== '') {
    params.set('aisle_id', String(q.aisle_id).trim());
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

export async function getAnalyticsSummary(q?: AnalyticsQueryParams): Promise<AnalyticsSummaryResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ANALYTICS_BASE}/summary${buildAnalyticsQueryString(q)}`);
  return handleResponse<AnalyticsSummaryResponse>(response);
}

export async function getAnalyticsTrends(q?: AnalyticsQueryParams): Promise<AnalyticsTrendsResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ANALYTICS_BASE}/trends${buildAnalyticsQueryString(q)}`);
  return handleResponse<AnalyticsTrendsResponse>(response);
}

export async function getAnalyticsInventoryPerformance(
  q?: AnalyticsQueryParams
): Promise<InventoryPerformanceListResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ANALYTICS_BASE}/inventories${buildAnalyticsQueryString(q)}`);
  return handleResponse<InventoryPerformanceListResponse>(response);
}

export async function getAnalyticsAisleIssues(q?: AnalyticsQueryParams): Promise<AisleIssueListResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ANALYTICS_BASE}/aisles${buildAnalyticsQueryString(q)}`);
  return handleResponse<AisleIssueListResponse>(response);
}

export async function getAnalyticsQualityPatterns(q?: AnalyticsQueryParams): Promise<QualityPatternListResponse> {
  const response = await protectedFetch(`${API_BASE}${V3_ANALYTICS_BASE}/quality${buildAnalyticsQueryString(q)}`);
  return handleResponse<QualityPatternListResponse>(response);
}

export async function getAnalyticsManualInterventions(
  q?: AnalyticsQueryParams
): Promise<ManualInterventionBreakdownResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_ANALYTICS_BASE}/manual-interventions${buildAnalyticsQueryString(q)}`
  );
  return handleResponse<ManualInterventionBreakdownResponse>(response);
}
