import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getAisles } from '../../../api/client';
import { queryKeys } from '../../../api/queryKeys';
import { getInventories } from '../../../api/client';
import {
  assignCaptureSessionGroupToExistingAisle,
  cancelCaptureSession,
  closeCaptureSession,
  computeCaptureSessionGroups,
  createAisleFromCaptureSessionGroup,
  createCaptureSession,
  getCaptureSessionDetail,
  getCaptureSessionGroups,
  getCaptureSessions,
  type CaptureSessionsListQuery,
} from '../api/captureSessionsApi';

function captureSessionsListKeyPart(params: CaptureSessionsListQuery): Record<string, string | number> {
  return {
    aisle_id: params.aisleId?.trim() ?? '',
    page: params.page ?? 1,
    page_size: params.pageSize ?? 25,
    status: params.statusCsv?.trim() ?? '',
  };
}

export function useCaptureSessionsList(params: CaptureSessionsListQuery, options?: { enabled?: boolean }) {
  const keyPart = captureSessionsListKeyPart(params);
  return useQuery({
    queryKey: queryKeys.captureSessions.list(params.inventoryId, keyPart),
    queryFn: () => getCaptureSessions(params),
    enabled: Boolean(params.inventoryId) && (options?.enabled ?? true),
  });
}

export function useCaptureSessionDetail(
  inventoryId: string | undefined,
  sessionId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.captureSessions.detail(inventoryId ?? '', sessionId ?? ''),
    queryFn: () => getCaptureSessionDetail(inventoryId!, sessionId!),
    enabled: Boolean(inventoryId && sessionId) && (options?.enabled ?? true),
  });
}

export function useCaptureSessionGroups(
  inventoryId: string | undefined,
  sessionId: string | undefined,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: queryKeys.captureSessions.groups(inventoryId ?? '', sessionId ?? ''),
    queryFn: () => getCaptureSessionGroups(inventoryId!, sessionId!),
    enabled: Boolean(inventoryId && sessionId) && (options?.enabled ?? true),
  });
}

export function useComputeCaptureSessionGroups() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ inventoryId, sessionId }: { inventoryId: string; sessionId: string }) =>
      computeCaptureSessionGroups(inventoryId, sessionId),
    onSuccess: (data, { inventoryId, sessionId }) => {
      queryClient.setQueryData(queryKeys.captureSessions.groups(inventoryId, sessionId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.detail(inventoryId, sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.groups(inventoryId, sessionId) });
    },
  });
}

export function useAssignCaptureSessionGroupToExistingAisle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      inventoryId,
      sessionId,
      groupId,
      aisleId,
    }: {
      inventoryId: string;
      sessionId: string;
      groupId: string;
      aisleId: string;
    }) => assignCaptureSessionGroupToExistingAisle(inventoryId, sessionId, groupId, aisleId),
    onSuccess: (data, { inventoryId, sessionId }) => {
      queryClient.setQueryData(queryKeys.captureSessions.groups(inventoryId, sessionId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.detail(inventoryId, sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.groups(inventoryId, sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aislesListTable(inventoryId) });
    },
  });
}

export function useCreateAisleFromCaptureSessionGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      inventoryId,
      sessionId,
      groupId,
      code,
    }: {
      inventoryId: string;
      sessionId: string;
      groupId: string;
      code: string;
    }) => createAisleFromCaptureSessionGroup(inventoryId, sessionId, groupId, code),
    onSuccess: (data, { inventoryId, sessionId }) => {
      queryClient.setQueryData(queryKeys.captureSessions.groups(inventoryId, sessionId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.detail(inventoryId, sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.groups(inventoryId, sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aislesListTable(inventoryId) });
    },
  });
}

export function useCreateCaptureSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ inventoryId, aisleId }: { inventoryId: string; aisleId?: string }) =>
      createCaptureSession(inventoryId, aisleId),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(created.inventory_id) });
    },
  });
}

export function useCloseCaptureSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ inventoryId, sessionId, aisleId }: { inventoryId: string; sessionId: string; aisleId?: string }) =>
      closeCaptureSession(inventoryId, sessionId, aisleId),
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.all });
      queryClient.setQueryData(
        queryKeys.captureSessions.detail(detail.session.inventory_id, detail.session.id),
        detail
      );
    },
  });
}

export function useCancelCaptureSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ inventoryId, sessionId }: { inventoryId: string; sessionId: string }) =>
      cancelCaptureSession(inventoryId, sessionId),
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.all });
      queryClient.setQueryData(
        queryKeys.captureSessions.detail(detail.session.inventory_id, detail.session.id),
        detail
      );
    },
  });
}

export function useInventoryOptions() {
  return useQuery({
    queryKey: queryKeys.inventories.listWithParams({ page: 1, page_size: 200 }),
    queryFn: () => getInventories({ page: 1, page_size: 200 }),
  });
}

export function useAisleOptions(inventoryId: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.inventories.aislesListTable(inventoryId ?? ''),
    queryFn: () => getAisles(inventoryId!, { page: 1, page_size: 200 }),
    enabled: Boolean(inventoryId) && (options?.enabled ?? true),
  });
}
