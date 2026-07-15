import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { aisleAssetsResponseToOutcomes, uploadAisleAssetsBatch } from '../../../api/assetsApi';
import { queryKeys } from '../../../api/queryKeys';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAppSnackbar } from '../../../components/ui';
import { useBeforeUnloadWarning } from '../../../hooks';
import {
  executeBulkUpload,
  type BulkUploadProgressSnapshot,
  type BulkUploadRunResult,
} from '../../uploads';
import { useUploadLimits } from '../../uploads/useUploadLimits';
import { isAbortError } from '../../uploads/uploadRetryPolicy';

export interface UseAisleAssetUploadFlowOptions {
  inventoryId: string;
  /**
   * When both are passed, upload errors are owned by the parent (explicit coordination with other flows).
   */
  uploadError?: string | null;
  setUploadError?: (message: string | null) => void;
  onAfterSuccess?: () => void;
  /**
   * Runs immediately before the upload mutation (when files are known).
   * Opening the file picker alone does not call this — use it e.g. to clear sibling flow errors.
   */
  onBeforeUploadAttempt?: () => void;
}

/**
 * Aisle asset upload via shared bulk uploader (auto-batching, progress, cancel, retry failed).
 */
export function useAisleAssetUploadFlow({
  inventoryId,
  uploadError: controlledError,
  setUploadError: controlledSetError,
  onAfterSuccess,
  onBeforeUploadAttempt,
}: UseAisleAssetUploadFlowOptions) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const queryClient = useQueryClient();
  const limits = useUploadLimits();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingPickAisleIdRef = useRef<string | null>(null);
  const uploadingAisleIdRef = useRef<string | null>(null);
  const lastAisleIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastResultRef = useRef<BulkUploadRunResult | null>(null);
  const [internalError, setInternalError] = useState<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [currentTargetAisleId, setCurrentTargetAisleId] = useState<string | null>(null);
  const [progress, setProgress] = useState<BulkUploadProgressSnapshot | null>(null);

  const controlled = controlledSetError !== undefined;
  const uploadError = controlled ? (controlledError ?? null) : internalError;
  const setUploadError = controlled ? controlledSetError! : setInternalError;

  const isUploadingPhotos = uploadingAisleId !== null;
  useBeforeUnloadWarning(isUploadingPhotos);

  const setActiveUploadingAisleId = useCallback((aisleId: string | null) => {
    uploadingAisleIdRef.current = aisleId;
    setUploadingAisleId(aisleId);
  }, []);

  const invalidateAisle = useCallback(
    (aisleId: string) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.aisleSourceAssets(inventoryId, aisleId),
      });
    },
    [inventoryId, queryClient]
  );

  const uploadFilesForAisle = useCallback(
    async (aisleId: string, files: File[], opts?: { onlyFailed?: boolean }) => {
      if (!inventoryId || (!files.length && !opts?.onlyFailed)) return;
      if (uploadingAisleIdRef.current !== null) return;
      onBeforeUploadAttempt?.();
      setUploadError(null);
      lastAisleIdRef.current = aisleId;
      setActiveUploadingAisleId(aisleId);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const prev = lastResultRef.current;
        const result = await executeBulkUpload({
          files,
          signal: controller.signal,
          onProgress: setProgress,
          maxFilesPerBatch: limits.maxFilesPerRequest,
          maxBytesPerBatch: limits.maxBytesPerRequest,
          maxFileSizeBytes: limits.maxFileSizeBytes,
          concurrency: limits.uploadConcurrency,
          retryAttempts: limits.retryAttempts,
          retryBaseDelayMs: limits.retryBaseDelayMs,
          existingFiles: opts?.onlyFailed && prev ? prev.files : undefined,
          onlyClientIds:
            opts?.onlyFailed && prev
              ? new Set(prev.files.filter((f) => f.status === 'failed').map((f) => f.clientId))
              : undefined,
          uploadBatchId: opts?.onlyFailed && prev ? prev.uploadBatchId : undefined,
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
        lastResultRef.current = result;
        if (result.completedCount > 0) {
          invalidateAisle(aisleId);
          showSnackbar(
            t('aisle.assets_uploaded_snackbar', { count: result.completedCount }),
            result.failedCount > 0 ? 'warning' : 'success'
          );
          onAfterSuccess?.();
        } else if (result.failedCount > 0 && result.cancelledCount === 0) {
          const message = t('uploads.photos.error');
          setUploadError(message);
          showSnackbar(message, 'error');
        }
      } catch (err) {
        if (isAbortError(err)) {
          return;
        }
        const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
        const message = resolveApiErrorMessage(apiErr, 'errors.upload_failed');
        setUploadError(message);
        showSnackbar(message, 'error');
      } finally {
        setActiveUploadingAisleId(null);
        abortRef.current = null;
      }
    },
    [
      inventoryId,
      invalidateAisle,
      limits.maxBytesPerRequest,
      limits.maxFileSizeBytes,
      limits.maxFilesPerRequest,
      limits.retryAttempts,
      limits.retryBaseDelayMs,
      limits.uploadConcurrency,
      onAfterSuccess,
      onBeforeUploadAttempt,
      setActiveUploadingAisleId,
      setUploadError,
      showSnackbar,
      t,
    ]
  );

  const beginUploadForAisle = useCallback(
    (aisleId: string) => {
      if (uploadingAisleIdRef.current !== null) return;
      setUploadError(null);
      pendingPickAisleIdRef.current = aisleId;
      setCurrentTargetAisleId(aisleId);
      fileInputRef.current?.click();
    },
    [setUploadError]
  );

  const handleNativeFileInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      const aisleId = pendingPickAisleIdRef.current;
      pendingPickAisleIdRef.current = null;
      setCurrentTargetAisleId(null);
      e.target.value = '';
      if (!aisleId || !files.length) return;
      await uploadFilesForAisle(aisleId, files);
    },
    [uploadFilesForAisle]
  );

  const handleFilesSelectedForAisle = useCallback(
    async (aisleId: string, files: File[]) => {
      if (uploadingAisleIdRef.current !== null) return;
      setCurrentTargetAisleId(null);
      pendingPickAisleIdRef.current = null;
      await uploadFilesForAisle(aisleId, files);
    },
    [uploadFilesForAisle]
  );

  const cancelUpload = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retryFailedUploads = useCallback(async () => {
    const aisleId = lastAisleIdRef.current;
    if (!aisleId || !lastResultRef.current) return;
    await uploadFilesForAisle(aisleId, [], { onlyFailed: true });
  }, [uploadFilesForAisle]);

  return {
    fileInputRef,
    currentTargetAisleId,
    uploadingAisleId,
    isUploadingPhotos,
    uploadError,
    setUploadError,
    beginUploadForAisle,
    handleNativeFileInputChange,
    handleFilesSelectedForAisle,
    progress,
    cancelUpload,
    retryFailedUploads,
  };
}
