/**
 * GET /api/v3/observability/metrics — Phase H5 read-only operational metrics.
 */

import { V3_OBSERVABILITY_BASE } from '../constants/v3ApiPaths';
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

export async function getObservabilityMetrics(
  params: ObservabilityMetricsQueryParams = {}
): Promise<ObservabilityMetricsResponse> {
  const qs = new URLSearchParams();
  if (params.from) qs.set('from', params.from);
  if (params.to) qs.set('to', params.to);
  if (params.clientId) qs.set('client_id', params.clientId);
  if (params.clientSupplierId) qs.set('client_supplier_id', params.clientSupplierId);
  if (params.providerName) qs.set('provider_name', params.providerName);
  if (params.modelName) qs.set('model_name', params.modelName);
  const q = qs.toString();
  const path = `${getObservabilityMetricsPath()}${q ? `?${q}` : ''}`;
  return apiRequestJson<ObservabilityMetricsResponse>(`${API_BASE}${path}`);
}
