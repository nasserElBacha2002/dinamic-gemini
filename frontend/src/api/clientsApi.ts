import { V3_CLIENTS_BASE } from '../constants/v3ApiPaths';
import type { Client, ClientsListResponse, CreateClientRequest } from './types';
import { handleResponse, protectedFetch } from './http';

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
  const response = await protectedFetch(`${API_BASE}${V3_CLIENTS_BASE}/${qs}`);
  return handleResponse<ClientsListResponse>(response);
}

export async function getClient(clientId: string): Promise<Client> {
  const response = await protectedFetch(`${API_BASE}${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}`);
  return handleResponse<Client>(response);
}

export async function createClient(body: CreateClientRequest): Promise<Client> {
  const response = await protectedFetch(`${API_BASE}${V3_CLIENTS_BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<Client>(response);
}
