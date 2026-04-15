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
  patchCachesForAisleResultsStrategy,
  patchCachesForDetailStrategy,
  patchCachesForReviewQueueStrategy,
} from './reviewActionCachePatch';

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
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
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
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, vars.aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, vars.aisleId) });
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
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, vars.aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, vars.aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.jobDetail(inventoryId, vars.aisleId, vars.jobId) });
    },
  });
}

export type RunAisleMergeVariables = { aisleId: string; jobId: string | null };
export type ReviewMutationStrategy = 'reviewQueue' | 'aisleResults' | 'detail';
export interface ReviewMutationOptions {
  strategy?: ReviewMutationStrategy;
}

export function useRunAisleMerge(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: RunAisleMergeVariables) =>
      runAisleMerge(inventoryId, vars.aisleId, { jobId: vars.jobId }),
    onSuccess: (_, vars) => {
      const { aisleId } = vars;
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.inventories.all, 'aisles', inventoryId, 'merge-results', aisleId],
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisleJobs(inventoryId, aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.positions(inventoryId, aisleId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.benchmarkCompareInventory(inventoryId) });
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
      // Review Queue screen (`ReviewQueuePage`) loads rows via `useReviewQueue` only; the drawer uses
      // `positionDetail`. Nothing on that route subscribes to aisle `positions`, merge-results, or `aisles`,
      // so invalidating those would only add redundant traffic after a review action.
      if (strategy === 'reviewQueue') {
        const flags = patchCachesForReviewQueueStrategy(
          queryClient,
          inventoryId,
          aisleId,
          positionId,
          body
        );
        if (flags.invalidatePositionDetail) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId),
          });
        }
        if (flags.invalidateReviewQueue) {
          queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue.all });
        }
        return;
      }

      if (strategy === 'aisleResults') {
        const flags = patchCachesForAisleResultsStrategy(
          queryClient,
          inventoryId,
          aisleId,
          positionId,
          body
        );
        if (flags.invalidatePositionDetail) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId),
          });
        }
        if (flags.invalidatePositionsList) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
          });
        }
        queryClient.invalidateQueries({
          queryKey: queryKeys.inventories.mergeResults(inventoryId, aisleId),
        });
        return;
      }

      // Detail flows often sit beside a parent positions list (same aisle); refreshing that list keeps row
      // summaries and counts aligned with the reviewed position without touching merge/review-queue domains.
      if (strategy === 'detail') {
        const flags = patchCachesForDetailStrategy(
          queryClient,
          inventoryId,
          aisleId,
          positionId,
          body
        );
        if (flags.invalidatePositionDetail) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId),
          });
        }
        if (flags.invalidatePositionsList) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
          });
        }
        return;
      }

      // Default behavior (Phase 3 compatibility) for call sites that do not pass a strategy.
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.mergeResults(inventoryId, aisleId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue.all });
    },
  });
}
