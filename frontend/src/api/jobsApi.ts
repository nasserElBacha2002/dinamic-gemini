import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { buildQueryString } from './queryString';
import type {
  AisleExecutionLogResponse,
  AisleJobsListResponse,
  ExecutionLogPage,
  ExecutionLogResponse,
  JobArtifactPage,
  ArtifactPreview,
  JobErrorPage,
  JobRetryChain,
  JobSummary,
  JobTimelinePage,
  PositionDetailResponse,
  PositionListResponse,
  PromoteOperationalJobResponse,
  ReviewActionRequest,
  RunAuditabilityView,
} from './types';
import { apiDownloadBlob, apiRequestJson, apiRequestVoid } from './request';

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

function jobScopedPath(inventoryId: string, aisleId: string, jobId: string, suffix: string): string {
  const inv = encodeURIComponent(inventoryId);
  const aisle = encodeURIComponent(aisleId);
  const job = encodeURIComponent(jobId);
  return `${API_BASE}${V3_INVENTORIES_BASE}/${inv}/aisles/${aisle}/jobs/${job}${suffix}`;
}

export async function getJobArtifacts(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  query?: {
    category?: string;
    kind?: string;
    status?: string;
    cursor?: string;
    limit?: number;
  }
): Promise<JobArtifactPage> {
  const qs = buildQueryString([
    ['category', query?.category],
    ['kind', query?.kind],
    ['status', query?.status],
    ['cursor', query?.cursor],
    ['limit', query?.limit, { min: 1 }],
  ]);
  return apiRequestJson<JobArtifactPage>(
    `${jobScopedPath(inventoryId, aisleId, jobId, '/artifacts')}${qs}`
  );
}

export function getJobArtifactDownloadUrl(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  artifactId: string
): string {
  return jobScopedPath(
    inventoryId,
    aisleId,
    jobId,
    `/artifacts/${encodeURIComponent(artifactId)}/download`
  );
}

export async function getJobArtifactPreview(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  artifactId: string
): Promise<ArtifactPreview> {
  return apiRequestJson<ArtifactPreview>(
    jobScopedPath(
      inventoryId,
      aisleId,
      jobId,
      `/artifacts/${encodeURIComponent(artifactId)}/preview`
    )
  );
}

export async function downloadJobArtifact(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  artifactId: string,
  fallbackFilename: string
): Promise<void> {
  return apiDownloadBlob(getJobArtifactDownloadUrl(inventoryId, aisleId, jobId, artifactId), {
    fallbackFilename,
  });
}

export async function getJobRetryChain(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<JobRetryChain> {
  return apiRequestJson<JobRetryChain>(jobScopedPath(inventoryId, aisleId, jobId, '/retry-chain'));
}

export async function getExecutionLogPage(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  query?: {
    cursor?: string;
    limit?: number;
    level?: string;
    stage?: string;
    search?: string;
    sort_order?: 'asc' | 'desc';
  }
): Promise<ExecutionLogPage> {
  const qs = buildQueryString([
    ['cursor', query?.cursor],
    ['limit', query?.limit, { min: 1 }],
    ['level', query?.level],
    ['stage', query?.stage],
    ['search', query?.search],
    ['sort_order', query?.sort_order],
  ]);
  return apiRequestJson<ExecutionLogPage>(
    `${jobScopedPath(inventoryId, aisleId, jobId, '/execution-log/page')}${qs}`
  );
}

export async function getJobTimeline(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  query?: { cursor?: string; limit?: number; stage?: string; event_type?: string; level?: string }
): Promise<JobTimelinePage> {
  const qs = buildQueryString([
    ['cursor', query?.cursor],
    ['limit', query?.limit, { min: 1 }],
    ['stage', query?.stage],
    ['event_type', query?.event_type],
    ['level', query?.level],
  ]);
  return apiRequestJson<JobTimelinePage>(
    `${jobScopedPath(inventoryId, aisleId, jobId, '/timeline')}${qs}`
  );
}

export async function getJobErrors(
  inventoryId: string,
  aisleId: string,
  jobId: string,
  query?: { cursor?: string; limit?: number }
): Promise<JobErrorPage> {
  const qs = buildQueryString([
    ['cursor', query?.cursor],
    ['limit', query?.limit, { min: 1 }],
  ]);
  return apiRequestJson<JobErrorPage>(
    `${jobScopedPath(inventoryId, aisleId, jobId, '/errors')}${qs}`
  );
}

export async function getJobHybridReport(
  inventoryId: string,
  aisleId: string,
  jobId: string
): Promise<Record<string, unknown>> {
  return apiRequestJson<Record<string, unknown>>(
    jobScopedPath(inventoryId, aisleId, jobId, '/hybrid-report')
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
