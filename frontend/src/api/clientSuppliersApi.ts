import { pathToClientSuppliersBase, V3_CLIENTS_BASE } from '../constants/v3ApiPaths';
import type {
  ClientSupplier,
  ClientSuppliersListResponse,
  CreateClientSupplierRequest,
} from './types';
import { handleResponse, protectedFetch } from './http';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ClientSuppliersListQuery {
  page?: number;
  page_size?: number;
}

function buildClientSuppliersListQueryString(q: ClientSuppliersListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.page != null && q.page >= 1) params.set('page', String(q.page));
  if (q.page_size != null && q.page_size >= 1) params.set('page_size', String(q.page_size));
  const s = params.toString();
  return s ? `?${s}` : '';
}

export async function listClientSuppliers(
  clientId: string,
  listQuery?: ClientSuppliersListQuery
): Promise<ClientSuppliersListResponse> {
  const qs = buildClientSuppliersListQueryString(listQuery);
  const response = await protectedFetch(
    `${API_BASE}${pathToClientSuppliersBase(clientId)}${qs}`
  );
  return handleResponse<ClientSuppliersListResponse>(response);
}

export async function getClientSupplier(
  clientId: string,
  supplierId: string
): Promise<ClientSupplier> {
  const response = await protectedFetch(
    `${API_BASE}${pathToClientSuppliersBase(clientId)}/${encodeURIComponent(supplierId)}`
  );
  return handleResponse<ClientSupplier>(response);
}

export async function createClientSupplier(
  clientId: string,
  body: CreateClientSupplierRequest
): Promise<ClientSupplier> {
  const response = await protectedFetch(
    `${API_BASE}${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}/suppliers`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  );
  return handleResponse<ClientSupplier>(response);
}
