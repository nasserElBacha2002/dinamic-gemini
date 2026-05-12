import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
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
