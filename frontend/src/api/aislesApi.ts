import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  Aisle,
  CreateAisleRequest,
  PaginatedAisleListResponse,
  ProcessAisleResponse,
  MergeResultsResponse,
  RunMergeResponse,
} from './types';
import { apiDownloadBlob, apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

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
