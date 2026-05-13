import { V3_ANALYTICS_BASE, V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  AisleBenchmarkCompareManyRequest,
  AisleBenchmarkCompareManyResponse,
  AisleIssueListResponse,
  AnalyticsSummaryResponse,
  AnalyticsTrendsResponse,
  InventoryPerformanceListResponse,
  ManualInterventionBreakdownResponse,
  QualityPatternListResponse,
} from './types';
import { buildQueryString } from './queryString';
import { apiDownloadBlob, apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface AnalyticsQueryParams {
  date_from?: string | null;
  date_to?: string | null;
  inventory_id?: string | null;
  aisle_id?: string | null;
}

function buildAnalyticsQueryString(q?: AnalyticsQueryParams): string {
  return buildQueryString([
    ['date_from', q?.date_from],
    ['date_to', q?.date_to],
    ['inventory_id', q?.inventory_id],
    ['aisle_id', q?.aisle_id],
  ]);
}

export async function getAnalyticsSummary(q?: AnalyticsQueryParams): Promise<AnalyticsSummaryResponse> {
  return apiRequestJson<AnalyticsSummaryResponse>(
    `${API_BASE}${V3_ANALYTICS_BASE}/summary${buildAnalyticsQueryString(q)}`
  );
}

export async function getAnalyticsTrends(q?: AnalyticsQueryParams): Promise<AnalyticsTrendsResponse> {
  return apiRequestJson<AnalyticsTrendsResponse>(
    `${API_BASE}${V3_ANALYTICS_BASE}/trends${buildAnalyticsQueryString(q)}`
  );
}

export async function getAnalyticsInventoryPerformance(
  q?: AnalyticsQueryParams
): Promise<InventoryPerformanceListResponse> {
  return apiRequestJson<InventoryPerformanceListResponse>(
    `${API_BASE}${V3_ANALYTICS_BASE}/inventories${buildAnalyticsQueryString(q)}`
  );
}

export async function getAnalyticsAisleIssues(q?: AnalyticsQueryParams): Promise<AisleIssueListResponse> {
  return apiRequestJson<AisleIssueListResponse>(
    `${API_BASE}${V3_ANALYTICS_BASE}/aisles${buildAnalyticsQueryString(q)}`
  );
}

export async function getAnalyticsQualityPatterns(q?: AnalyticsQueryParams): Promise<QualityPatternListResponse> {
  return apiRequestJson<QualityPatternListResponse>(
    `${API_BASE}${V3_ANALYTICS_BASE}/quality${buildAnalyticsQueryString(q)}`
  );
}

export async function getAnalyticsManualInterventions(
  q?: AnalyticsQueryParams
): Promise<ManualInterventionBreakdownResponse> {
  return apiRequestJson<ManualInterventionBreakdownResponse>(
    `${API_BASE}${V3_ANALYTICS_BASE}/manual-interventions${buildAnalyticsQueryString(q)}`
  );
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
  return apiRequestJson<AisleBenchmarkCompareManyResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/benchmark/compare-many`,
    {
      method: 'POST',
      body: payload,
    }
  );
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
