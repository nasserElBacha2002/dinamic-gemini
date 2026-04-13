import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAppSnackbar } from '../../../components/ui';
import { useUploadAisleAssetsFlex } from '../../../hooks';

export interface UseAisleAssetUploadFlowOptions {
  inventoryId: string;
  /**
   * When both are passed, upload errors are owned by the parent (explicit coordination with other flows).
   */
  uploadError?: string | null;
  setUploadError?: (message: string | null) => void;
  onAfterSuccess?: () => void;
  /** Called immediately before an upload mutation runs (e.g. clear sibling flow errors). */
  onBeforeUploadAttempt?: () => void;
}

/**
 * Explicit aisle asset upload flow: pick an aisle, open the native file selector, upload selected files.
 * `pendingPickAisleIdRef` only bridges sync timing between click() and change (React state may lag one frame).
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingPickAisleIdRef = useRef<string | null>(null);
  const [internalError, setInternalError] = useState<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [currentTargetAisleId, setCurrentTargetAisleId] = useState<string | null>(null);

  const controlled = controlledSetError !== undefined;
  const uploadError = controlled ? (controlledError ?? null) : internalError;
  const setUploadError = controlled ? controlledSetError! : setInternalError;

  const uploadMutation = useUploadAisleAssetsFlex(inventoryId);

  const uploadFilesForAisle = useCallback(
    async (aisleId: string, files: File[]) => {
      if (!inventoryId || !files.length) return;
      onBeforeUploadAttempt?.();
      setUploadError(null);
      setUploadingAisleId(aisleId);
      try {
        const result = await uploadMutation.mutateAsync({ aisleId, files });
        showSnackbar(t('aisle.assets_uploaded_snackbar', { count: result.assets.length }), 'success');
        onAfterSuccess?.();
      } catch (err) {
        const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
        setUploadError(resolveApiErrorMessage(apiErr, 'errors.upload_failed'));
      } finally {
        setUploadingAisleId(null);
      }
    },
    [inventoryId, onAfterSuccess, onBeforeUploadAttempt, setUploadError, showSnackbar, t, uploadMutation]
  );

  const beginUploadForAisle = useCallback(
    (aisleId: string) => {
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

  /** Programmatic entry (e.g. drag-and-drop) when the target aisle is already known. */
  const handleFilesSelectedForAisle = useCallback(
    async (aisleId: string, files: File[]) => {
      setCurrentTargetAisleId(null);
      pendingPickAisleIdRef.current = null;
      await uploadFilesForAisle(aisleId, files);
    },
    [uploadFilesForAisle]
  );

  return {
    fileInputRef,
    currentTargetAisleId,
    uploadingAisleId,
    uploadError,
    setUploadError,
    beginUploadForAisle,
    handleNativeFileInputChange,
    handleFilesSelectedForAisle,
  };
}
