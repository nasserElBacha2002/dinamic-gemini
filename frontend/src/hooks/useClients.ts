/**
 * TanStack Query hooks for clients and client suppliers (Phase A7.2).
 */

import { useQuery } from '@tanstack/react-query';
import type { ClientsListQuery, ClientSuppliersListQuery, SupplierPromptConfigsListQuery } from '../api/client';
import {
  getActiveGlobalPromptConfig,
  getActiveSupplierPromptConfig,
  getClient,
  getClientSupplier,
  listGlobalPromptConfigs,
  listClients,
  listClientSuppliers,
  listSupplierPromptConfigs,
  listSupplierReferenceImages,
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

export function useSupplierReferenceImages(
  clientId: string | undefined,
  supplierId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.clients.suppliers.referenceImages(clientId ?? '', supplierId ?? ''),
    queryFn: () => listSupplierReferenceImages(clientId!, supplierId!),
    enabled: Boolean(clientId && supplierId) && (options?.enabled !== false),
  });
}

export function useSupplierPromptConfigs(
  clientId: string | undefined,
  supplierId: string | undefined,
  listQuery: SupplierPromptConfigsListQuery | undefined,
  options?: { enabled?: boolean }
) {
  const providerName = (listQuery?.provider_name ?? '').trim();
  const modelName = (listQuery?.model_name ?? '').trim() || null;
  return useQuery({
    queryKey: queryKeys.clients.suppliers.promptConfigs.listByScope(
      clientId ?? '',
      supplierId ?? '',
      providerName,
      modelName
    ),
    queryFn: () => listSupplierPromptConfigs(clientId!, supplierId!, listQuery),
    enabled: Boolean(clientId && supplierId && providerName) && (options?.enabled !== false),
  });
}

export function useActiveSupplierPromptConfig(
  clientId: string | undefined,
  supplierId: string | undefined,
  providerName: string | undefined,
  modelName: string | null | undefined,
  options?: { enabled?: boolean }
) {
  const normalizedProviderName = (providerName ?? '').trim();
  const normalizedModelName = (modelName ?? '').trim() || null;
  return useQuery({
    queryKey: queryKeys.clients.suppliers.promptConfigs.activeByScope(
      clientId ?? '',
      supplierId ?? '',
      normalizedProviderName,
      normalizedModelName
    ),
    queryFn: () =>
      getActiveSupplierPromptConfig(clientId!, supplierId!, normalizedProviderName, normalizedModelName),
    enabled: Boolean(clientId && supplierId && normalizedProviderName) && (options?.enabled !== false),
    retry: false,
  });
}

export function useGlobalPromptConfigs(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.admin.globalPromptConfigs.list(),
    queryFn: listGlobalPromptConfigs,
    enabled: options?.enabled !== false,
  });
}

export function useActiveGlobalPromptConfig(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.admin.globalPromptConfigs.active(),
    queryFn: getActiveGlobalPromptConfig,
    enabled: options?.enabled !== false,
    retry: false,
  });
}
