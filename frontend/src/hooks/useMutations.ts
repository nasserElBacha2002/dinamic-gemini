/**
 * TanStack Query mutation hooks with explicit invalidation.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  createInventory,
  createAisle,
  startAisleProcessing,
  runAisleMerge,
  uploadAisleAssets,
  uploadInventoryVisualReferences,
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

export function useRunAisleMerge(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (aisleId: string) => runAisleMerge(inventoryId, aisleId),
    onSuccess: (_, aisleId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.mergeResults(inventoryId, aisleId) });
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

export function useSubmitReviewAction(inventoryId: string, aisleId: string, positionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ReviewActionRequest) =>
      submitReviewAction(inventoryId, aisleId, positionId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
    },
  });
}
