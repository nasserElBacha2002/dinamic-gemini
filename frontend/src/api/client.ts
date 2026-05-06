/**
 * v3 API client — inventories and aisles.
 * Base URL is relative so Vite proxy forwards /api to the backend.
 * Protected requests include Authorization: Bearer <token> from auth storage.
 *
 * User-visible fallback copy should use i18n.t keys (see translation.json), not raw English.
 */

import { V3_ADMIN_BASE, V3_ANALYTICS_BASE, V3_INVENTORIES_BASE, V3_REVIEW_QUEUE_BASE } from '../constants/v3ApiPaths';
import { getStoredToken } from '../features/auth/storage';
import i18n from '../i18n';
import type {
  ApiErrorDetail,
  UploadAisleAssetsResponse,
  SourceAssetSummary,
  PositionListResponse,
  PositionDetailResponse,
  ReviewActionRequest,
  AisleExecutionLogResponse,
  ExecutionLogResponse,
  JobSummary,
  AisleJobsListResponse,
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
  PromoteOperationalJobResponse,
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

/** Get execution log for a job (v3.1.1). Job must belong to the given aisle. */
export async function getExecutionLog(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<ExecutionLogResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/execution-log`
  );
  return handleResponse<ExecutionLogResponse>(response);
}

/** Aggregated execution log for all jobs on an aisle (v3 multi-job observability). */
export async function getAisleExecutionLog(
  inventoryId: string,
  aisleId: string
): Promise<AisleExecutionLogResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/execution-log`
  );
  return handleResponse<AisleExecutionLogResponse>(response);
}

/** Direct URL for execution log plain-text download (use with authenticated fetch). */
export function getExecutionLogTxtUrl(inventoryId: string, aisleId: string, jobId: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  const job = encodeURIComponent(jobId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/jobs/${job}/execution-log.txt`;
}

/** Direct URL for aisle aggregated execution log plain-text download. */
export function getAisleExecutionLogTxtUrl(inventoryId: string, aisleId: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/execution-log.txt`;
}

/** Download execution log as UTF-8 text (same artifact as JSON execution-log). */
export async function downloadExecutionLogTxt(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<void> {
  const path = getExecutionLogTxtUrl(inventoryId, aisleId, jobId);
  const response = await protectedFetch(path);
  const fallbackName = `inventory_${inventoryId}_aisle_${aisleId}_job_${jobId}_execution_log.txt`;
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

/** Download merged aisle execution log as UTF-8 text. */
export async function downloadAisleExecutionLogTxt(
  inventoryId: string,
  aisleId: string
): Promise<void> {
  const path = getAisleExecutionLogTxtUrl(inventoryId, aisleId);
  const response = await protectedFetch(path);
  const fallbackName = `inventory_${inventoryId}_aisle_${aisleId}_execution_log.txt`;
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

export async function getAisleJobDetail(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}`
  );
  return handleResponse<JobSummary>(response);
}

export async function cancelAisleJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' }
  );
  return handleResponse<JobSummary>(response);
}

export async function retryAisleJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/retry`,
    { method: 'POST' }
  );
  return handleResponse<JobSummary>(response);
}

export async function uploadAisleAssets(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<UploadAisleAssetsResponse> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/assets`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadAisleAssetsResponse>(response);
}

export async function listAisleAssets(inventoryId: string, aisleId: string): Promise<SourceAssetSummary[]> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets`
  );
  return handleResponse<SourceAssetSummary[]>(response);
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
  const path = `${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}/file`;
  if (jobId != null && String(jobId).trim() !== '') {
    return `${base}${path}?job_id=${encodeURIComponent(String(jobId).trim())}`;
  }
  return `${base}${path}`;
}

/**
 * Authenticated JSON endpoint that returns how to display a reference asset (presigned URL vs fetch /file).
 * Same ``job_id`` query semantics as {@link getReferenceImageFileUrl}.
 */
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

/** Identifies one aisle asset image for the evidence viewer (matches reference file routing). */
export interface EvidenceImageLoadSpec {
  inventoryId: string;
  aisleId: string;
  assetId: string;
  jobId?: string | null;
}

/** Result of resolving evidence/reference image for display. */
export type FetchEvidenceImageResult =
  | { ok: true; imageSrc: string; revoke?: () => void }
  | { ok: false; status: number; detail?: string };

async function fetchAuthorizedReferenceFileAsBlob(spec: EvidenceImageLoadSpec): Promise<FetchEvidenceImageResult> {
  const fileUrl = getReferenceImageFileUrl(spec.inventoryId, spec.aisleId, spec.assetId, spec.jobId);
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  try {
    const response = await fetch(fileUrl, { credentials: 'omit', headers });
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
    return {
      ok: true,
      imageSrc: blobUrl,
      revoke: () => URL.revokeObjectURL(blobUrl),
    };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}

/**
 * Resolve evidence/reference image for ``<img src>`` via the JSON ``image-display-url`` contract,
 * then presigned URL or authenticated GET to ``.../file`` when the API requests it (local / legacy / HEIC preview).
 */
export async function fetchEvidenceImageDisplay(spec: EvidenceImageLoadSpec): Promise<FetchEvidenceImageResult> {
  const url = getReferenceImageDisplayUrl(spec.inventoryId, spec.aisleId, spec.assetId, spec.jobId);
  try {
    const response = await protectedFetch(url);
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
    let data: { image_url?: unknown; requires_authenticated_fetch?: unknown };
    try {
      data = (await response.json()) as typeof data;
    } catch {
      return { ok: false, status: 502, detail: i18n.t('errors.invalid_image_display_url') };
    }
    const imageUrl =
      typeof data.image_url === 'string' && data.image_url.trim() !== '' ? data.image_url.trim() : null;
    const needFetch = data.requires_authenticated_fetch === true;
    if (imageUrl) {
      return { ok: true, imageSrc: imageUrl };
    }
    if (needFetch) {
      return fetchAuthorizedReferenceFileAsBlob(spec);
    }
    return { ok: false, status: 502, detail: i18n.t('errors.invalid_image_display_url') };
  } catch {
    return { ok: false, status: 0, detail: undefined };
  }
}

/** Query params for GET aisle positions (§9.7). Omitted keys are not sent; backend defaults apply. */
export interface AislePositionsListQuery {
  status?: string | null;
  needs_review?: boolean | null;
  min_confidence?: number | null;
  sku_filter?: string | null;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_dir?: string;
  /**
   * When false, request unmerged rows (photo-accurate review). Omitted/true uses backend default
   * (SKU consolidation on).
   */
  consolidate_by_sku?: boolean | null;
  /** When set, list only this inventory job's positions (same as GET query `job_id`). */
  job_id?: string | null;
}

function buildAislePositionsQueryString(q: AislePositionsListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.status != null && String(q.status).trim() !== '') {
    params.set('status', String(q.status).trim());
  }
  if (q.needs_review != null) {
    params.set('needs_review', String(q.needs_review));
  }
  if (q.min_confidence != null && !Number.isNaN(q.min_confidence)) {
    params.set('min_confidence', String(q.min_confidence));
  }
  if (q.sku_filter != null && String(q.sku_filter).trim() !== '') {
    params.set('sku_filter', String(q.sku_filter).trim());
  }
  if (q.page != null && q.page >= 1) {
    params.set('page', String(q.page));
  }
  if (q.page_size != null && q.page_size >= 1) {
    params.set('page_size', String(q.page_size));
  }
  if (q.sort_by != null && String(q.sort_by).trim() !== '') {
    params.set('sort_by', String(q.sort_by).trim());
  }
  if (q.sort_dir != null && String(q.sort_dir).trim() !== '') {
    params.set('sort_dir', String(q.sort_dir).trim());
  }
  if (q.job_id != null && String(q.job_id).trim() !== '') {
    params.set('job_id', String(q.job_id).trim());
  }
  if (q.consolidate_by_sku === false) {
    params.set('consolidate_by_sku', 'false');
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

/** List process_aisle jobs for an aisle (newest first) — run browser / selector. */
export async function listAisleJobs(
  inventoryId: string,
  aisleId: string,
  options?: { limit?: number }
): Promise<AisleJobsListResponse> {
  const params = new URLSearchParams();
  if (options?.limit != null && options.limit >= 1) {
    params.set('limit', String(options.limit));
  }
  const qs = params.toString();
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs${qs ? `?${qs}` : ''}`;
  const response = await protectedFetch(path);
  return handleResponse<AisleJobsListResponse>(response);
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

export async function promoteAisleOperationalJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<PromoteOperationalJobResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/promote-operational`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId.trim() }),
    }
  );
  return handleResponse<PromoteOperationalJobResponse>(response);
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

/** List positions (results) for an aisle — Épica 6 / Aisle Results table. */
export async function getAislePositions(
  inventoryId: string,
  aisleId: string,
  listQuery?: AislePositionsListQuery
): Promise<PositionListResponse> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positions`;
  const response = await protectedFetch(`${path}${buildAislePositionsQueryString(listQuery)}`);
  return handleResponse<PositionListResponse>(response);
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
