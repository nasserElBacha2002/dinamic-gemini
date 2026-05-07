/**
 * TanStack Query hooks for clients and client suppliers (Phase A7.2).
 */

import { useQuery } from '@tanstack/react-query';
import type { ClientsListQuery, ClientSuppliersListQuery } from '../api/client';
import {
  getClient,
  getClientSupplier,
  listClients,
  listClientSuppliers,
} from '../api/client';
import { queryKeys } from '../api/queryKeys';

function clientsListKeyPart(params: ClientsListQuery | undefined): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (params?.page != null && params.page >= 1) out.page = params.page;
  if (params?.page_size != null && params.page_size >= 1) out.page_size = params.page_size;
  return out;
}

function clientSuppliersListKeyPart(
  params: ClientSuppliersListQuery | undefined
): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (params?.page != null && params.page >= 1) out.page = params.page;
  if (params?.page_size != null && params.page_size >= 1) out.page_size = params.page_size;
  return out;
}

export function useClients(listQuery?: ClientsListQuery) {
  const q = clientsListKeyPart(listQuery);
  return useQuery({
    queryKey: queryKeys.clients.list(q),
    queryFn: () => listClients(listQuery),
  });
}

export function useClient(clientId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.clients.detail(clientId ?? ''),
    queryFn: () => getClient(clientId!),
    enabled: Boolean(clientId) && (options?.enabled !== false),
  });
}

export function useClientSuppliers(
  clientId: string | undefined,
  listQuery?: ClientSuppliersListQuery,
  options?: { enabled?: boolean }
) {
  const q = clientSuppliersListKeyPart(listQuery);
  return useQuery({
    queryKey: queryKeys.clients.suppliers.list(clientId ?? '', q),
    queryFn: () => listClientSuppliers(clientId!, listQuery),
    enabled: Boolean(clientId) && (options?.enabled !== false),
  });
}

export function useClientSupplier(
  clientId: string | undefined,
  supplierId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.clients.suppliers.detail(clientId ?? '', supplierId ?? ''),
    queryFn: () => getClientSupplier(clientId!, supplierId!),
    enabled: Boolean(clientId && supplierId) && (options?.enabled !== false),
  });
}
