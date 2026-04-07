/**
 * v3 API client — inventories and aisles.
 * Base URL is relative so Vite proxy forwards /api to the backend.
 * Protected requests include Authorization: Bearer <token> from auth storage.
 */

import { getStoredToken } from '../features/auth/storage';
import type {
  Inventory,
  Aisle,
  AisleStatusResponse,
  CreateInventoryRequest,
  CreateAisleRequest,
  ApiErrorDetail,
  ProcessAisleResponse,
  UploadAisleAssetsResponse,
  UploadInventoryVisualReferencesResponse,
  InventoryVisualReferenceListResponse,
  InventoryVisualReference,
  PositionListResponse,
  PositionDetailResponse,
  RunMergeResponse,
  MergeResultsResponse,
  ReviewActionRequest,
  InventoryMetrics,
  ExecutionLogResponse,
  JobSummary,
  AisleJobsListResponse,
  PaginatedInventoryListResponse,
  PaginatedAisleListResponse,
  ProcessingProviderOptionsResponse,
  ReviewQueueListResponse,
  AnalyticsSummaryResponse,
  AnalyticsTrendsResponse,
  InventoryPerformanceListResponse,
  AisleIssueListResponse,
  QualityPatternListResponse,
  ManualInterventionBreakdownResponse,
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

/** Query params for GET /api/v3/inventories (Sprint 1.4). */
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

/**
 * GET /api/v3/inventories — paginated object (`items`, `page`, …), not a bare array (Sprint 1.4 contract).
 */
export async function getInventories(
  listQuery?: InventoriesListQuery
): Promise<PaginatedInventoryListResponse> {
  const qs = buildInventoriesListQueryString(listQuery);
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/${qs}`);
  return handleResponse<PaginatedInventoryListResponse>(response);
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

function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* ignore */
    }
  }
  const quoted = /filename\s*=\s*"([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1].trim();
  return fallback;
}

/**
 * Download consolidated inventory results as CSV (same rows as operator-facing Results, all aisles).
 * Uses Content-Disposition filename when present.
 */
export async function exportInventoryResultsCsv(inventoryId: string): Promise<void> {
  const path = `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/export?format=csv`;
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
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/`, {
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

export async function deleteInventoryVisualReference(
  inventoryId: string,
  referenceId: string
): Promise<void> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/visual-references/${encodeURIComponent(referenceId)}`,
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
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/visual-references/${encodeURIComponent(referenceId)}`,
    { method: 'PUT', body: form }
  );
  return handleResponse<InventoryVisualReference>(response);
}

export async function fetchInventoryVisualReferenceFile(
  inventoryId: string,
  referenceId: string
): Promise<{ imageSrc: string; revoke: () => void }> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/visual-references/${encodeURIComponent(referenceId)}/file`
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

export interface AislesListQuery {
  search?: string | null;
  status?: string | null;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
}

function buildAislesListQueryString(q: AislesListQuery | undefined): string {
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

/**
 * GET .../inventories/{id}/aisles — paginated object (`items`, …), not a bare array (Sprint 1.4 contract).
 */
export async function getAisles(
  inventoryId: string,
  listQuery?: AislesListQuery
): Promise<PaginatedAisleListResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles${buildAislesListQueryString(listQuery)}`
  );
  return handleResponse<PaginatedAisleListResponse>(response);
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

export async function getProcessingProviderOptions(): Promise<ProcessingProviderOptionsResponse> {
  const response = await protectedFetch(`${API_BASE}/api/v3/inventories/processing-provider-options`);
  return handleResponse<ProcessingProviderOptionsResponse>(response);
}

export async function startAisleProcessing(
  inventoryId: string,
  aisleId: string,
  options?: { providerName?: string | null; modelName?: string | null; promptKey?: string | null }
): Promise<ProcessAisleResponse> {
  const body: Record<string, string> = {};
  const prov = options?.providerName;
  if (prov != null && String(prov).trim() !== '') {
    body.provider_name = String(prov).trim().toLowerCase();
  }
  const mod = options?.modelName;
  if (mod != null && String(mod).trim() !== '') {
    body.model_name = String(mod).trim();
  }
  const pk = options?.promptKey;
  if (pk != null && String(pk).trim() !== '') {
    body.prompt_key = String(pk).trim();
  }
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/process`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
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

/** Run manual authoritative merge for an aisle and update visible results quantities. */
export async function runAisleMerge(
  inventoryId: string,
  aisleId: string,
  options: { jobId: string | null }
): Promise<RunMergeResponse> {
  const raw = options.jobId != null ? String(options.jobId).trim() : '';
  const jobId = raw !== '' ? raw : 'legacy';
  const params = new URLSearchParams();
  params.set('job_id', jobId);
  const qs = params.toString();
  const url = `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/merge?${qs}`;
  const response = await protectedFetch(url, { method: 'POST' });
  return handleResponse<RunMergeResponse>(response);
}

/** Read merge/consolidation artifacts for an aisle. */
export async function getAisleMergeResults(
  inventoryId: string,
  aisleId: string,
  options?: { jobId?: string | null }
): Promise<MergeResultsResponse> {
  const params = new URLSearchParams();
  if (options?.jobId != null && String(options.jobId).trim() !== '') {
    params.set('job_id', String(options.jobId).trim());
  }
  const qs = params.toString();
  const path = `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/merge-results${qs ? `?${qs}` : ''}`;
  const response = await protectedFetch(path);
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

export async function getAisleJobDetail(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}`
  );
  return handleResponse<JobSummary>(response);
}

export async function cancelAisleJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/cancel`,
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
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/retry`,
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
    `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/assets`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadAisleAssetsResponse>(response);
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
  const path = `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/assets/${encodeURIComponent(assetId)}/image-display-url`;
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
      return { ok: false, status: 502, detail: 'Invalid image display URL response' };
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
    return { ok: false, status: 502, detail: 'Invalid image display URL response' };
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
  const path = `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/jobs${qs ? `?${qs}` : ''}`;
  const response = await protectedFetch(path);
  return handleResponse<AisleJobsListResponse>(response);
}

/** List positions (results) for an aisle — Épica 6 / Aisle Results table. */
export async function getAislePositions(
  inventoryId: string,
  aisleId: string,
  listQuery?: AislePositionsListQuery
): Promise<PositionListResponse> {
  const path = `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/positions`;
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
    `${API_BASE}/api/v3/review-queue/positions${buildReviewQueueQueryString(listQuery)}`
  );
  return handleResponse<ReviewQueueListResponse>(response);
}

/** Get position detail with products and evidences — Épica 6. */
export async function getPositionDetail(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  options?: { jobId?: string | null }
): Promise<PositionDetailResponse> {
  const params = new URLSearchParams();
  if (options?.jobId != null && String(options.jobId).trim() !== '') {
    params.set('job_id', String(options.jobId).trim());
  }
  const qs = params.toString();
  const path = `${API_BASE}/api/v3/inventories/${inventoryId}/aisles/${aisleId}/positions/${positionId}${qs ? `?${qs}` : ''}`;
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
  const response = await protectedFetch(`${API_BASE}/api/v3/analytics/summary${buildAnalyticsQueryString(q)}`);
  return handleResponse<AnalyticsSummaryResponse>(response);
}

export async function getAnalyticsTrends(q?: AnalyticsQueryParams): Promise<AnalyticsTrendsResponse> {
  const response = await protectedFetch(`${API_BASE}/api/v3/analytics/trends${buildAnalyticsQueryString(q)}`);
  return handleResponse<AnalyticsTrendsResponse>(response);
}

export async function getAnalyticsInventoryPerformance(
  q?: AnalyticsQueryParams
): Promise<InventoryPerformanceListResponse> {
  const response = await protectedFetch(`${API_BASE}/api/v3/analytics/inventories${buildAnalyticsQueryString(q)}`);
  return handleResponse<InventoryPerformanceListResponse>(response);
}

export async function getAnalyticsAisleIssues(q?: AnalyticsQueryParams): Promise<AisleIssueListResponse> {
  const response = await protectedFetch(`${API_BASE}/api/v3/analytics/aisles${buildAnalyticsQueryString(q)}`);
  return handleResponse<AisleIssueListResponse>(response);
}

export async function getAnalyticsQualityPatterns(q?: AnalyticsQueryParams): Promise<QualityPatternListResponse> {
  const response = await protectedFetch(`${API_BASE}/api/v3/analytics/quality${buildAnalyticsQueryString(q)}`);
  return handleResponse<QualityPatternListResponse>(response);
}

export async function getAnalyticsManualInterventions(
  q?: AnalyticsQueryParams
): Promise<ManualInterventionBreakdownResponse> {
  const response = await protectedFetch(
    `${API_BASE}/api/v3/analytics/manual-interventions${buildAnalyticsQueryString(q)}`
  );
  return handleResponse<ManualInterventionBreakdownResponse>(response);
}
