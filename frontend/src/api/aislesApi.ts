import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  Aisle,
  AisleStatusResponse,
  ApiErrorDetail,
  CreateAisleRequest,
  PaginatedAisleListResponse,
  ProcessAisleResponse,
  MergeResultsResponse,
  RunMergeResponse,
} from './types';
import { filenameFromContentDisposition, handleResponse, protectedFetch, throwApiErrorIfNotOk } from './http';

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
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles${buildAislesListQueryString(listQuery)}`
  );
  return handleResponse<PaginatedAisleListResponse>(response);
}

export async function createAisle(
  inventoryId: string,
  body: CreateAisleRequest
): Promise<Aisle> {
  const response = await protectedFetch(`${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<Aisle>(response);
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
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/process`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  );
  return handleResponse<ProcessAisleResponse>(response);
}

export async function getAisleStatus(
  inventoryId: string,
  aisleId: string
): Promise<AisleStatusResponse> {
  const response = await protectedFetch(
    `${API_BASE}${V3_INVENTORIES_BASE}/${inventoryId}/aisles/${aisleId}/status`
  );
  return handleResponse<AisleStatusResponse>(response);
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
  const response = await protectedFetch(url, { method: 'POST' });
  return handleResponse<RunMergeResponse>(response);
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
  const response = await protectedFetch(path);
  return handleResponse<MergeResultsResponse>(response);
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
  const response = await protectedFetch(path);
  const fallbackName = `inventory_${inventoryId}_aisle_${aisleId}_results.csv`;
  if (!response.ok) {
    const text = await response.text();
    let data: ApiErrorDetail;
    try {
      data = (text ? JSON.parse(text) : {}) as ApiErrorDetail;
    } catch {
      data = {};
    }
    throwApiErrorIfNotOk(response, text, data);
  }
  const blob = await response.blob();
  const filename = filenameFromContentDisposition(response.headers.get('Content-Disposition'), fallbackName);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
