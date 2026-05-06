import { useCallback, useState } from 'react';
import { fetchInventoryVisualReferenceFile } from '../../../api/client';
import { ApiError } from '../../../api/types';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';

type InventoryReferencePreviewResult = { imageSrc: string; revoke: () => void };

export interface UseInventoryReferencePreviewOptions {
  inventoryId: string;
  fetchInventoryVisualReferenceFileFn?: typeof fetchInventoryVisualReferenceFile;
}

export function useInventoryReferencePreview({
  inventoryId,
  fetchInventoryVisualReferenceFileFn,
}: UseInventoryReferencePreviewOptions) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const loadPreview = useCallback(
    async (item: ManagedImageAssetItem): Promise<InventoryReferencePreviewResult> => {
      setIsLoading(true);
      setError(null);
      try {
        const doFetch = fetchInventoryVisualReferenceFileFn ?? fetchInventoryVisualReferenceFile;
        const result = await doFetch(inventoryId, item.id);
        setPreviewUrl(result.imageSrc);
        return result;
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setError(err);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchInventoryVisualReferenceFileFn, inventoryId]
  );

  const clearPreview = useCallback(() => {
    setPreviewUrl(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    previewUrl,
    isLoading,
    error,
    loadPreview,
    clearPreview,
    clearError,
  };
}
