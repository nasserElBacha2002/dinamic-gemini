import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  Aisle,
  CreateAisleRequest,
  PaginatedAisleListResponse,
  ProcessAisleResponse,
  MergeResultsResponse,
  RunMergeResponse,
  UpdateAisleRequest,
} from './types';
import { buildQueryString } from './queryString';
import { apiDownloadBlob, apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface AislesListQuery {
  search?: string | null;
  status?: string | null;
  /** Soft-active filter; omit or null = no filter. */
  is_active?: boolean | null;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
}

/** Wire aisles list query — must stay aligned with list omission rules (see ``queryParamCanonicalization`` for related keys). */
function buildAislesListQueryString(q?: AislesListQuery): string {
  return buildQueryString([
    ['search', q?.search],
    ['status', q?.status],
    ['is_active', q?.is_active],
    ['sort_by', q?.sort_by],
    ['sort_dir', q?.sort_dir],
    ['page', q?.page, { min: 1 }],
    ['page_size', q?.page_size, { min: 1 }],
  ]);
}

export async function getAisles(
  inventoryId: string,
  listQuery?: AislesListQuery
): Promise<PaginatedAisleListResponse> {
  return apiRequestJson<PaginatedAisleListResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles${buildAislesListQueryString(listQuery)}`
  );
}

export async function createAisle(
  inventoryId: string,
  body: CreateAisleRequest
): Promise<Aisle> {
  return apiRequestJson<Aisle>(`${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles`, {
    method: 'POST',
    body,
  });
}

export async function updateAisle(
  inventoryId: string,
  aisleId: string,
  body: UpdateAisleRequest
): Promise<Aisle> {
  return apiRequestJson<Aisle>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}`,
    {
      method: 'PATCH',
      body,
    }
  );
}

export async function deactivateAisle(inventoryId: string, aisleId: string): Promise<Aisle> {
  return apiRequestJson<Aisle>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/deactivate`,
    { method: 'POST' }
  );
}

export async function activateAisle(inventoryId: string, aisleId: string): Promise<Aisle> {
  return apiRequestJson<Aisle>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/activate`,
    { method: 'POST' }
  );
}

export async function startAisleProcessing(
  inventoryId: string,
  aisleId: string,
  options?: {
    providerName?: string | null;
    modelName?: string | null;
    promptKey?: string | null;
    identificationMode?: string | null;
  }
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
  const idMode = options?.identificationMode;
  if (idMode != null && String(idMode).trim() !== '') {
    body.identification_mode = String(idMode).trim().toUpperCase();
  }
  return apiRequestJson<ProcessAisleResponse>(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/process`,
    {
      method: 'POST',
      body,
    }
  );
}

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
  const url = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/merge?${qs}`;
  return apiRequestJson<RunMergeResponse>(url, { method: 'POST' });
}

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
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/merge-results${qs ? `?${qs}` : ''}`;
  return apiRequestJson<MergeResultsResponse>(path);
}

export async function exportAisleResultsCsv(
  inventoryId: string,
  aisleId: string,
  options?: { jobId?: string | null; technical?: boolean }
): Promise<void> {
  const params = new URLSearchParams({ format: 'csv' });
  if (options?.technical) {
    params.set('technical', 'true');
  }
  const jid = options?.jobId?.trim();
  if (jid) {
    params.set('job_id', jid);
  }
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/export?${params}`;
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_aisle_${aisleId}_results.csv`,
  });
}

/** Business-profile aisle operational CSV (Spanish headers, readable columns). */
export async function exportAisleOperationalCsv(
  inventoryId: string,
  aisleId: string,
  options?: { jobId?: string | null }
): Promise<void> {
  const params = new URLSearchParams({ format: 'csv', profile: 'business' });
  const jid = options?.jobId?.trim();
  if (jid) {
    params.set('job_id', jid);
  }
  const path = `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/export?${params}`;
  return apiDownloadBlob(path, {
    fallbackFilename: `inventory_${inventoryId}_aisle_${aisleId}_operational.csv`,
  });
}
