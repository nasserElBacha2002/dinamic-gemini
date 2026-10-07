import { V3_CLIENTS_BASE } from '../constants/v3ApiPaths';
import type { Client, ClientsListResponse, CreateClientRequest } from './types';
import { buildQueryString } from './queryString';
import { apiDownloadBlob, apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ClientsListQuery {
  page?: number;
  page_size?: number;
}

function buildClientsListQueryString(q?: ClientsListQuery): string {
  return buildQueryString([
    ['page', q?.page, { min: 1 }],
    ['page_size', q?.page_size, { min: 1 }],
  ]);
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

/** Offline Raspberry scanner configuration package (admin JSON download). */
export async function downloadRaspberryOfflinePackage(clientId?: string): Promise<void> {
  const qs = buildQueryString([['client_id', clientId?.trim() || null]]);
  const path = `${API_BASE}${V3_CLIENTS_BASE}/raspberry-offline-package${qs}`;
  return apiDownloadBlob(path, {
    fallbackFilename: clientId
      ? `raspberry-offline-package-${clientId}.json`
      : 'raspberry-offline-package-all.json',
  });
}
