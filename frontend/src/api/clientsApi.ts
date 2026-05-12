import { V3_CLIENTS_BASE } from '../constants/v3ApiPaths';
import type { Client, ClientsListResponse, CreateClientRequest } from './types';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ClientsListQuery {
  page?: number;
  page_size?: number;
}

function buildClientsListQueryString(q: ClientsListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.page != null && q.page >= 1) params.set('page', String(q.page));
  if (q.page_size != null && q.page_size >= 1) params.set('page_size', String(q.page_size));
  const s = params.toString();
  return s ? `?${s}` : '';
}

export async function listClients(listQuery?: ClientsListQuery): Promise<ClientsListResponse> {
  const qs = buildClientsListQueryString(listQuery);
  return apiRequestJson<ClientsListResponse>(`${API_BASE}${V3_CLIENTS_BASE}/${qs}`);
}

export async function getClient(clientId: string): Promise<Client> {
  return apiRequestJson<Client>(`${API_BASE}${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}`);
}

export async function createClient(body: CreateClientRequest): Promise<Client> {
  return apiRequestJson<Client>(`${API_BASE}${V3_CLIENTS_BASE}/`, {
    method: 'POST',
    body,
  });
}
