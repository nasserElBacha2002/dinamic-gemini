import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';
import type {
  ListAisleCodeScansResponse,
  RunAisleCodeScanResponse,
  SummarizeAisleCodeScansResponse,
} from './types/codeScans';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

function codeScansBase(inventoryId: string, aisleId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/code-scans`;
}

export async function runAisleCodeScan(
  inventoryId: string,
  aisleId: string,
  options?: { jobId?: string | null }
): Promise<RunAisleCodeScanResponse> {
  const params = new URLSearchParams();
  const jobId = options?.jobId?.trim();
  if (jobId) {
    params.set('job_id', jobId);
  }
  const query = params.toString();
  const url = `${codeScansBase(inventoryId, aisleId)}/run${query ? `?${query}` : ''}`;
  return apiRequestJson<RunAisleCodeScanResponse>(url, {
    method: 'POST',
  });
}

export async function listAisleCodeScans(
  inventoryId: string,
  aisleId: string
): Promise<ListAisleCodeScansResponse> {
  return apiRequestJson<ListAisleCodeScansResponse>(codeScansBase(inventoryId, aisleId));
}

export async function getAisleCodeScanSummary(
  inventoryId: string,
  aisleId: string
): Promise<SummarizeAisleCodeScansResponse> {
  return apiRequestJson<SummarizeAisleCodeScansResponse>(`${codeScansBase(inventoryId, aisleId)}/summary`);
}
