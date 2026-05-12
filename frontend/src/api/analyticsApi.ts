import { V3_ANALYTICS_BASE, V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  AisleBenchmarkCompareManyRequest,
  AisleBenchmarkCompareManyResponse,
  AisleBenchmarkCompareResponse,
  AisleIssueListResponse,
  AnalyticsSummaryResponse,
  AnalyticsTrendsResponse,
  InventoryPerformanceListResponse,
  ManualInterventionBreakdownResponse,
  QualityPatternListResponse,
} from './types';
import { handleResponse, protectedFetch } from './http';
import { apiDownloadBlob } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

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
  const fallbackFilename =
    'runJobId' in options
      ? `benchmark_run_${inventoryId}_${aisleId}_${options.runJobId}.csv`
      : `benchmark_compare_${inventoryId}_${aisleId}_${options.jobAId}_${options.jobBId}.csv`;
  return apiDownloadBlob(path, { fallbackFilename });
}
