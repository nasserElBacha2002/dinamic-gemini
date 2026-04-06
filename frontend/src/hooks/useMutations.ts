/**
 * TanStack Query mutation hooks with explicit invalidation.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  createInventory,
  createAisle,
  startAisleProcessing,
  cancelAisleJob,
  retryAisleJob,
  runAisleMerge,
  uploadAisleAssets,
  uploadInventoryVisualReferences,
  deleteInventoryVisualReference,
  replaceInventoryVisualReference,
  submitReviewAction,
} from '../api/client';
import type { CreateInventoryRequest, CreateAisleRequest, ReviewActionRequest } from '../api/types';
import { queryKeys } from '../api/queryKeys';

export function useCreateInventory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateInventoryRequest) => createInventory(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.list() });
    },
  });
}

export function useCreateAisle(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateAisleRequest) => createAisle(inventoryId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
    },
  });
}

export function useStartAisleProcessing(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (aisleId: string) => startAisleProcessing(inventoryId, aisleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
    },
  });
}

export function useCancelAisleJob(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ aisleId, jobId }: { aisleId: string; jobId: string }) =>
      cancelAisleJob(inventoryId, aisleId, jobId),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.jobDetail(inventoryId, vars.aisleId, vars.jobId) });
    },
  });
}

export function useRetryAisleJob(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ aisleId, jobId }: { aisleId: string; jobId: string }) =>
      retryAisleJob(inventoryId, aisleId, jobId),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.jobDetail(inventoryId, vars.aisleId, vars.jobId) });
    },
  });
}

export type RunAisleMergeVariables = { aisleId: string; jobId?: string | null };

export function useRunAisleMerge(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: RunAisleMergeVariables) =>
      runAisleMerge(inventoryId, vars.aisleId, { jobId: vars.jobId }),
    onSuccess: (_, vars) => {
      const { aisleId, jobId } = vars;
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.inventories.mergeResults(inventoryId, aisleId), jobId ?? null],
      });
    },
  });
}

export function useUploadAisleAssets(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadAisleAssets(inventoryId, aisleId, files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
    },
  });
}

/** Upload assets for any aisle; pass aisleId as first argument to mutateAsync. */
export function useUploadAisleAssetsFlex(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ aisleId, files }: { aisleId: string; files: File[] }) =>
      uploadAisleAssets(inventoryId, aisleId, files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
    },
  });
}

export function useUploadInventoryVisualReferences(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadInventoryVisualReferences(inventoryId, files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.visualReferences(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
    },
  });
}

export function useDeleteInventoryVisualReference(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (referenceId: string) => deleteInventoryVisualReference(inventoryId, referenceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.visualReferences(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
    },
  });
}

export function useReplaceInventoryVisualReference(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ referenceId, file }: { referenceId: string; file: File }) =>
      replaceInventoryVisualReference(inventoryId, referenceId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.visualReferences(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
    },
  });
}

export function useSubmitReviewAction(inventoryId: string, aisleId: string, positionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ReviewActionRequest) =>
      submitReviewAction(inventoryId, aisleId, positionId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [
          ...queryKeys.inventories.all,
          'aisles',
          inventoryId,
          'positions',
          aisleId,
          'detail',
          positionId,
        ],
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
      // Also invalidate summary/KPI levels to ensure parent page counts are accurate.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.metrics(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
    },
  });
}
