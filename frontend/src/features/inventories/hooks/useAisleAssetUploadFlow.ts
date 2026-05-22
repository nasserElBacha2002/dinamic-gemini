import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { isTooManyFilesForUpload, tooManyFilesMessage } from '../../../utils/uploadFileLimits';
import { useAppSnackbar } from '../../../components/ui';
import { useBeforeUnloadWarning, useUploadAisleAssetsFlex } from '../../../hooks';

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
 * Explicit aisle asset upload flow: pick an aisle, open the native file selector, upload selected files.
 *
 * Internal: `pendingPickAisleIdRef` holds the aisle id between `input.click()` and the `change` event.
 * React state updates from `beginUploadForAisle` are not guaranteed to flush before `change` fires, so
 * the ref is the reliable hand-off; it is not part of the public API and is cleared after each pick.
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
  /** See module doc — bridges native file input timing only; never exposed to consumers. */
  const pendingPickAisleIdRef = useRef<string | null>(null);
  const [internalError, setInternalError] = useState<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [currentTargetAisleId, setCurrentTargetAisleId] = useState<string | null>(null);

  const controlled = controlledSetError !== undefined;
  const uploadError = controlled ? (controlledError ?? null) : internalError;
  const setUploadError = controlled ? controlledSetError! : setInternalError;

  const uploadMutation = useUploadAisleAssetsFlex(inventoryId);
  const isUploadingPhotos = uploadingAisleId !== null;

  useBeforeUnloadWarning(isUploadingPhotos);

  const uploadFilesForAisle = useCallback(
    async (aisleId: string, files: File[]) => {
      if (!inventoryId || !files.length) return;
      if (isTooManyFilesForUpload(files.length)) {
        setUploadError(tooManyFilesMessage('aisle'));
        return;
      }
      onBeforeUploadAttempt?.();
      setUploadError(null);
      setUploadingAisleId(aisleId);
      try {
        await uploadMutation.mutateAsync({ aisleId, files });
        showSnackbar(t('uploads.photos.success'), 'success');
        onAfterSuccess?.();
      } catch (err) {
        const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
        const message = resolveApiErrorMessage(apiErr, 'errors.upload_failed');
        setUploadError(message);
        showSnackbar(message, 'error');
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
    isUploadingPhotos,
    uploadError,
    setUploadError,
    beginUploadForAisle,
    handleNativeFileInputChange,
    handleFilesSelectedForAisle,
  };
}
