/**
 * TanStack Query mutation hooks with explicit invalidation.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { executeBulkUpload } from '../features/uploads';
import {
  activateSupplierPromptConfigVersion,
  createSupplierPromptConfigVersion,
  createInventory,
  createAisle,
  createClient,
  createClientSupplier,
  createManualImageResult,
  deleteSupplierReferenceImage,
  startAisleProcessing,
  cancelAisleJob,
  retryAisleJob,
  runAisleMerge,
  uploadAisleAssetsBatch,
  aisleAssetsResponseToOutcomes,
  deleteAisleSourceAsset,
  uploadSupplierReferenceImages,
  submitReviewAction,
  promoteAisleOperationalJob,
  updateInventory,
  updateAisle,
  deactivateAisle,
  activateAisle,
} from '../api/client';
import type {
  CreateClientRequest,
  CreateClientSupplierRequest,
  CreateSupplierPromptConfigRequest,
  CreateInventoryRequest,
  CreateAisleRequest,
  CreateManualImageResultRequest,
  ReviewActionRequest,
  UploadSupplierReferenceImagesRequest,
  UpdateInventoryRequest,
  UpdateAisleRequest,
} from '../api/types';
import { queryKeys } from '../api/queryKeys';
import {
  applySubmitReviewActionCacheEffects,
  type ReviewMutationStrategy,
} from './reviewActionCachePatch';
import {
  patchAisleInAislesLists,
  patchCreateAisleIntoAislesLists,
  patchPromoteOperationalJobInAisleJobs,
} from './mutationCachePatch';
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

export function useUpdateInventory(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateInventoryRequest) => updateInventory(inventoryId, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.inventories.detail(inventoryId), updated);
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.analytics.all });
    },
  });
}

export function useCreateClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateClientRequest) => createClient(body),
    onSuccess: (createdClient) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clients.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.clients.detail(createdClient.id) });
    },
  });
}

export function useCreateClientSupplier(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateClientSupplierRequest) => createClientSupplier(clientId, body),
    onSuccess: (createdSupplier) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.clients.suppliers.all(clientId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.detail(clientId, createdSupplier.id),
      });
    },
  });
}

export function useUploadSupplierReferenceImages(clientId: string, supplierId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UploadSupplierReferenceImagesRequest) =>
      uploadSupplierReferenceImages(clientId, supplierId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.referenceImages(clientId, supplierId),
      });
    },
  });
}

export function useDeleteSupplierReferenceImage(clientId: string, supplierId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (imageId: string) => deleteSupplierReferenceImage(clientId, supplierId, imageId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.referenceImages(clientId, supplierId),
      });
    },
  });
}

export function useCreateSupplierPromptConfigVersion(clientId: string, supplierId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateSupplierPromptConfigRequest) =>
      createSupplierPromptConfigVersion(clientId, supplierId, body),
    onSuccess: (created) => {
      const normalizedProviderName = (created.provider_name ?? '').trim() || null;
      const normalizedModelName = (created.model_name ?? '').trim() || null;
      const scope =
        !normalizedProviderName
          ? 'all_providers_models'
          : normalizedModelName
            ? 'provider_model'
            : 'provider';
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.promptConfigs.listByScope(
          clientId,
          supplierId,
          scope,
          normalizedProviderName,
          normalizedModelName
        ),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.promptConfigs.activeByScope(
          clientId,
          supplierId,
          scope,
          normalizedProviderName,
          normalizedModelName
        ),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.promptConfigs.all(clientId, supplierId),
      });
    },
  });
}

export function useActivateSupplierPromptConfigVersion(clientId: string, supplierId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (configId: string) => activateSupplierPromptConfigVersion(clientId, supplierId, configId),
    onSuccess: (activated) => {
      const normalizedProviderName = (activated.provider_name ?? '').trim() || null;
      const normalizedModelName = (activated.model_name ?? '').trim() || null;
      const scope =
        !normalizedProviderName
          ? 'all_providers_models'
          : normalizedModelName
            ? 'provider_model'
            : 'provider';
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.promptConfigs.listByScope(
          clientId,
          supplierId,
          scope,
          normalizedProviderName,
          normalizedModelName
        ),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.promptConfigs.activeByScope(
          clientId,
          supplierId,
          scope,
          normalizedProviderName,
          normalizedModelName
        ),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clients.suppliers.promptConfigs.all(clientId, supplierId),
      });
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

function invalidateAisleLifecycleCaches(queryClient: ReturnType<typeof useQueryClient>, inventoryId: string) {
  // Aggregates (metrics, list pending counts, analytics qty) change when is_active flips.
  queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.inventories.list() });
  queryClient.invalidateQueries({ queryKey: queryKeys.inventories.metrics(inventoryId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.analytics.all });
}

export function useUpdateAisle(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ aisleId, body }: { aisleId: string; body: UpdateAisleRequest }) =>
      updateAisle(inventoryId, aisleId, body),
    onSuccess: (updatedAisle) => {
      const patched = patchAisleInAislesLists(queryClient, inventoryId, updatedAisle);
      if (!patched) {
        queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.detail(inventoryId) });
    },
  });
}

export function useDeactivateAisle(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (aisleId: string) => deactivateAisle(inventoryId, aisleId),
    onSuccess: (updatedAisle) => {
      patchAisleInAislesLists(queryClient, inventoryId, updatedAisle);
      invalidateAisleLifecycleCaches(queryClient, inventoryId);
    },
  });
}

export function useActivateAisle(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (aisleId: string) => activateAisle(inventoryId, aisleId),
    onSuccess: (updatedAisle) => {
      patchAisleInAislesLists(queryClient, inventoryId, updatedAisle);
      invalidateAisleLifecycleCaches(queryClient, inventoryId);
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
    mutationFn: async (files: File[]) => {
      const result = await executeBulkUpload({
        files,
        uploadBatch: async ({ uploadBatchId, files: batchFiles, signal, onByteProgress }) => {
          const body = await uploadAisleAssetsBatch({
            inventoryId,
            aisleId,
            files: batchFiles.map((f) => f.file),
            clientFileIds: batchFiles.map((f) => f.clientId),
            uploadBatchId,
            signal,
            onProgress: onByteProgress,
          });
          return aisleAssetsResponseToOutcomes(body);
        },
      });
      return { assets: result.files.filter((f) => f.status === 'completed').map((f) => ({ id: f.serverId })) };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleSourceAssets(inventoryId, aisleId),
      });
    },
  });
}

/** Upload assets for any aisle; pass aisleId as first argument to mutateAsync. */
export function useUploadAisleAssetsFlex(inventoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ aisleId, files }: { aisleId: string; files: File[] }) => {
      const result = await executeBulkUpload({
        files,
        uploadBatch: async ({ uploadBatchId, files: batchFiles, signal, onByteProgress }) => {
          const body = await uploadAisleAssetsBatch({
            inventoryId,
            aisleId,
            files: batchFiles.map((f) => f.file),
            clientFileIds: batchFiles.map((f) => f.clientId),
            uploadBatchId,
            signal,
            onProgress: onByteProgress,
          });
          return aisleAssetsResponseToOutcomes(body);
        },
      });
      return { assets: result.files.filter((f) => f.status === 'completed') };
    },
    onSuccess: (_, { aisleId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleSourceAssets(inventoryId, aisleId),
      });
    },
  });
}

export function useDeleteAisleSourceAsset(inventoryId: string, aisleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetId: string) => deleteAisleSourceAsset(inventoryId, aisleId, assetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleSourceAssets(inventoryId, aisleId),
      });
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

/** Operator manual coverage for an image without an automatic result. 409 when one already exists. */
export function useCreateManualImageResult(
  inventoryId: string,
  aisleId: string,
  sourceAssetId: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateManualImageResultRequest) =>
      createManualImageResult(inventoryId, aisleId, sourceAssetId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.inventories.all, 'aisles', inventoryId, aisleId, 'jobs'],
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
    },
  });
}
