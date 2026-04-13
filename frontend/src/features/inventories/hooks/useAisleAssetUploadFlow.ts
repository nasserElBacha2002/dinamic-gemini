import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAppSnackbar } from '../../../components/ui';
import { useUploadAisleAssetsFlex } from '../../../hooks';

function readFilesFromInput(
  e: React.ChangeEvent<HTMLInputElement>,
  pendingAisleIdRef: React.MutableRefObject<string | null>
): { files: File[]; aisleId: string } | null {
  const aisleId = pendingAisleIdRef.current;
  const files = e.target.files;
  if (!aisleId || !files?.length) return null;
  return { files: Array.from(files), aisleId };
}

export interface UseAisleAssetUploadFlowOptions {
  inventoryId: string;
  onAfterSuccess?: () => void;
  /** e.g. clear processing error when a new upload starts */
  onBeforeUpload?: () => void;
}

export function useAisleAssetUploadFlow({
  inventoryId,
  onAfterSuccess,
  onBeforeUpload,
}: UseAisleAssetUploadFlowOptions) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingAisleIdRef = useRef<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const uploadMutation = useUploadAisleAssetsFlex(inventoryId);

  const openPickerForAisle = useCallback(
    (aisleId: string) => {
      setUploadError(null);
      pendingAisleIdRef.current = aisleId;
      fileInputRef.current?.click();
    },
    []
  );

  const handleFileInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const ctx = readFilesFromInput(e, pendingAisleIdRef);
      pendingAisleIdRef.current = null;
      e.target.value = '';
      if (!inventoryId || !ctx) return;

      onBeforeUpload?.();
      setUploadError(null);
      setUploadingAisleId(ctx.aisleId);
      try {
        const result = await uploadMutation.mutateAsync({ aisleId: ctx.aisleId, files: ctx.files });
        showSnackbar(t('aisle.assets_uploaded_snackbar', { count: result.assets.length }), 'success');
        onAfterSuccess?.();
      } catch (err) {
        const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
        setUploadError(resolveApiErrorMessage(apiErr, 'errors.upload_failed'));
      } finally {
        setUploadingAisleId(null);
      }
    },
    [inventoryId, onAfterSuccess, onBeforeUpload, showSnackbar, t, uploadMutation]
  );

  return {
    fileInputRef,
    uploadingAisleId,
    uploadError,
    setUploadError,
    openPickerForAisle,
    handleFileInputChange,
  };
}
