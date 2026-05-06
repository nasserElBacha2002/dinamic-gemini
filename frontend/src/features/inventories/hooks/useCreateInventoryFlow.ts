import { useCallback, useState } from 'react';
import { createInventory, uploadInventoryVisualReferences } from '../../../api/client';
import type { CreateInventoryRequest, Inventory } from '../../../api/types';
import { ApiError } from '../../../api/types';

export interface UseCreateInventoryFlowOptions {
  createInventoryFn?: (body: CreateInventoryRequest) => Promise<Inventory>;
}

export function useCreateInventoryFlow({ createInventoryFn }: UseCreateInventoryFlowOptions = {}) {
  const [isCreating, setIsCreating] = useState(false);
  const [isUploadingReferences, setIsUploadingReferences] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const submitCreateInventory = useCallback(
    async (body: CreateInventoryRequest): Promise<Inventory> => {
      setIsCreating(true);
      setError(null);
      try {
        const doCreate = createInventoryFn ?? createInventory;
        return await doCreate(body);
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setError(err);
        throw err;
      } finally {
        setIsCreating(false);
      }
    },
    [createInventoryFn]
  );

  const submitUploadInventoryReferences = useCallback(
    async (inventoryId: string, files: File[]): Promise<void> => {
      setIsUploadingReferences(true);
      setError(null);
      try {
        await uploadInventoryVisualReferences(inventoryId, files);
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setError(err);
        throw err;
      } finally {
        setIsUploadingReferences(false);
      }
    },
    []
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    submitCreateInventory,
    submitUploadInventoryReferences,
    isCreating,
    isUploadingReferences,
    error,
    clearError,
  };
}
