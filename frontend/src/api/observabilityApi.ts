/**
 * GET /api/v3/observability/metrics — Phase H5 read-only operational metrics.
 */

import { V3_OBSERVABILITY_BASE } from '../constants/v3ApiPaths';
import { buildQueryString } from './queryString';
import type { ObservabilityMetricsResponse } from './types';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export type ObservabilityMetricsQueryParams = {
  from?: string;
  to?: string;
  clientId?: string;
  clientSupplierId?: string;
  providerName?: string;
  modelName?: string;
};

/** Relative path (after API base) for tests. */
export function getObservabilityMetricsPath(): string {
  return `${V3_OBSERVABILITY_BASE}/metrics`;
}

/**
 * Optional metrics filters — uses `{ trim: false }` so legacy **truthy** emission is preserved
 * (e.g. whitespace-only strings are still sent if callers pass them).
 */
export function buildObservabilityMetricsQueryString(params: ObservabilityMetricsQueryParams = {}): string {
  return buildQueryString([
    ['from', params.from, { trim: false }],
    ['to', params.to, { trim: false }],
    ['client_id', params.clientId, { trim: false }],
    ['client_supplier_id', params.clientSupplierId, { trim: false }],
    ['provider_name', params.providerName, { trim: false }],
    ['model_name', params.modelName, { trim: false }],
  ]);
}

export async function getObservabilityMetrics(
  params: ObservabilityMetricsQueryParams = {}
): Promise<ObservabilityMetricsResponse> {
  const path = `${getObservabilityMetricsPath()}${buildObservabilityMetricsQueryString(params)}`;
  return apiRequestJson<ObservabilityMetricsResponse>(`${API_BASE}${path}`);
}
