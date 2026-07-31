/**
 * TanStack Query hooks for aisle locations (physical positioning).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createAisleLocation,
  invalidateAisleLocationLabel,
  issueAisleLocationLabel,
  listAisleLocationLabels,
  listAisleLocations,
  renderAisleLocationLabel,
  replaceAisleLocationLabel,
  updateAisleLocation,
  type AisleLocationsListQuery,
} from '../api/client';
import { queryKeys } from '../api/queryKeys';
import type {
  CreateAisleLocationRequest,
  InvalidateAisleLocationLabelRequest,
  IssueAisleLocationLabelRequest,
  UpdateAisleLocationRequest,
} from '../api/types';

const DEFAULT_LOCATIONS_QUERY: AisleLocationsListQuery = { page: 1, page_size: 100 };

export function useAisleLocations(
  inventoryId: string | undefined,
  aisleId: string | undefined,
  listQuery?: AisleLocationsListQuery,
  options?: { enabled?: boolean }
) {
  const q = { ...DEFAULT_LOCATIONS_QUERY, ...listQuery };
  const params: Record<string, string | number> = {
    page: q.page ?? 1,
    page_size: q.page_size ?? 100,
  };
  if (q.status) params.status = q.status;
  if (q.search) params.search = q.search;
  return useQuery({
    queryKey: queryKeys.inventories.aisleLocationsList(inventoryId ?? '', aisleId ?? '', params),
    queryFn: () => listAisleLocations(inventoryId!, aisleId!, q),
    enabled: Boolean(inventoryId && aisleId) && options?.enabled !== false,
  });
}

export function useAisleLocationLabels(
  inventoryId: string | undefined,
  locationId: string | undefined,
  options?: { enabled?: boolean; status?: string | null }
) {
  return useQuery({
    queryKey: queryKeys.inventories.aisleLocationLabels(inventoryId ?? '', locationId ?? ''),
    queryFn: () =>
      listAisleLocationLabels(inventoryId!, locationId!, { status: options?.status }),
    enabled: Boolean(inventoryId && locationId) && options?.enabled !== false,
  });
}

function invalidateLocationCaches(
  queryClient: ReturnType<typeof useQueryClient>,
  inventoryId: string,
  aisleId: string,
  locationId?: string
) {
  queryClient.invalidateQueries({
    queryKey: queryKeys.inventories.aisleLocations(inventoryId, aisleId),
  });
  if (locationId) {
    queryClient.invalidateQueries({
      queryKey: queryKeys.inventories.aisleLocationLabels(inventoryId, locationId),
    });
  }
}

export function useCreateAisleLocation(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateAisleLocationRequest) =>
      createAisleLocation(inventoryId, aisleId, body),
    onSuccess: () => invalidateLocationCaches(queryClient, inventoryId, aisleId),
  });
}

export function useUpdateAisleLocation(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      locationId,
      body,
    }: {
      locationId: string;
      body: UpdateAisleLocationRequest;
    }) => updateAisleLocation(inventoryId, aisleId, locationId, body),
    onSuccess: (updated) =>
      invalidateLocationCaches(queryClient, inventoryId, aisleId, updated.id),
  });
}

export function useIssueAisleLocationLabel(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      locationId,
      body,
    }: {
      locationId: string;
      body?: IssueAisleLocationLabelRequest;
    }) => issueAisleLocationLabel(inventoryId, locationId, body),
    onSuccess: (label) =>
      invalidateLocationCaches(queryClient, inventoryId, aisleId, label.location_id),
  });
}

export function useInvalidateAisleLocationLabel(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      locationId,
      labelId,
      body,
    }: {
      locationId: string;
      labelId: string;
      body?: InvalidateAisleLocationLabelRequest;
    }) => invalidateAisleLocationLabel(inventoryId, locationId, labelId, body),
    onSuccess: (label) =>
      invalidateLocationCaches(queryClient, inventoryId, aisleId, label.location_id),
  });
}

export function useRenderAisleLocationLabel(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      labelId,
      format,
      preset,
    }: {
      labelId: string;
      format: 'PDF' | 'PNG';
      preset: string;
    }) => renderAisleLocationLabel(inventoryId, labelId, { format, preset }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleLocations(inventoryId, aisleId),
      });
    },
  });
}

export function useReplaceAisleLocationLabel(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ labelId }: { labelId: string }) =>
      replaceAisleLocationLabel(inventoryId, labelId),
    onSuccess: (label) =>
      invalidateLocationCaches(queryClient, inventoryId, aisleId, label.location_id),
  });
}
