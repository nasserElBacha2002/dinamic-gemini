import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { buildQueryString } from './queryString';
import type {
  AisleExecutionLogResponse,
  AisleJobsListResponse,
  ExecutionLogResponse,
  JobSummary,
  PositionListResponse,
  PromoteOperationalJobResponse,
  RunAuditabilityView,
} from './types';
import { apiDownloadBlob, apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export function getExecutionLogTxtUrl(inventoryId: string, aisleId: string, jobId: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  const job = encodeURIComponent(jobId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/jobs/${job}/execution-log.txt`;
}

export function getAisleExecutionLogTxtUrl(inventoryId: string, aisleId: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/execution-log.txt`;
}

export async function getExecutionLog(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<ExecutionLogResponse> {
  return apiRequestJson<ExecutionLogResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/execution-log`
  );
}

/** Path suffix (after API base) for GET job auditability (Phase H) — exposed for tests. */
export function getJobAuditabilityPath(inventoryId: string, aisleId: string, jobId: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  const job = encodeURIComponent(jobId);
  return `${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/jobs/${job}/auditability`;
}

export async function getJobAuditability(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<RunAuditabilityView> {
  return apiRequestJson<RunAuditabilityView>(
    `${API_BASE}${getJobAuditabilityPath(inventoryId, aisleId, jobId)}`
  );
}

export async function getAisleExecutionLog(
  inventoryId: string,
  aisleId: string
): Promise<AisleExecutionLogResponse> {
  return apiRequestJson<AisleExecutionLogResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/execution-log`
  );
}

export async function downloadExecutionLogTxt(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<void> {
  const path = getExecutionLogTxtUrl(inventoryId, aisleId, jobId);
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_aisle_${aisleId}_job_${jobId}_execution_log.txt`,
  });
}

export async function downloadAisleExecutionLogTxt(
  inventoryId: string,
  aisleId: string
): Promise<void> {
  const path = getAisleExecutionLogTxtUrl(inventoryId, aisleId);
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_aisle_${aisleId}_execution_log.txt`,
  });
}

export async function getAisleJobDetail(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  return apiRequestJson<JobSummary>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}`
  );
}

export async function cancelAisleJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  return apiRequestJson<JobSummary>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' }
  );
}

export async function retryAisleJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobSummary> {
  return apiRequestJson<JobSummary>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs/${encodeURIComponent(jobId)}/retry`,
    { method: 'POST' }
  );
}

export interface AislePositionsListQuery {
  status?: string | null;
  needs_review?: boolean | null;
  min_confidence?: number | null;
  sku_filter?: string | null;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_dir?: string;
  consolidate_by_sku?: boolean | null;
  job_id?: string | null;
}

/** Wire aisle positions list query — omission and boolean rules stay aligned with `canonicalizeAislePositionsListQuery`. */
export function buildAislePositionsQueryString(q?: AislePositionsListQuery): string {
  const minConfidenceWire =
    q?.min_confidence != null && !Number.isNaN(q.min_confidence) ? String(q.min_confidence) : undefined;

  return buildQueryString([
    ['status', q?.status],
    ['needs_review', q?.needs_review],
    ['min_confidence', minConfidenceWire, { trim: false }],
    ['sku_filter', q?.sku_filter],
    ['page', q?.page, { min: 1 }],
    ['page_size', q?.page_size, { min: 1 }],
    ['sort_by', q?.sort_by],
    ['sort_dir', q?.sort_dir],
    ['job_id', q?.job_id],
    ['consolidate_by_sku', q?.consolidate_by_sku, { emit: 'false-only' }],
  ]);
}

export async function listAisleJobs(
  inventoryId: string,
  aisleId: string,
  options?: { limit?: number }
): Promise<AisleJobsListResponse> {
  const qs = buildQueryString([['limit', options?.limit, { min: 1 }]]);
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/jobs${qs}`;
  return apiRequestJson<AisleJobsListResponse>(path);
}

export async function promoteAisleOperationalJob(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<PromoteOperationalJobResponse> {
  return apiRequestJson<PromoteOperationalJobResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/promote-operational`,
    {
      method: 'POST',
      body: { job_id: jobId.trim() },
    }
  );
}

export async function getAislePositions(
  inventoryId: string,
  aisleId: string,
  listQuery?: AislePositionsListQuery
): Promise<PositionListResponse> {
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/positions`;
  return apiRequestJson<PositionListResponse>(`${path}${buildAislePositionsQueryString(listQuery)}`);
}
