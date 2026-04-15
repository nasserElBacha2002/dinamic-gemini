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
  promoteAisleOperationalJob,
} from '../api/client';
import type { CreateInventoryRequest, CreateAisleRequest, ReviewActionRequest } from '../api/types';
import { queryKeys } from '../api/queryKeys';
import {
  applySubmitReviewActionCacheEffects,
  type ReviewMutationStrategy,
} from './reviewActionCachePatch';
import { patchCreateAisleIntoAislesLists, patchPromoteOperationalJobInAisleJobs } from './mutationCachePatch';
import { recordMutationInvalidationsObs } from '../dev/cacheMutationObservability';

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
    onSuccess: (createdAisle) => {
      const patched = patchCreateAisleIntoAislesLists(queryClient, inventoryId, createdAisle);
      if (!patched) {
        queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
      recordMutationInvalidationsObs({
        flow: 'useCreateAisle',
        labels: [...(patched ? [] : ['inventories.aisles(invalidate)']), 'inventories.detail'],
      });
    },
  });
}

export function useStartAisleProcessing(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      aisleId: string;
      providerName?: string | null;
      modelName?: string | null;
      promptKey?: string | null;
    }) =>
      startAisleProcessing(inventoryId, vars.aisleId, {
        providerName: vars.providerName,
        modelName: vars.modelName,
        promptKey: vars.promptKey,
      }),
    onSuccess: (_, vars) => {
      const { aisleId } = vars;
      // New run invalidates aisle list + detail, job list, and positions slice for this aisle.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      recordMutationInvalidationsObs({
        flow: 'useStartAisleProcessing',
        labels: ['inventories.aisles', 'inventories.detail', 'inventories.aisleJobs', 'inventories.positions'],
      });
    },
  });
}

export function useCancelAisleJob(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ aisleId, jobId }: { aisleId: string; jobId: string }) =>
      cancelAisleJob(inventoryId, aisleId, jobId),
    onSuccess: (_, vars) => {
      // Job cancel affects run list, per-aisle positions slice, and job-scoped detail — all can be visible in UI.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, vars.aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, vars.aisleId) });
      // Job-scoped detail (log / summary) must drop stale state for the cancelled job.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.jobDetail(inventoryId, vars.aisleId, vars.jobId) });
      recordMutationInvalidationsObs({
        flow: 'useCancelAisleJob',
        labels: ['inventories.aisles', 'inventories.aisleJobs', 'inventories.positions', 'inventories.jobDetail'],
      });
    },
  });
}

export function useRetryAisleJob(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ aisleId, jobId }: { aisleId: string; jobId: string }) =>
      retryAisleJob(inventoryId, aisleId, jobId),
    onSuccess: (_, vars) => {
      // Same surface as cancel: operators see jobs list, positions, and job detail after retry.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, vars.aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, vars.aisleId) });
      // Job-scoped detail must reflect the restarted run (same boundary as cancel).
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.jobDetail(inventoryId, vars.aisleId, vars.jobId) });
      recordMutationInvalidationsObs({
        flow: 'useRetryAisleJob',
        labels: ['inventories.aisles', 'inventories.aisleJobs', 'inventories.positions', 'inventories.jobDetail'],
      });
    },
  });
}

export type RunAisleMergeVariables = { aisleId: string; jobId: string | null };
export interface ReviewMutationOptions {
  strategy?: ReviewMutationStrategy;
}

/**
 * Manual merge for one aisle/run. Positions are invalidated here so all subscribers refetch.
 * Merge-results GET is refreshed only from `AislePositionsPage` via `queryClient.fetchQuery` after
 * `mutateAsync` — avoids duplicate network when combined with TanStack invalidation (Phase 1).
 */
export function useRunAisleMerge(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: RunAisleMergeVariables) =>
      runAisleMerge(inventoryId, vars.aisleId, { jobId: vars.jobId }),
    onSuccess: (_, vars) => {
      const { aisleId } = vars;
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      recordMutationInvalidationsObs({
        flow: 'useRunAisleMerge',
        labels: ['inventories.positions'],
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

/** Phase 6 — point operational_job_id at a succeeded run (benchmark → operational). */
export function usePromoteAisleOperationalJob(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => promoteAisleOperationalJob(inventoryId, aisleId, jobId),
    onSuccess: (data) => {
      const patched = patchPromoteOperationalJobInAisleJobs(
        queryClient,
        inventoryId,
        aisleId,
        data.operational_job_id
      );
      if (!patched) {
        queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, aisleId) });
      }
      // Positions list is job-scoped; default run / evidence can change when operational pointer moves.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      // Inventory-detail aisle rows can surface run/operational metadata.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      // Benchmark compare queries are keyed under this inventory; stale pairs would mislead operators.
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.benchmarkCompareInventory(inventoryId) });
      recordMutationInvalidationsObs({
        flow: 'usePromoteAisleOperationalJob',
        labels: [
          ...(!patched ? ['inventories.aisleJobs(invalidate)'] : []),
          'inventories.positions',
          'inventories.aisles',
          'inventories.benchmarkCompareInventory',
        ],
      });
    },
  });
}

export function useSubmitReviewAction(
  inventoryId: string,
  aisleId: string,
  positionId: string,
  options?: ReviewMutationOptions
) {
  const queryClient = useQueryClient();
  const strategy = options?.strategy;
  return useMutation({
    mutationFn: (body: ReviewActionRequest) =>
      submitReviewAction(inventoryId, aisleId, positionId, body),
    onSuccess: (_data, body) => {
      applySubmitReviewActionCacheEffects({
        queryClient,
        inventoryId,
        aisleId,
        positionId,
        body,
        strategy,
      });
    },
  });
}
