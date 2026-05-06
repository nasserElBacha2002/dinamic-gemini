import { useCallback, useState } from 'react';
import { fetchInventoryVisualReferenceFile } from '../../../api/client';
import { ApiError } from '../../../api/types';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';

type InventoryReferencePreviewResult = Awaited<ReturnType<typeof fetchInventoryVisualReferenceFile>>;

export interface UseInventoryReferencePreviewOptions {
  inventoryId: string;
  fetchInventoryVisualReferenceFileFn?: typeof fetchInventoryVisualReferenceFile;
}

export function useInventoryReferencePreview({
  inventoryId,
  fetchInventoryVisualReferenceFileFn,
}: UseInventoryReferencePreviewOptions) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const loadPreview = useCallback(
    async (item: ManagedImageAssetItem): Promise<InventoryReferencePreviewResult> => {
      setIsLoading(true);
      setError(null);
      try {
        const doFetch = fetchInventoryVisualReferenceFileFn ?? fetchInventoryVisualReferenceFile;
        const result = await doFetch(inventoryId, item.id);
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

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    isLoading,
    error,
    loadPreview,
    clearError,
  };
}
